import asyncio
import re
import time
from collections.abc import Mapping
from typing import TypedDict, Any
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.runnables import RunnableConfig
from ..config import get_settings
from ..company import format_company_context
from ..memory import format_memory_context
from .contracts import (
    BoardSynthesis,
    ExecutiveAssessment,
    PositionExtraction,
    assessment_for_board,
    board_dissent_markdown,
    board_synthesis_markdown,
    build_position_extraction,
    format_challenge_docket,
    format_targeted_cross_examination,
    parse_structured_output,
    parse_targeted_cross_examination,
    parse_revision_for_assessment,
    revision_for_board,
    validate_assessment_evidence_references,
    validate_board_evidence_references,
    validate_claim_evidence_references,
)
from .prompts import (
    ASSESSMENT_OUTPUT_INSTRUCTIONS,
    CHALLENGE_OUTPUT_INSTRUCTIONS,
    EXECUTIVES,
    EXECUTIVE_PROFILES,
    BOARD_SYNTHESIS_PROMPT,
    POSITION_REVISION_PROMPT,
    executive_system_prompt,
)

class BoardState(TypedDict, total=False):
    title: str
    agenda: str
    founder_context: str
    assessments: dict[str, str]
    position_extraction: str
    critiques: dict[str, str]
    revisions: dict[str, str]
    recommendation: str
    rationale: str
    dissent: str
    provider_metadata: dict[str, dict[str, str]]
    evidence_register: list[dict[str, Any]]
    institutional_memory: list[dict[str, Any]]
    company_context: dict[str, Any]

def llm_for(
    role: str,
    runtime_config: Mapping[str, Any] | None = None,
):
    settings = get_settings()
    configurable = (runtime_config or {}).get("configurable") or {}
    source_config = configurable.get("llm_configs", {}).get(role)
    if source_config:
        provider = source_config["provider"].lower()
        source_provider = source_config.get("source_provider", provider).lower()
        model = source_config["model"]
        base_url = source_config["base_url"]
        api_key = source_config["api_key"]
    else:
        provider = settings.provider_for(role).lower()
        source_provider = provider
        model = settings.model_for(role)
        base_url = (
            settings.local_base_url if provider == "local" else settings.cloud_base_url
        )
        api_key = (
            settings.local_api_key if provider == "local" else settings.cloud_api_key
        )
    if source_provider == "anthropic":
        if not api_key:
            raise RuntimeError(f"{role} requires an Anthropic API key.")
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise RuntimeError(
                "Anthropic support is missing from the Python environment running "
                "the backend. Install requirements.txt with that same interpreter."
            ) from exc
        return (
            ChatAnthropic(
                model=model,
                api_key=api_key,
                base_url=base_url,
                max_retries=2,
            ),
            source_provider,
            model,
        )
    if source_provider == "google_gemini":
        if not api_key:
            raise RuntimeError(f"{role} requires a Google Gemini API key.")
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise RuntimeError(
                "Google Gemini support is missing from the Python environment "
                "running the backend. Install requirements.txt with that same interpreter."
            ) from exc
        return (
            ChatGoogleGenerativeAI(
                model=model,
                api_key=api_key,
                temperature=0.2,
                vertexai=False,
            ),
            source_provider,
            model,
        )
    if provider == "local":
        local_api_key = api_key or (
            "ollama" if source_provider == "ollama" else "lm-studio"
        )
        return (
            ChatOpenAI(
                model=model,
                base_url=base_url,
                api_key=local_api_key,
                temperature=0.2,
                max_retries=1,
            ),
            source_provider,
            model,
        )
    if provider == "cloud":
        if not api_key:
            raise RuntimeError(f"{role} is routed to a hosted provider but no API key is configured.")
        return (
            ChatOpenAI(
                model=model,
                base_url=base_url,
                api_key=api_key,
                temperature=0.2,
                max_retries=2,
            ),
            source_provider,
            model,
        )
    raise ValueError(f"Unsupported provider '{provider}' for {role}; use local or cloud.")

def chunk_text(chunk: Any) -> str:
    content = chunk.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for block in content:
            if isinstance(block, str):
                text_parts.append(block)
            elif isinstance(block, dict) and block.get("type") in {"text", "output_text"}:
                text = block.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
        return "".join(text_parts)
    return ""

