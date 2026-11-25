import asyncio
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.contracts import build_position_extraction
from app.agents.graph import (
    assess,
    board_graph,
    build_synthesis_input,
    call_role,
    challenge,
    synthesize,
)
from app.database import Base
from app.company import ensure_company
from app.models import (
    AgentContribution,
    BoardMeeting,
    MeetingRunCheckpoint,
    MeetingRunEvent,
    MeetingStatus,
)
from app.routers import meetings
from app.schemas import MeetingOut, MeetingProgressOut


def structured_assessment_json():
    return json.dumps({
        "schema_version": 1,
        "executive_position": "conditional",
        "recommendation": "Proceed with a bounded discovery phase.",
        "confidence": "medium",
        "supporting_facts": [],
        "assumptions": [],
        "hypotheses": [],
        "unknowns": [],
        "risks": [],
        "alternatives": [],
        "dependencies": [],
        "success_criteria": [],
        "decision_gates": [],
    })


def structured_targeted_challenge_json(challenger_role):
    roles = ("CEO", "CFO", "CTO", "CSO")
    return json.dumps({
        "schema_version": 1,
        "challenges": [
            {
                "target_role": target_role,
                "target_claim_id": f"{target_role}.recommendation",
                "challenge_question": f"What evidence supports {target_role}'s recommendation?",
                "why_it_matters": "The decision depends on this recommendation.",
            }
            for target_role in roles
            if target_role != challenger_role
        ],
    })


def structured_revision_json():
    return json.dumps({
        "schema_version": 1,
        "position_change": "maintain",
        "previous_position": "conditional",
        "revised_position": "conditional",
        "reason_for_change": "The original position remains appropriate.",
        "arguments_that_changed_my_view": [],
        "remaining_disagreements": [],
    })


def structured_board_synthesis_json():
    return json.dumps({
        "schema_version": 1,
        "executive_summary": "A bounded discovery phase is warranted.",
        "recommendation": "Proceed conditionally.",
        "rationale": "The evidence is incomplete.",
        "shared_conclusions": ["More evidence is needed."],
        "genuine_disagreements": ["The CFO favors deferral."],
        "material_dissent": [],
        "evidence_register": [],
        "unresolved_questions": ["Will customers participate?"],
        "next_actions": [],
        "decision_gates": ["Review evidence before product investment."],
    })


class FakeBoardGraph:
    async def ainvoke(self, _meeting_input, config):
        report = config["configurable"]["progress_callback"]
        await report({
            "event_type": "agent_started",
            "phase": "assessment",
            "role": "CEO",
            "message": "CEO started an independent assessment.",
        })
        await report({
            "event_type": "agent_output",
            "phase": "assessment",
            "role": "CEO",
            "message": "Partial CEO response",
        })
        await report({
            "event_type": "checkpoint_saved",
            "phase": "assessment",
            "role": "CEO",
            "message": "CEO assessment checkpoint saved.",
            "content": "CEO assessment",
            "provider": "local",
            "model": "test-model",
        })
        await report({
            "event_type": "agent_completed",
            "phase": "assessment",
            "role": "CEO",
            "message": "CEO completed its independent assessment.",
        })
        return {
            "assessments": {role: f"{role} assessment" for role in ("CEO", "CFO", "CTO", "CSO")},
            "critiques": {role: f"{role} challenge" for role in ("CEO", "CFO", "CTO", "CSO")},
            "recommendation": "Board recommendation",
            "provider_metadata": {},
        }


class FailingBoardGraph:
    async def ainvoke(self, _meeting_input, config):
        raise RuntimeError("Local model is unavailable")

class CapturingResumeGraph:
    def __init__(self):
        self.meeting_input = None

    async def ainvoke(self, meeting_input, config):
        self.meeting_input = meeting_input
        return {
            "assessments": meeting_input["assessments"],
            "critiques": meeting_input["critiques"],
            "recommendation": "Resumed board recommendation",
            "provider_metadata": meeting_input["provider_metadata"],
        }


class MeetingProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "progress-tests.db"
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        self.company = ensure_company(self.session_factory())
        self.db = self.session_factory()
        meeting = BoardMeeting(
            company_id=self.company.id,
            title="Progress test",
            agenda="Test persistent progress events and status.",
        )
        self.db.add(meeting)
        self.db.commit()
        self.meeting_id = meeting.id
        self.session_local_patch = patch(
            "app.routers.meetings.SessionLocal",
            self.session_factory,
        )
        self.session_local_patch.start()

    def tearDown(self):
        self.session_local_patch.stop()
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def start_run(self, graph):
        tasks = BackgroundTasks()
        with patch("app.routers.meetings.board_graph", graph):
            meeting = asyncio.run(meetings.run_meeting(self.meeting_id, tasks, self.db, self.company))
            self.assertEqual(meeting.status, MeetingStatus.running)
            asyncio.run(tasks())
        self.db.expire_all()

    def test_run_executes_in_background_and_persists_agent_events(self):
        self.start_run(FakeBoardGraph())

        meeting = self.db.query(BoardMeeting).filter_by(id=self.meeting_id).one()
        self.assertEqual(meeting.status, MeetingStatus.completed)
        self.assertEqual(len(meeting.contributions), 8)

        progress = meetings.get_meeting_progress(self.meeting_id, 0, self.db, self.company)
        self.assertEqual(progress["meeting"].status, MeetingStatus.completed)
        validated_progress = MeetingProgressOut.model_validate(progress)
        self.assertEqual(validated_progress.meeting.id, self.meeting_id)
        self.assertIsNone(validated_progress.meeting.contributions[0].revision)
        self.assertEqual(validated_progress.progress_percent, 100)
        self.assertIsNone(validated_progress.eta_seconds)
        self.assertLess(validated_progress.elapsed_seconds, 10)
        self.assertEqual(len(validated_progress.checkpoints), 1)
        self.assertEqual(validated_progress.checkpoints[0].content, "CEO assessment")
        self.assertEqual(
            [event.event_type for event in validated_progress.events],
            [
                "run_started",
                "agent_started",
                "agent_output",
                "checkpoint_saved",
                "agent_completed",
                "run_completed",
            ],
        )
        checkpoint = (
            self.db.query(MeetingRunCheckpoint)
            .filter_by(meeting_id=self.meeting_id, phase="assessment", role="CEO")
            .one()
        )
        self.assertEqual(checkpoint.content, "CEO assessment")
        self.assertEqual(checkpoint.model_name, "test-model")

        last_event_id = validated_progress.events[-1].id
        later_progress = meetings.get_meeting_progress(
            self.meeting_id,
            last_event_id,
            self.db,
            self.company,
        )
        self.assertEqual(later_progress["events"], [])
        self.assertEqual(later_progress["checkpoints"], [])

    def test_revision_checkpoint_is_additive_and_legacy_contributions_remain_valid(self):
        self.db.add(AgentContribution(
            meeting_id=self.meeting_id,
            role="CEO",
            phase="assessment",
            assessment="Historical free-form assessment.",
            critique="",
        ))
        self.db.add(MeetingRunCheckpoint(
            meeting_id=self.meeting_id,
            phase="revision",
            role="CEO",
            content=structured_revision_json(),
            model_provider="local",
            model_name="test-model",
        ))
        self.db.commit()

        meeting = MeetingOut.model_validate(
            meetings.load_meeting(self.db, self.meeting_id)
        )

        contribution = meeting.contributions[0]
        self.assertEqual(contribution.assessment, "Historical free-form assessment.")
        self.assertEqual(contribution.revision, structured_revision_json())

    def test_failed_run_is_logged_and_can_be_retried(self):
        self.start_run(FailingBoardGraph())
        meeting = self.db.query(BoardMeeting).filter_by(id=self.meeting_id).one()
        self.assertEqual(meeting.status, MeetingStatus.failed)
        failure_event = (
            self.db.query(MeetingRunEvent)
            .filter_by(meeting_id=self.meeting_id, attempt=1, event_type="run_failed")
            .one()
        )
        self.assertIn("Local model is unavailable", failure_event.message)

        self.start_run(FakeBoardGraph())
        meeting = self.db.query(BoardMeeting).filter_by(id=self.meeting_id).one()
        self.assertEqual(meeting.status, MeetingStatus.completed)
        attempts = (
            self.db.query(MeetingRunEvent.attempt)
            .filter(MeetingRunEvent.meeting_id == self.meeting_id)
            .distinct()
            .order_by(MeetingRunEvent.attempt)
            .all()
        )
        self.assertEqual([attempt[0] for attempt in attempts], [1, 2])

    def test_running_meeting_cannot_be_started_twice(self):
        tasks = BackgroundTasks()
        with patch("app.routers.meetings.board_graph", FakeBoardGraph()):
            asyncio.run(meetings.run_meeting(self.meeting_id, tasks, self.db, self.company))
            with self.assertRaises(HTTPException) as error:
                asyncio.run(meetings.run_meeting(self.meeting_id, BackgroundTasks(), self.db, self.company))
        self.assertEqual(error.exception.status_code, 409)

    def test_stale_attempt_cannot_persist_progress_or_checkpoint(self):
        self.db.add(
            MeetingRunEvent(
                meeting_id=self.meeting_id,
                attempt=1,
                event_type="run_started",
                phase="setup",
                message="Attempt 1 started.",
            )
        )
        self.db.query(BoardMeeting).filter_by(id=self.meeting_id).update(
            {BoardMeeting.status: MeetingStatus.running}
        )
        self.db.commit()
        meeting_id = self.meeting_id
        session_factory = self.session_factory

        class SupersedingGraph:
            async def ainvoke(self, _meeting_input, config):
                newer_db = session_factory()
                try:
                    newer_db.add(
                        MeetingRunEvent(
                            meeting_id=meeting_id,
                            attempt=2,
                            event_type="run_started",
                            phase="setup",
                            message="Attempt 2 started.",
                        )
                    )
                    newer_db.commit()
                finally:
                    newer_db.close()

                await config["configurable"]["progress_callback"]({
                    "event_type": "checkpoint_saved",
                    "phase": "assessment",
                    "role": "CEO",
                    "message": "Stale checkpoint.",
                    "content": "Stale response",
                    "provider": "local",
                    "model": "test-model",
                })

        with patch("app.routers.meetings.board_graph", SupersedingGraph()):
            asyncio.run(meetings.run_meeting_in_background(self.meeting_id, 1))

        self.db.expire_all()
        self.assertEqual(
            self.db.query(BoardMeeting).filter_by(id=self.meeting_id).one().status,
            MeetingStatus.running,
        )
        self.assertEqual(
            self.db.query(MeetingRunCheckpoint)
            .filter_by(meeting_id=self.meeting_id, phase="assessment")
            .count(),
            0,
        )
        self.assertEqual(
            self.db.query(MeetingRunEvent)
            .filter_by(
                meeting_id=self.meeting_id,
                attempt=1,
                event_type="checkpoint_saved",
            )
            .count(),
            0,
        )

    def test_stale_attempt_cannot_overwrite_completed_meeting_result(self):
        self.db.add(
            MeetingRunEvent(
                meeting_id=self.meeting_id,
                attempt=1,
                event_type="run_started",
                phase="setup",
                message="Attempt 1 started.",
            )
        )
        self.db.query(BoardMeeting).filter_by(id=self.meeting_id).update(
            {BoardMeeting.status: MeetingStatus.running}
        )
        self.db.commit()
        meeting_id = self.meeting_id
        session_factory = self.session_factory

        class SupersedingGraph:
            async def ainvoke(self, _meeting_input, config):
                newer_db = session_factory()
                try:
                    newer_db.add(
                        MeetingRunEvent(
                            meeting_id=meeting_id,
                            attempt=2,
                            event_type="run_started",
                            phase="setup",
                            message="Attempt 2 started.",
                        )
                    )
                    newer_db.commit()
                finally:
                    newer_db.close()
                return {
                    "assessments": {},
                    "critiques": {},
                    "recommendation": "Stale recommendation",
                    "provider_metadata": {},
                }

        with patch("app.routers.meetings.board_graph", SupersedingGraph()):
            asyncio.run(meetings.run_meeting_in_background(self.meeting_id, 1))

        self.db.expire_all()
        meeting = self.db.query(BoardMeeting).filter_by(id=self.meeting_id).one()
        self.assertEqual(meeting.status, MeetingStatus.running)
        self.assertIsNone(meeting.resolution)
        self.assertEqual(meeting.contributions, [])
        self.assertEqual(
            self.db.query(MeetingRunEvent)
            .filter_by(
                meeting_id=self.meeting_id,
                attempt=1,
                event_type="run_completed",
            )
            .count(),
            0,
        )

    def test_stale_attempt_failure_does_not_fail_newer_run(self):
        self.db.add(
            MeetingRunEvent(
                meeting_id=self.meeting_id,
                attempt=1,
                event_type="run_started",
                phase="setup",
                message="Attempt 1 started.",
            )
        )
        self.db.query(BoardMeeting).filter_by(id=self.meeting_id).update(
            {BoardMeeting.status: MeetingStatus.running}
        )
        self.db.commit()
        meeting_id = self.meeting_id
        session_factory = self.session_factory

        class SupersedingGraph:
            async def ainvoke(self, _meeting_input, config):
                newer_db = session_factory()
                try:
                    newer_db.add(
                        MeetingRunEvent(
                            meeting_id=meeting_id,
                            attempt=2,
                            event_type="run_started",
                            phase="setup",
                            message="Attempt 2 started.",
                        )
                    )
                    newer_db.commit()
                finally:
                    newer_db.close()
                raise RuntimeError("Late failure from attempt 1")

        with patch("app.routers.meetings.board_graph", SupersedingGraph()):
            asyncio.run(meetings.run_meeting_in_background(self.meeting_id, 1))

        self.db.expire_all()
        meeting = self.db.query(BoardMeeting).filter_by(id=self.meeting_id).one()
        self.assertEqual(meeting.status, MeetingStatus.running)
        self.assertEqual(
            self.db.query(MeetingRunEvent)
            .filter_by(
                meeting_id=self.meeting_id,
                attempt=1,
                event_type="run_failed",
            )
            .count(),
            0,
        )

    def test_api_restart_backfills_completed_streams_and_retry_reuses_them(self):
        roles = ("CEO", "CFO", "CTO", "CSO")
        self.db.add(
            MeetingRunEvent(
                meeting_id=self.meeting_id,
                attempt=1,
                event_type="run_started",
                phase="setup",
                message="Board deliberation started.",
            )
        )
        for phase in ("assessment", "challenge"):
            for role in roles:
                self.db.add_all([
                    MeetingRunEvent(
                        meeting_id=self.meeting_id,
                        attempt=1,
                        event_type="agent_output",
                        phase=phase,
                        role=role,
                        message=f"{role} saved ",
                    ),
                    MeetingRunEvent(
                        meeting_id=self.meeting_id,
                        attempt=1,
                        event_type="agent_output",
                        phase=phase,
                        role=role,
                        message=phase,
                    ),
                    MeetingRunEvent(
                        meeting_id=self.meeting_id,
                        attempt=1,
                        event_type="agent_completed",
                        phase=phase,
                        role=role,
                        message=f"{role} completed {phase}.",
                    ),
                ])
        extraction_content = build_position_extraction({
            role: f"{role} saved assessment"
            for role in roles
        }).model_dump_json()
        self.db.add(MeetingRunCheckpoint(
            meeting_id=self.meeting_id,
            phase="position_extraction",
            role="BOARD",
            content=extraction_content,
            model_provider="system",
            model_name="deterministic-position-extraction-v1",
        ))
        self.db.query(BoardMeeting).filter_by(id=self.meeting_id).update(
            {BoardMeeting.status: MeetingStatus.running}
        )
        self.db.commit()

        meetings.recover_interrupted_runs(self.db)
        self.db.expire_all()
        interrupted = self.db.query(BoardMeeting).filter_by(id=self.meeting_id).one()
        self.assertEqual(interrupted.status, MeetingStatus.failed)
        self.assertEqual(
            self.db.query(MeetingRunCheckpoint)
            .filter_by(meeting_id=self.meeting_id)
            .count(),
            9,
        )

        graph = CapturingResumeGraph()
        self.start_run(graph)
        self.assertEqual(graph.meeting_input["assessments"]["CEO"], "CEO saved assessment")
        self.assertEqual(graph.meeting_input["critiques"]["CSO"], "CSO saved challenge")
        self.assertEqual(graph.meeting_input["position_extraction"], extraction_content)
        self.assertEqual(graph.meeting_input["provider_metadata"]["CEO"]["provider"], "unknown")
        self.assertNotIn("BOARD", graph.meeting_input["provider_metadata"])
        self.assertEqual(
            self.db.query(BoardMeeting).filter_by(id=self.meeting_id).one().status,
            MeetingStatus.completed,
        )

    def test_graph_emits_agent_and_phase_progress(self):
        progress_events = []

        async def record_progress(event):
            progress_events.append(event)

        async def model_response(role, _system, _user, _config, phase, **_kwargs):
            if phase == "assessment":
                return structured_assessment_json(), "local", "test-model"
            if phase == "challenge":
                return structured_targeted_challenge_json(role), "local", "test-model"
            if phase == "revision":
                return structured_revision_json(), "local", "test-model"
            if phase == "synthesis":
                return structured_board_synthesis_json(), "local", "test-model"
            return "agent challenge", "local", "test-model"

        with patch(
            "app.agents.graph.call_role",
            new=AsyncMock(side_effect=model_response),
        ):
            asyncio.run(
                board_graph.ainvoke(
                    {
                        "title": "Progress test",
                        "agenda": "Test graph progress callbacks.",
                        "founder_context": "",
                    },
                    config={"configurable": {"progress_callback": record_progress}},
                )
            )

        agent_events = [event for event in progress_events if event["event_type"] == "agent_started"]
        self.assertEqual(len(agent_events), 13)
        self.assertEqual(
            {event["phase"] for event in progress_events if event["event_type"] == "phase_started"},
            {"assessment", "position_extraction", "challenge", "revision", "synthesis"},
        )
        self.assertEqual(
            len([event for event in progress_events if event["event_type"] == "checkpoint_saved"]),
            14,
        )

    def test_malformed_assessment_fails_the_phase_without_saving_a_checkpoint(self):
        progress_events = []

        async def record_progress(event):
            progress_events.append(event)

        with (
            patch(
                "app.agents.graph.get_settings",
                return_value=SimpleNamespace(agent_concurrency=4),
            ),
            patch(
                "app.agents.graph.call_role",
                new=AsyncMock(return_value=("not JSON", "local", "test-model")),
            ),
            self.assertRaisesRegex(ValueError, "must be a single valid JSON object"),
        ):
            asyncio.run(
                assess(
                    {
                        "title": "Malformed output test",
                        "agenda": "Verify invalid output is not successful.",
                        "founder_context": "",
                    },
                    config={"configurable": {"progress_callback": record_progress}},
                )
            )

        self.assertTrue(
            any(event["event_type"] == "agent_failed" for event in progress_events)
        )
        self.assertFalse(
            any(event["event_type"] == "checkpoint_saved" for event in progress_events)
        )

    def test_malformed_targeted_challenge_fails_without_saving_a_checkpoint(self):
        progress_events = []

        async def record_progress(event):
            progress_events.append(event)

        assessments = {
            role: structured_assessment_json()
            for role in ("CEO", "CFO", "CTO", "CSO")
        }
        with (
            patch(
                "app.agents.graph.get_settings",
                return_value=SimpleNamespace(agent_concurrency=4),
            ),
            patch(
                "app.agents.graph.call_role",
                new=AsyncMock(return_value=("not JSON", "local", "test-model")),
            ),
            self.assertRaisesRegex(ValueError, "must be a validated JSON object"),
        ):
            asyncio.run(
                challenge(
                    {
                        "title": "Malformed challenge test",
                        "agenda": "Verify invalid cross-examination is not checkpointed.",
                        "assessments": assessments,
                    },
                    config={"configurable": {"progress_callback": record_progress}},
                )
            )

        self.assertTrue(
            any(event["event_type"] == "agent_failed" for event in progress_events)
        )
        self.assertFalse(
            any(event["event_type"] == "checkpoint_saved" for event in progress_events)
        )

    def test_graph_skips_saved_agent_work_and_only_retries_synthesis(self):
        saved_state = {
            "title": "Progress test",
            "agenda": "Test reuse of persisted agent checkpoints.",
            "founder_context": "",
            "assessments": {role: f"{role} saved assessment" for role in ("CEO", "CFO", "CTO", "CSO")},
            "critiques": {role: f"{role} saved challenge" for role in ("CEO", "CFO", "CTO", "CSO")},
            "revisions": {
                role: structured_revision_json()
                for role in ("CEO", "CFO", "CTO", "CSO")
            },
            "provider_metadata": {},
        }
        progress_events = []

        async def record_progress(event):
            progress_events.append(event)

        call_role_mock = AsyncMock(
            return_value=(structured_board_synthesis_json(), "local", "test-model")
        )
        with patch("app.agents.graph.call_role", new=call_role_mock):
            result = asyncio.run(
                board_graph.ainvoke(
                    saved_state,
                    config={"configurable": {"progress_callback": record_progress}},
                )
            )

        self.assertEqual(call_role_mock.await_count, 1)
        self.assertEqual(call_role_mock.await_args.args[0], "BOARD")
        self.assertIn("Proceed conditionally.", result["recommendation"])
        reused = [event for event in progress_events if event["event_type"] == "checkpoint_reused"]
        self.assertEqual(len(reused), 12)

        call_role_mock.reset_mock()
        saved_state["recommendation"] = "Already saved synthesis"
        with patch("app.agents.graph.call_role", new=call_role_mock):
            completed = asyncio.run(
                board_graph.ainvoke(
                    saved_state,
                    config={"configurable": {"progress_callback": record_progress}},
                )
            )
        self.assertEqual(call_role_mock.await_count, 0)
        self.assertEqual(completed["recommendation"], "Already saved synthesis")

    def test_synthesis_input_is_bounded_and_keeps_each_agent_role(self):
        roles = ("CEO", "CFO", "CTO", "CSO")
        state = {
            "title": "BOARD_TITLE_START " + ("meeting " * 300) + " BOARD_TITLE_END",
            "agenda": "AGENDA_START " + ("agenda " * 1000) + " AGENDA_END",
            "founder_context": "CONTEXT_START " + ("context " * 1000) + " CONTEXT_END",
            "assessments": {
                role: f"ASSESSMENT_START_{role} " + ("assessment " * 500)
                + f" ASSESSMENT_END_{role}"
                for role in roles
            },
            "critiques": {
                role: f"CHALLENGE_START_{role} " + ("challenge " * 500)
                + f" CHALLENGE_END_{role}"
                for role in roles
            },
        }

        synthesis_input = build_synthesis_input(state, max_chars=2048)

        self.assertLessEqual(len(synthesis_input), 2048)
        self.assertIn("middle omitted to fit model context", synthesis_input)
        for role in roles:
            self.assertIn(f"### {role}\n", synthesis_input)
            self.assertIn(f"### {role} challenge\n", synthesis_input)
            self.assertIn(f"ASSESSMENT_START_{role}", synthesis_input)
            self.assertIn(f"ASSESSMENT_END_{role}", synthesis_input)
            self.assertIn(f"CHALLENGE_START_{role}", synthesis_input)
            self.assertIn(f"CHALLENGE_END_{role}", synthesis_input)

    def test_context_limit_retries_synthesis_with_smaller_input(self):
        roles = ("CEO", "CFO", "CTO", "CSO")
        saved_state = {
            "title": "Progress test",
            "agenda": "Test bounded synthesis retry.",
            "founder_context": "",
            "assessments": {
                role: f"{role} assessment " + ("assessment details " * 250)
                for role in roles
            },
            "critiques": {
                role: f"{role} challenge " + ("challenge details " * 250)
                for role in roles
            },
            "provider_metadata": {},
        }
        progress_events = []

        async def record_progress(event):
            progress_events.append(event)

        settings = SimpleNamespace(
            board_synthesis_max_input_chars=6000,
            provider_for=lambda _role: "local",
        )
        call_role_mock = AsyncMock(
            side_effect=[
                RuntimeError(
                    "The number of tokens to keep from the initial prompt is greater "
                    "than the context length."
                ),
                (structured_board_synthesis_json(), "local", "test-model"),
            ]
        )
        with (
            patch("app.agents.graph.get_settings", return_value=settings),
            patch("app.agents.graph.call_role", new=call_role_mock),
        ):
            result = asyncio.run(
                synthesize(
                    saved_state,
                    config={"configurable": {"progress_callback": record_progress}},
                )
            )

        first_input = call_role_mock.await_args_list[0].args[2]
        second_input = call_role_mock.await_args_list[1].args[2]
        self.assertLessEqual(len(first_input), 6000)
        self.assertLessEqual(len(second_input), 3000)
        self.assertLess(len(second_input), len(first_input))
        self.assertIn("Proceed conditionally.", result["recommendation"])
        retry_events = [
            event for event in progress_events
            if event["event_type"] == "agent_started"
        ]
        self.assertEqual(len(retry_events), 2)
        self.assertIn("retrying with a 3,000-character", retry_events[-1]["message"])

    def test_tpm_limit_retries_synthesis_with_smaller_input(self):
        state = {
            "title": "Progress test",
            "agenda": "Test total TPM synthesis retry.",
            "founder_context": "",
            "assessments": {
                role: f"{role} assessment " + ("assessment detail " * 700)
                for role in ("CEO", "CFO", "CTO", "CSO")
            },
            "critiques": {
                role: f"{role} challenge " + ("challenge detail " * 700)
                for role in ("CEO", "CFO", "CTO", "CSO")
            },
            "provider_metadata": {},
        }
        progress_events = []

        async def record_progress(event):
            progress_events.append(event)

        settings = SimpleNamespace(
            board_synthesis_max_input_chars=6000,
            provider_for=lambda _role: "cloud",
        )
        call_role_mock = AsyncMock(
            side_effect=[
                RuntimeError(
                    "Error code: 413 - Request too large for model "
                    "`qwen/qwen3.8-27b` on tokens per minute (TPM): "
                    "Limit 8000, Requested 12067."
                ),
                (structured_board_synthesis_json(), "groq", "qwen/qwen3.8-27b"),
            ]
        )
        with (
            patch("app.agents.graph.get_settings", return_value=settings),
            patch("app.agents.graph.call_role", new=call_role_mock),
        ):
            result = asyncio.run(
                synthesize(
                    state,
                    config={"configurable": {"progress_callback": record_progress}},
                )
            )

        first_input = call_role_mock.await_args_list[0].args[2]
        second_input = call_role_mock.await_args_list[1].args[2]
        self.assertLessEqual(len(first_input), 6000)
        self.assertLess(len(second_input), len(first_input))
        self.assertEqual(call_role_mock.await_args_list[1].kwargs["output_cap"], 1600)
        self.assertIn("Proceed conditionally.", result["recommendation"])
        retry_events = [
            event for event in progress_events
            if event["event_type"] == "agent_started"
        ]
        self.assertEqual(len(retry_events), 2)
        self.assertIn("8,000 allowed", retry_events[-1]["message"])
        self.assertIn("retrying with a", retry_events[-1]["message"])

    def test_board_synthesis_budget_applies_to_cloud_and_ui_selected_sources(self):
        state = {
            "title": "Progress test",
            "agenda": "Test provider-independent synthesis budget.",
            "founder_context": "",
            "assessments": {},
            "critiques": {},
            "provider_metadata": {},
        }
        settings = SimpleNamespace(
            board_synthesis_max_input_chars=6000,
            provider_for=lambda _role: "cloud",
        )
        call_role_mock = AsyncMock(
            return_value=(structured_board_synthesis_json(), "local", "test-model")
        )
        with (
            patch("app.agents.graph.get_settings", return_value=settings),
            patch(
                "app.agents.graph.build_synthesis_input",
                return_value="bounded local input",
            ) as build_input_mock,
            patch("app.agents.graph.call_role", new=call_role_mock),
        ):
            result = asyncio.run(
                synthesize(
                    state,
                    config={
                        "configurable": {
                            "llm_configs": {"BOARD": {"provider": "cloud"}}
                        }
                    },
                )
            )

        self.assertEqual(build_input_mock.call_args.args[1], 6000)
        self.assertIn("Proceed conditionally.", result["recommendation"])

    def test_call_role_streams_visible_text_and_excludes_non_text_blocks(self):
        class FakeStreamingLLM:
            async def astream(self, _messages):
                for content in (
                    "Hello ",
                    "x" * 1200,
                    [{"type": "reasoning", "text": "private reasoning"},
                     {"type": "text", "text": "!"}],
                ):
                    yield SimpleNamespace(content=content)

        progress_events = []

        async def record_progress(event):
            progress_events.append(event)

        async def run_call():
            return await call_role(
                "CEO",
                "system",
                "user",
                {"configurable": {"progress_callback": record_progress}},
                "assessment",
            )

        with patch("app.agents.graph.llm_for", return_value=(FakeStreamingLLM(), "local", "test-model")):
            result, provider, model = asyncio.run(run_call())

        streamed_text = "".join(
            event["message"]
            for event in progress_events
            if event["event_type"] == "agent_output"
        )
        self.assertEqual(streamed_text.strip(), result)
        self.assertNotIn("private reasoning", streamed_text)
        self.assertLessEqual(
            max(
                len(event["message"])
                for event in progress_events
                if event["event_type"] == "agent_output"
            ),
            512,
        )
        self.assertEqual((provider, model), ("local", "test-model"))

    def test_call_role_retries_output_token_rate_limit_with_provider_parameter(self):
        class RateLimitedStreamingLLM:
            def __init__(self):
                self.calls = 0
                self.bound_options = []

            def bind(self, **options):
                self.bound_options.append(options)
                return self

            async def astream(self, _messages):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError(
                        "Error code: 429 - output tokens per minute (OTPM): "
                        "Limit 1000, Requested 1348."
                    )
                yield SimpleNamespace(content="Retried response")

        for provider, expected_option in (
            ("groq", {"max_tokens": 900}),
            ("google_gemini", {"max_output_tokens": 900}),
        ):
            with self.subTest(provider=provider):
                model_client = RateLimitedStreamingLLM()
                progress_events = []

                async def record_progress(event):
                    progress_events.append(event)

                async def run_call():
                    return await call_role(
                        "CTO",
                        "system",
                        "user",
                        {"configurable": {"progress_callback": record_progress}},
                        "assessment",
                    )

                with patch(
                    "app.agents.graph.llm_for",
                    return_value=(model_client, provider, "test-model"),
                ):
                    result, used_provider, _ = asyncio.run(run_call())

                streamed = "".join(
                    event["message"]
                    for event in progress_events
                    if event["event_type"] == "agent_output"
                )
                self.assertEqual(result, "Retried response")
                self.assertEqual(streamed, result)
                self.assertEqual(used_provider, provider)
                self.assertEqual(model_client.bound_options, [expected_option])
                self.assertTrue(
                    any(
                        "retrying with a 900-token output cap" in event["message"]
                        for event in progress_events
                    )
                )

    def test_running_progress_reports_elapsed_time_and_adaptive_eta(self):
        now = datetime.now(timezone.utc)
        self.db.add_all([
            MeetingRunEvent(
                meeting_id=self.meeting_id,
                attempt=1,
                event_type="run_started",
                phase="setup",
                message="Started",
                created_at=now - timedelta(seconds=30),
            ),
            MeetingRunEvent(
                meeting_id=self.meeting_id,
                attempt=1,
                event_type="agent_started",
                phase="assessment",
                role="CEO",
                message="Started",
                created_at=now - timedelta(seconds=10),
            ),
        ])
        self.db.query(BoardMeeting).filter_by(id=self.meeting_id).update(
            {BoardMeeting.status: MeetingStatus.running}
        )
        self.db.commit()

        progress = meetings.get_meeting_progress(self.meeting_id, 0, self.db, self.company)
        validated_progress = MeetingProgressOut.model_validate(progress)
        self.assertAlmostEqual(validated_progress.elapsed_seconds, 30, delta=1)
        self.assertEqual(validated_progress.eta_seconds, 770)
        self.assertFalse(validated_progress.eta_calibrated)
        self.assertGreater(validated_progress.progress_percent, 0)
        slow_call_events = (
            self.db.query(MeetingRunEvent)
            .filter(
                MeetingRunEvent.meeting_id == self.meeting_id,
                MeetingRunEvent.attempt == 1,
                MeetingRunEvent.event_type.in_(meetings.PROGRESS_EVENT_TYPES),
            )
            .all()
        )
        slow_metrics = meetings.calculate_run_metrics(
            slow_call_events,
            MeetingStatus.running,
            now=now + timedelta(seconds=150),
        )
        self.assertGreater(slow_metrics["eta_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