def _output_rate_limit(error: Exception) -> tuple[int, int, int] | None:
    message = str(error)
    if "output tokens per minute" not in message.lower() and "otpm" not in message.lower():
        return None
    limit_match = re.search(r"\blimit\s+([\d,]+)", message, re.IGNORECASE)
    requested_match = re.search(r"\brequested\s+([\d,]+)", message, re.IGNORECASE)
    if not limit_match or not requested_match:
        return None
    limit = int(limit_match.group(1).replace(",", ""))
    requested = int(requested_match.group(1).replace(",", ""))
    if limit <= 0 or requested <= limit:
        return None
    return limit, requested, max(1, int(limit * 0.9))

def _request_rate_limit(error: Exception) -> tuple[int, int] | None:
    message = str(error)
    lowered = message.lower()
    if "output tokens per minute" in lowered or "otpm" in lowered:
        return None
    if "tokens per minute" not in lowered and not re.search(r"\btpm\b", lowered):
        return None
    limit_match = re.search(r"\blimit\s+([\d,]+)", message, re.IGNORECASE)
    requested_match = re.search(r"\brequested\s+([\d,]+)", message, re.IGNORECASE)
    if not limit_match or not requested_match:
        return None
    limit = int(limit_match.group(1).replace(",", ""))
    requested = int(requested_match.group(1).replace(",", ""))
    if limit <= 0 or requested <= limit:
        return None
    return limit, requested

async def emit_progress(
    config: RunnableConfig,
    event_type: str,
    phase: str,
    message: str,
    role: str | None = None,
):
    callback = (config.get("configurable") or {}).get("progress_callback")
    if callback:
        await callback({
            "event_type": event_type,
            "phase": phase,
            "role": role,
            "message": message,
        })

async def emit_checkpoint(
    config: RunnableConfig,
    phase: str,
    role: str,
    content: str,
    provider: str,
    model: str,
):
    callback = (config.get("configurable") or {}).get("progress_callback")
    if callback:
        await callback({
            "event_type": "checkpoint_saved",
            "phase": phase,
            "role": role,
            "message": f"{role} {phase} checkpoint saved.",
            "content": content,
            "provider": provider,
            "model": model,
        })

async def call_role(
    role: str,
    system: str,
    user: str,
    config: RunnableConfig,
    phase: str,
    output_cap: int | None = None,
):
    llm, provider, model = llm_for(role, config)
    output = []
    pending = ""
    last_emit = time.monotonic()
    messages = [("system", system), ("human", user)]
    token_limit_retries = 0
    while True:
        request_llm = llm
        if output_cap is not None:
            token_option = (
                "max_output_tokens"
                if provider == "google_gemini"
                else "max_tokens"
            )
            request_llm = llm.bind(**{token_option: output_cap})
        try:
            async for chunk in request_llm.astream(messages):
                text = chunk_text(chunk)
                if not text:
                    continue
                output.append(text)
                pending += text
                while len(pending) >= 512:
                    await emit_progress(config, "agent_output", phase, pending[:512], role)
                    pending = pending[512:]
                    last_emit = time.monotonic()
                now = time.monotonic()
                if pending and (len(pending) >= 96 or now - last_emit >= 0.6):
                    await emit_progress(config, "agent_output", phase, pending, role)
                    pending = ""
                    last_emit = now
            break
        except Exception as exc:
            rate_limit = _output_rate_limit(exc)
            if not rate_limit or output or token_limit_retries >= 2:
                raise
            limit, requested, next_cap = rate_limit
            if output_cap is not None:
                next_cap = min(next_cap, max(1, int(output_cap * 0.8)))
            output_cap = next_cap
            token_limit_retries += 1
            await emit_progress(
                config,
                "agent_started",
                phase,
                f"{provider} rejected an expected {requested:,}-token output "
                f"against its {limit:,}-token/minute limit; retrying with a "
                f"{output_cap:,}-token output cap.",
                role,
            )
    if pending:
        await emit_progress(config, "agent_output", phase, pending, role)
    return "".join(output).strip(), provider, model

def _excerpt(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text

    marker = "\n[...middle omitted to fit model context...]\n"
    if max_chars <= len(marker):
        return text[:max_chars]
    excerpt_chars = max_chars - len(marker)
    leading_chars = excerpt_chars * 2 // 3
    trailing_chars = excerpt_chars - leading_chars
    trailing_text = text[-trailing_chars:] if trailing_chars else ""
    return f"{text[:leading_chars]}{marker}{trailing_text}"


def format_evidence_register(
    evidence_records: list[dict[str, Any]],
    max_chars: int = 6000,
) -> str:
    if not evidence_records:
        return "No evidence register records are attached to this meeting."
    prefix = (
        "EVIDENCE REGISTER SNAPSHOT (search excerpts are leads, not proof; "
        "inspect the cited source):\n"
    )
    separator_chars = max(0, len(evidence_records) - 1)
    record_budget = (max_chars - len(prefix) - separator_chars) // len(evidence_records)
    if record_budget < 200:
        raise ValueError("Evidence register context budget is too small for attached records.")
    records = []
    for record in evidence_records:
        header = (
            f"- EVIDENCE-{record['id']} [{record['category']} · "
            f"{record['classification']} · {record.get('source_provider', 'manual')} · "
            f"quality {record['evidence_quality']}]"
        )
        values = {
            "Claim": record["claim"],
            "Source": " · ".join(
                str(value)
                for value in (
                    record.get("source_title"),
                    record.get("source_reference"),
                    record.get("source_url"),
                )
                if value
            ) or "Not supplied",
            "Dates": (
                f"publication {record.get('publication_date') or 'not supplied'}; "
                f"retrieved {record.get('retrieved_at') or 'not recorded'}"
            ),
            "Use": (
                f"relied on by {', '.join(record.get('relying_executives') or []) or 'none'}; "
                f"challenged {bool(record.get('challenged'))}; "
                f"disputed {bool(record.get('disputed'))}"
            ),
            "Limitations": record.get("limitations") or "Not assessed.",
        }
        empty_entry = header + "".join(f"\n  {label}: " for label in values)
        content_budget = max(0, record_budget - len(empty_entry))
        field_weights = {
            "Claim": 0.32,
            "Source": 0.34,
            "Dates": 0.10,
            "Use": 0.10,
        }
        field_budgets = {
            label: int(content_budget * weight)
            for label, weight in field_weights.items()
        }
        field_budgets["Limitations"] = content_budget - sum(field_budgets.values())
        fields = "\n".join(
            f"  {label}: {_excerpt(str(value), field_budgets[label])}"
            for label, value in values.items()
        )
        records.append(f"{header}\n{fields}")
    return prefix + "\n".join(records)


def _available_evidence_ids(state: BoardState) -> set[int]:
    return {
        int(record["id"])
        for record in state.get("evidence_register", [])
    }


def format_institutional_memory(
    memory_records: list[dict[str, Any]],
    max_chars: int = 1800,
) -> str:
    """Render a bounded recall of prior founder decisions for a prompt.

    Returns an empty string when nothing was recalled so prompts never
    carry a placeholder section for meetings with memory disabled.
    """
    if not memory_records:
        return ""
    return format_memory_context(memory_records, max_chars=max_chars)


def build_synthesis_input(state: BoardState, max_chars: int | None = None) -> str:
    title = state.get("title", "")
    agenda = state.get("agenda", "")
    founder_context = state.get("founder_context", "")
    assessments = list(state.get("assessments", {}).items())
    critiques = list(state.get("critiques", {}).items())
    revisions = list(state.get("revisions", {}).items())
    evidence_context = format_evidence_register(state.get("evidence_register", []))
    memory_context = format_institutional_memory(state.get("institutional_memory", []))
    company_text = format_company_context(state.get("company_context", {}))
    extraction = None
    if state.get("position_extraction"):
        extraction = parse_structured_output(
            state["position_extraction"],
            PositionExtraction,
        )
    elif len(state.get("assessments", {})) == len(EXECUTIVES):
        extraction = build_position_extraction(state["assessments"])

    def format_challenge(role: str, content: str) -> str:
        if extraction is None:
            return f"LEGACY UNSTRUCTURED CHALLENGE (not claim-validated):\n{content}"
        return format_targeted_cross_examination(
            content,
            role,
            extraction,
            EXECUTIVE_PROFILES[role].challenge_categories,
            _available_evidence_ids(state),
        )

    def format_input(meeting_title: str, meeting_agenda: str, context: str,
                     assessment_texts: list[str], critique_texts: list[str],
                     revision_texts: list[str], evidence_text: str,
                     memory_text: str, company_block: str) -> str:
        assessment_section = "\n\n".join(
            f"### {role}\n{text}"
            for (role, _), text in zip(assessments, assessment_texts)
        )
        challenge_section = "\n\n".join(
            f"### {role} challenge\n{text}"
            for (role, _), text in zip(critiques, critique_texts)
        )
        revision_section = "\n\n".join(
            f"### {role} position revision\n{text}"
            for (role, _), text in zip(revisions, revision_texts)
        ) or "No explicit position revisions are available; do not infer that a position was reconsidered."
        memory_section = (
            "INSTITUTIONAL MEMORY (relevant prior founder decisions and outcomes; "
            f"context, not binding authority):\n{memory_text}\n\n"
            if str(memory_text).strip()
            else ""
        )
        company_section = (
            f"{company_block}\n\n" if str(company_block).strip() else ""
        )
        return (
            f"MEETING: {meeting_title}\nAGENDA: {meeting_agenda}\n"
            f"FOUNDER CONTEXT: {context}\n\n"
            f"{company_section}"
            "EVIDENCE REGISTER SNAPSHOT (source records are not automatically proof):\n"
            f"{evidence_text}\n\n"
            f"{memory_section}"
            f"EXECUTIVE ASSESSMENTS:\n{assessment_section}\n\n"
            f"CHALLENGE ROUND:\n{challenge_section}\n\n"
            f"POSITION REVISIONS:\n{revision_section}"
        )

    full_input = format_input(
        title,
        agenda,
        founder_context,
        [assessment_for_board(text) for _, text in assessments],
        [format_challenge(role, text) for role, text in critiques],
        [revision_for_board(text) for _, text in revisions],
        evidence_context,
        memory_context,
        company_text,
    )
    if max_chars is None or len(full_input) <= max_chars:
        return full_input
    if max_chars < 512:
        raise ValueError("BOARD synthesis input budget must be at least 512 characters.")

    fixed_text_budget = max(0, max_chars // 8 - len("MEETING: \nAGENDA: \nFOUNDER CONTEXT: \n\n"))
    title_budget = min(128, fixed_text_budget // 6)
    agenda_budget = fixed_text_budget * 2 // 3
    context_budget = max(0, fixed_text_budget - title_budget - agenda_budget)
    evidence_budget = min(len(evidence_context), max_chars // 8)
    memory_budget = min(len(memory_context), max_chars // 8)
    company_budget = min(len(company_text), max_chars // 8)
    compact_memory = (
        "INSTITUTIONAL MEMORY (relevant prior founder decisions and outcomes; "
        "context, not binding authority):\n"
        f"{_excerpt(memory_context, memory_budget)}\n\n"
        if str(memory_context).strip()
        else ""
    )
    compact_company = (
        f"{_excerpt(company_text, company_budget)}\n\n"
        if str(company_text).strip()
        else ""
    )
    compact_fixed = (
        f"MEETING: {_excerpt(title, title_budget)}\n"
        f"AGENDA: {_excerpt(agenda, agenda_budget)}\n"
        f"FOUNDER CONTEXT: {_excerpt(founder_context, context_budget)}\n\n"
        f"{compact_company}"
        "EVIDENCE REGISTER SNAPSHOT (source records are not automatically proof):\n"
        f"{_excerpt(evidence_context, evidence_budget)}\n\n"
        f"{compact_memory}"
    )

    section_labels = "\n\nEXECUTIVE ASSESSMENTS:\n"
    challenge_label = "\n\nCHALLENGE ROUND:\n"
    revision_label = "\n\nPOSITION REVISIONS:\n"
    assessment_headers = [f"### {role}\n" for role, _ in assessments]
    challenge_headers = [f"### {role} challenge\n" for role, _ in critiques]
    revision_headers = [f"### {role} position revision\n" for role, _ in revisions]
    headings_size = (
        len(section_labels)
        + len(challenge_label)
        + len(revision_label)
        + sum(map(len, assessment_headers))
        + sum(map(len, challenge_headers))
        + sum(map(len, revision_headers))
    )
    body_budget = max_chars - len(compact_fixed) - headings_size
    response_count = len(assessments) + len(critiques) + len(revisions)
    per_response_budget = max(0, body_budget // max(1, response_count))
    while True:
        compact_assessments = [
            _excerpt(assessment_for_board(text), per_response_budget)
            for _, text in assessments
        ]
        compact_critiques = [
            _excerpt(format_challenge(role, text), per_response_budget)
            for role, text in critiques
        ]
        compact_revisions = [
            _excerpt(revision_for_board(text), per_response_budget)
            for _, text in revisions
        ]
        compact_input = format_input(
            _excerpt(title, title_budget),
            _excerpt(agenda, agenda_budget),
            _excerpt(founder_context, context_budget),
            compact_assessments,
            compact_critiques,
            compact_revisions,
            _excerpt(evidence_context, evidence_budget),
            _excerpt(memory_context, memory_budget),
            _excerpt(company_text, company_budget),
        )
        overflow = len(compact_input) - max_chars
        if overflow <= 0:
            return compact_input
        if per_response_budget == 0:
            raise ValueError("BOARD synthesis input budget is too small for its section headers.")
        per_response_budget = max(
            0,
            per_response_budget
            - max(1, (overflow + max(1, response_count) - 1) // max(1, response_count)),
        )

def is_context_limit_error(error: Exception) -> bool:
    context_error_phrases = (
        "context length",
        "context_length",
        "context window",
        "maximum context",
        "number of tokens to keep",
        "too many tokens",
        "prompt is too long",
    )
    current: BaseException | None = error
    messages = []
    while current is not None:
        messages.append(str(current).lower())
        current = current.__cause__ or current.__context__
    return any(phrase in message for message in messages for phrase in context_error_phrases)

async def assess(state: BoardState, config: RunnableConfig):
    settings = get_settings()
    semaphore = asyncio.Semaphore(max(1, settings.agent_concurrency))
    phase = "assessment"
    await emit_progress(config, "phase_started", phase, "Independent assessment round started.")
    assessments = dict(state.get("assessments", {}))
    metadata = dict(state.get("provider_metadata", {}))
    for role in EXECUTIVES:
        if role in assessments:
            await emit_progress(
                config, "checkpoint_reused", phase,
                f"{role} assessment restored from a saved checkpoint.", role,
            )
    memory_block = format_institutional_memory(state.get("institutional_memory", []))
    memory_section = (
        "INSTITUTIONAL MEMORY (relevant prior founder decisions and outcomes; "
        "context, not binding authority; verify applicability before relying on it):\n"
        f"{memory_block}\n\n"
        if memory_block
        else ""
    )
    company_block = format_company_context(state.get("company_context", {}))
    company_section = (
        "COMPANY CONTEXT (current mission, priorities, constraints, financial "
        "assumptions and founder-approved knowledge; treat as the operating "
        "baseline for this assessment):\n"
        f"{company_block}\n\n"
        if company_block
        else ""
    )
    user = (
        f"BOARD MEETING: {state['title']}\nAGENDA: {state['agenda']}\n"
        f"FOUNDER CONTEXT: {state.get('founder_context', '')}\n\n"
        f"{company_section}"
        "SOURCE-BACKED EVIDENCE REGISTER:\n"
        f"{format_evidence_register(state.get('evidence_register', []))}\n\n"
        f"{memory_section}"
        "Prepare your independent assessment. You have not seen other executives' views. "
        "Be explicit about assumptions and missing evidence. Search excerpts and source "
        "titles are leads, not proof; distinguish source existence from claim support."
    )
    async def run(role):
        async with semaphore:
            await emit_progress(
                config, "agent_started", phase, f"{role} started an independent assessment.", role
            )
            try:
                raw_result, provider, model = await call_role(
                    role,
                    executive_system_prompt(role, ASSESSMENT_OUTPUT_INSTRUCTIONS),
                    user,
                    config,
                    phase,
                )
                assessment = parse_structured_output(
                    raw_result,
                    ExecutiveAssessment,
                )
                validate_assessment_evidence_references(
                    assessment,
                    _available_evidence_ids(state),
                    role,
                )
                result = assessment.model_dump_json()
            except Exception as exc:
                await emit_progress(
                    config, "agent_failed", phase, f"{role} assessment failed: {exc}", role
                )
                raise
            await emit_checkpoint(config, phase, role, result, provider, model)
            await emit_progress(
                config, "agent_completed", phase, f"{role} completed its independent assessment.", role
            )
            return role, result, provider, model
    pending_roles = [role for role in EXECUTIVES if role not in assessments]
    results = await asyncio.gather(*(run(role) for role in pending_roles), return_exceptions=True)
    failures = [result for result in results if isinstance(result, BaseException)]
    if failures:
        raise failures[0]
    for role, result, provider, model in results:
        assessments[role] = result
        metadata[role] = {"provider": provider, "model": model}
    await emit_progress(config, "phase_completed", phase, "Independent assessment round completed.")
    return {"assessments": assessments, "provider_metadata": metadata}


async def extract_positions(state: BoardState, config: RunnableConfig):
    phase = "position_extraction"
    await emit_progress(
        config,
        "phase_started",
        phase,
        "Extracting and comparing validated executive positions.",
    )
    expected = build_position_extraction(state.get("assessments", {}))
    saved_content = state.get("position_extraction")
    if saved_content:
        saved = parse_structured_output(saved_content, PositionExtraction)
        if saved.model_dump() != expected.model_dump():
            raise ValueError(
                "Saved position extraction does not match the executive assessment checkpoints."
            )
        content = saved_content
        message = "Position extraction restored from its checkpoint."
    else:
        content = expected.model_dump_json()
        await emit_checkpoint(
            config,
            phase,
            "BOARD",
            content,
            "system",
            "deterministic-position-extraction-v1",
        )
        message = "Executive positions and claim references extracted."
    await emit_progress(config, "phase_completed", phase, message)
    return {"position_extraction": content}


async def challenge(state: BoardState, config: RunnableConfig):
    settings = get_settings()
    semaphore = asyncio.Semaphore(max(1, settings.agent_concurrency))
    phase = "challenge"
    await emit_progress(config, "phase_started", phase, "Executive challenge round started.")
    critiques = dict(state.get("critiques", {}))
    metadata = dict(state.get("provider_metadata", {}))
    extraction = (
        parse_structured_output(state["position_extraction"], PositionExtraction)
        if state.get("position_extraction")
        else build_position_extraction(state.get("assessments", {}))
    )
    evidence_records = state.get("evidence_register", [])
    available_evidence_ids = _available_evidence_ids(state)
    for role in EXECUTIVES:
        if role in critiques:
            parse_targeted_cross_examination(
                critiques[role],
                role,
                extraction,
                EXECUTIVE_PROFILES[role].challenge_categories,
                available_evidence_ids=available_evidence_ids,
            )
            await emit_progress(
                config, "checkpoint_reused", phase,
                f"{role} challenge restored from a saved checkpoint.", role,
            )
    async def run(role):
        docket = format_challenge_docket(
            extraction,
            role,
            EXECUTIVE_PROFILES[role].challenge_categories,
            evidence_records=evidence_records,
        )
        user = (
            f"BOARD AGENDA: {state['agenda']}\n\n"
            f"PRIORITIZED CLAIM DOCKET FOR {role}:\n{docket}\n\n"
            "Evaluate whether any cited sources actually support the target claim, "
            "including population, study design, jurisdiction, date, and product applicability. "
            "Return the evidence IDs you evaluated and separately identify any you materially dispute.\n\n"
            "The docket is derived from validated position extraction. Challenge exactly "
            "one cited claim from each other executive, selecting the most material issue "
            "within your mandate. The claim IDs are authoritative; do not invent IDs."
        )
        async with semaphore:
            await emit_progress(
                config, "agent_started", phase, f"{role} started its challenge review.", role
            )
            try:
                raw_result, provider, model = await call_role(
                    role,
                    executive_system_prompt(role, CHALLENGE_OUTPUT_INSTRUCTIONS),
                    user,
                    config,
                    phase,
                )
                examination = parse_targeted_cross_examination(
                    raw_result,
                    role,
                    extraction,
                    EXECUTIVE_PROFILES[role].challenge_categories,
                    available_evidence_ids=available_evidence_ids,
                )
                if examination is None:
                    raise ValueError(
                        "ExecutiveCrossExamination must be a validated JSON object."
                    )
                result = examination.model_dump_json()
            except Exception as exc:
                await emit_progress(
                    config, "agent_failed", phase, f"{role} challenge failed: {exc}", role
                )
                raise
            await emit_checkpoint(config, phase, role, result, provider, model)
            await emit_progress(
                config, "agent_completed", phase, f"{role} completed its challenge review.", role
            )
            return role, result, provider, model
    pending_roles = [role for role in EXECUTIVES if role not in critiques]
    results = await asyncio.gather(*(run(role) for role in pending_roles), return_exceptions=True)
    failures = [result for result in results if isinstance(result, BaseException)]
    if failures:
        raise failures[0]
    for role, result, provider, model in results:
        critiques[role] = result
        metadata[role] = {"provider": provider, "model": model}
    await emit_progress(config, "phase_completed", phase, "Executive challenge round completed.")
    return {"critiques": critiques, "provider_metadata": metadata}


async def revise_positions(state: BoardState, config: RunnableConfig):
    settings = get_settings()
    semaphore = asyncio.Semaphore(max(1, settings.agent_concurrency))
    phase = "revision"
    await emit_progress(config, "phase_started", phase, "Executive position reconsideration started.")
    revisions = dict(state.get("revisions", {}))
    metadata = dict(state.get("provider_metadata", {}))
    for role in EXECUTIVES:
        if role in revisions:
            parse_revision_for_assessment(
                revisions[role],
                state.get("assessments", {}).get(role, ""),
            )
            await emit_progress(
                config,
                "checkpoint_reused",
                phase,
                f"{role} position revision restored from a saved checkpoint.",
                role,
            )

    extraction = (
        parse_structured_output(state["position_extraction"], PositionExtraction)
        if state.get("position_extraction")
        else build_position_extraction(state.get("assessments", {}))
    )
    challenge_round = "\n\n".join(
        format_targeted_cross_examination(
            text,
            role,
            extraction,
            EXECUTIVE_PROFILES[role].challenge_categories,
            _available_evidence_ids(state),
        )
        for role, text in state.get("critiques", {}).items()
    )

    async def run(role: str):
        original_assessment = assessment_for_board(
            state.get("assessments", {}).get(role, "")
        )
        user = (
            f"BOARD AGENDA: {state.get('agenda', '')}\n\n"
            f"YOUR ORIGINAL ASSESSMENT:\n{original_assessment}\n\n"
            "SOURCE-BACKED EVIDENCE REGISTER:\n"
            f"{format_evidence_register(state.get('evidence_register', []))}\n\n"
            f"COMPLETE CHALLENGE ROUND:\n{challenge_round}\n\n"
            "Reconsider your own original position in light of the challenge arguments. "
            "State maintain, revise, or withdraw explicitly. If a legacy unstructured "
            "assessment does not state a clear previous position, choose the closest "
            "position supported by its text and explain the uncertainty."
        )
        async with semaphore:
            await emit_progress(
                config,
                "agent_started",
                phase,
                f"{role} is reconsidering its position after the challenge round.",
                role,
            )
            try:
                raw_result, provider, model = await call_role(
                    role,
                    executive_system_prompt(role, POSITION_REVISION_PROMPT),
                    user,
                    config,
                    phase,
                )
                revision = parse_revision_for_assessment(
                    raw_result,
                    state.get("assessments", {}).get(role, ""),
                )
                validate_claim_evidence_references(
                    revision.arguments_that_changed_my_view
                    + revision.remaining_disagreements,
                    _available_evidence_ids(state),
                    role,
                    "position revision",
                )
                result = revision.model_dump_json()
            except Exception as exc:
                await emit_progress(
                    config,
                    "agent_failed",
                    phase,
                    f"{role} position revision failed: {exc}",
                    role,
                )
                raise
            await emit_checkpoint(config, phase, role, result, provider, model)
            await emit_progress(
                config,
                "agent_completed",
                phase,
                f"{role} completed its position reconsideration.",
                role,
            )
            return role, result, provider, model

    pending_roles = [role for role in EXECUTIVES if role not in revisions]
    results = await asyncio.gather(*(run(role) for role in pending_roles), return_exceptions=True)
    failures = [result for result in results if isinstance(result, BaseException)]
    if failures:
        raise failures[0]
    for role, result, provider, model in results:
        revisions[role] = result
        metadata[role] = {"provider": provider, "model": model}
    await emit_progress(config, "phase_completed", phase, "Executive position reconsideration completed.")
    return {"revisions": revisions, "provider_metadata": metadata}

async def synthesize(state: BoardState, config: RunnableConfig):
    phase = "synthesis"
    await emit_progress(config, "phase_started", phase, "Pantheon synthesis started.")
    metadata = dict(state.get("provider_metadata", {}))
    if "recommendation" in state:
        await emit_progress(
            config, "checkpoint_reused", phase,
            "BOARD synthesis restored from a saved checkpoint.", "BOARD",
        )
        await emit_progress(config, "phase_completed", phase, "Pantheon synthesis completed.")
        return {
            "recommendation": state["recommendation"],
            "rationale": state.get(
                "rationale", "See the board synthesis for rationale, agreement and proposed next actions."
            ),
            "dissent": state.get(
                "dissent", "See the board synthesis for material dissent and unresolved questions."
            ),
            "provider_metadata": metadata,
        }
    await emit_progress(
        config, "agent_started", phase, "BOARD started synthesizing the council's findings.", "BOARD"
    )
    settings = get_settings()
    budget = settings.board_synthesis_max_input_chars
    output_cap = None
    tpm_retries = 0
    try:
        while True:
            user = build_synthesis_input(state, budget)
            try:
                raw_result, provider, model = await call_role(
                    "BOARD",
                    BOARD_SYNTHESIS_PROMPT,
                    user,
                    config,
                    phase,
                    output_cap=output_cap,
                )
                synthesis = parse_structured_output(raw_result, BoardSynthesis)
                validate_board_evidence_references(
                    synthesis,
                    _available_evidence_ids(state),
                )
                result = board_synthesis_markdown(synthesis)
                break
            except Exception as exc:
                current_budget = budget if budget is not None else len(user)
                context_error = is_context_limit_error(exc)
                rate_limit = _request_rate_limit(exc)
                if not context_error and not rate_limit:
                    raise
                if context_error:
                    if current_budget <= 512:
                        raise
                    budget = max(512, current_budget // 2)
                    retry_reason = "the model context limit"
                else:
                    if tpm_retries >= 4:
                        raise
                    tpm_retries += 1
                    limit, requested = rate_limit
                    if current_budget > 512:
                        reduction = min(0.75, (limit / requested) * 0.75)
                        budget = max(512, int(current_budget * reduction))
                        if budget >= current_budget:
                            budget = current_budget - 1
                    next_output_cap = max(1, int(limit * 0.2))
                    if output_cap is not None:
                        next_output_cap = min(
                            next_output_cap,
                            max(1, int(output_cap * 0.8)),
                        )
                    output_cap = next_output_cap
                    retry_reason = (
                        f"the provider TPM limit ({requested:,} requested, "
                        f"{limit:,} allowed)"
                    )
                await emit_progress(
                    config,
                    "agent_started",
                    phase,
                    f"BOARD synthesis exceeded {retry_reason}; retrying with a "
                    f"{budget:,}-character input budget"
                    + (f" and {output_cap:,}-token output cap." if output_cap else ".")
                    + f" Cause: {exc}",
                    "BOARD",
                )
    except Exception as exc:
        await emit_progress(
            config, "agent_failed", phase, f"BOARD synthesis failed: {exc}", "BOARD"
        )
        raise
    await emit_checkpoint(config, phase, "BOARD", result, provider, model)
    await emit_progress(
        config, "agent_completed", phase, "BOARD completed the Pantheon synthesis.", "BOARD"
    )
    await emit_progress(config, "phase_completed", phase, "Pantheon synthesis completed.")
    return {
        "recommendation": result,
        "rationale": synthesis.rationale,
        "dissent": board_dissent_markdown(synthesis),
        "provider_metadata": {**state.get("provider_metadata", {}), "BOARD": {"provider": provider, "model": model}},
    }

def build_board_graph():
    graph = StateGraph(BoardState)
    graph.add_node("independent_assessments", assess)
    graph.add_node("position_extraction", extract_positions)
    graph.add_node("challenge_round", challenge)
    graph.add_node("position_revisions", revise_positions)
    graph.add_node("board_synthesis", synthesize)
    graph.set_entry_point("independent_assessments")
    graph.add_edge("independent_assessments", "position_extraction")
    graph.add_edge("position_extraction", "challenge_round")
    graph.add_edge("challenge_round", "position_revisions")
    graph.add_edge("position_revisions", "board_synthesis")
    graph.add_edge("board_synthesis", END)
    return graph.compile()

board_graph = build_board_graph()
