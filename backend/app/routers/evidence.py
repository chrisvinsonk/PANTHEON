import asyncio
import json
import logging
import re
from datetime import date, datetime, timezone
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from ..auth import get_current_user
from ..database import get_db
from ..llm_config import (
    decrypt_api_key,
    encryption_key_ready,
    encrypt_api_key,
)
from ..models import (
    BoardMeeting,
    Company,
    EvidenceRecord,
    MeetingEvidenceLink,
    MeetingStatus,
    ResearchProviderConfig,
)
from ..schemas import (
    EvidenceRecordCreate,
    EvidenceRecordOut,
    EvidenceRecordUpdate,
    ResearchSearchOut,
    ResearchSearchRequest,
    ResearchSettingsOut,
    ResearchSourceOut,
    TavilyKeyUpdate,
)
from ..tenancy import get_active_company

logger = logging.getLogger(__name__)

evidence_router = APIRouter(
    prefix="/api/evidence",
    tags=["evidence register"],
    dependencies=[Depends(get_current_user)],
)
research_router = APIRouter(
    prefix="/api/research",
    tags=["research"],
    dependencies=[Depends(get_current_user)],
)

RESEARCH_PROVIDERS = {"pubmed", "clinicaltrials", "openfda", "tavily"}
EXECUTIVE_ROLES = {"CEO", "CFO", "CTO", "CSO"}
EVIDENCE_LIMITATIONS = (
    "Search-result metadata or excerpts are discovery leads, not proof that the linked "
    "source supports this claim. Review the source and its applicability before changing "
    "the evidence classification."
)


def _record_out(record: EvidenceRecord) -> EvidenceRecordOut:
    return EvidenceRecordOut(
        id=record.id,
        claim=record.claim,
        category=record.category,
        classification=record.classification,
        source_provider=record.source_provider,
        source_title=record.source_title,
        source_reference=record.source_reference,
        source_url=record.source_url,
        publication_date=record.publication_date,
        retrieved_at=record.retrieved_at,
        evidence_quality=record.evidence_quality,
        limitations=record.limitations,
        source_excerpt=record.source_excerpt,
        relying_executives=record.relying_executives or [],
        challenged=record.challenged,
        challenged_by=record.challenged_by or [],
        disputed=record.disputed,
        disputed_by=record.disputed_by or [],
        dispute_notes=record.dispute_notes,
        verification_note=record.verification_note,
        meeting_ids=sorted({link.meeting_id for link in record.meeting_links}),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _safe_source_url(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return ""
    from urllib.parse import urlsplit

    parsed = urlsplit(candidate)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        raise HTTPException(
            status_code=422,
            detail="Source URL must be an HTTP or HTTPS URL without embedded credentials.",
        )
    return candidate


def _replace_meeting_links(
    db: Session,
    record: EvidenceRecord,
    meeting_ids: list[int],
    company_id: int | None = None,
) -> None:
    ids = list(dict.fromkeys(meeting_ids))
    if len(ids) != len(meeting_ids):
        raise HTTPException(status_code=422, detail="Meeting IDs must be unique.")
    meeting_query = db.query(BoardMeeting).filter(BoardMeeting.id.in_(ids))
    if company_id is not None:
        meeting_query = meeting_query.filter(BoardMeeting.company_id == company_id)
    meetings = meeting_query.all() if ids else []
    if len(meetings) != len(ids):
        raise HTTPException(status_code=404, detail="One or more meetings were not found.")
    existing_ids = {link.meeting_id for link in record.meeting_links}
    if any(
        meeting.status != MeetingStatus.draft
        for meeting in meetings
        if meeting.id not in existing_ids
    ):
        raise HTTPException(
            status_code=409,
            detail="Evidence can only be attached to a draft meeting. Runs keep their original evidence snapshot.",
        )
    linked_counts = dict(
        db.query(MeetingEvidenceLink.meeting_id, func.count(MeetingEvidenceLink.id))
        .filter(MeetingEvidenceLink.meeting_id.in_(ids))
        .filter(MeetingEvidenceLink.evidence_id != record.id)
        .group_by(MeetingEvidenceLink.meeting_id)
        .all()
    ) if ids else {}
    if any(linked_counts.get(meeting_id, 0) >= 12 for meeting_id in ids):
        raise HTTPException(
            status_code=422,
            detail="A meeting can include at most 12 evidence records to keep model context bounded.",
        )
    record.meeting_links = [
        MeetingEvidenceLink(meeting_id=meeting_id, evidence=record)
        for meeting_id in ids
    ]


def _validated_record_payload(payload: dict) -> EvidenceRecordCreate:
    try:
        record = EvidenceRecordCreate.model_validate(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record.source_url = _safe_source_url(record.source_url)
    return record


@evidence_router.get("", response_model=list[EvidenceRecordOut])
def list_evidence(
    meeting_id: int | None = Query(default=None, gt=0),
    category: str | None = None,
    classification: str | None = None,
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    query = (
        db.query(EvidenceRecord)
        .options(selectinload(EvidenceRecord.meeting_links))
        .filter(EvidenceRecord.company_id == company.id)
    )
    if meeting_id is not None:
        query = query.join(MeetingEvidenceLink).filter(
            MeetingEvidenceLink.meeting_id == meeting_id
        )
    if category:
        query = query.filter(EvidenceRecord.category == category)
    if classification:
        query = query.filter(EvidenceRecord.classification == classification)
    records = query.order_by(EvidenceRecord.updated_at.desc()).limit(500).all()
    return [_record_out(record) for record in records]


@evidence_router.post("", response_model=EvidenceRecordOut, status_code=201)
def create_evidence(
    payload: EvidenceRecordCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
    company: Company = Depends(get_active_company),
):
    validated = _validated_record_payload(payload.model_dump())
    values = validated.model_dump(exclude={"meeting_ids"})
    values["source_url"] = _safe_source_url(values["source_url"])
    values["created_by"] = str(user.get("sub", ""))
    values["company_id"] = company.id
    if values["source_url"] and values["retrieved_at"] is None:
        values["retrieved_at"] = datetime.now(timezone.utc)
    record = EvidenceRecord(**values)
    db.add(record)
    db.flush()
    _replace_meeting_links(db, record, validated.meeting_ids, company.id)
    db.commit()
    db.refresh(record)
    return _record_out(record)


@evidence_router.patch("/{evidence_id}", response_model=EvidenceRecordOut)
def update_evidence(
    evidence_id: int,
    payload: EvidenceRecordUpdate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    record = (
        db.query(EvidenceRecord)
        .options(selectinload(EvidenceRecord.meeting_links))
        .filter_by(id=evidence_id, company_id=company.id)
        .first()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence record not found.")
    values = payload.model_dump(exclude_unset=True)
    meeting_ids = values.pop("meeting_ids", None)
    merged = {
        key: getattr(record, key)
        for key in EvidenceRecordCreate.model_fields
        if key != "meeting_ids"
    }
    merged.update(values)
    validated = _validated_record_payload(merged)
    for key, value in validated.model_dump(exclude={"meeting_ids"}).items():
        setattr(record, key, value)
    if meeting_ids is not None:
        existing_ids = {link.meeting_id for link in record.meeting_links}
        if existing_ids != set(meeting_ids):
            _replace_meeting_links(db, record, meeting_ids, company.id)
    db.commit()
    db.refresh(record)
    return _record_out(record)


@evidence_router.delete("/{evidence_id}", status_code=204)
def delete_evidence(
    evidence_id: int,
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    record = (
        db.query(EvidenceRecord)
        .filter_by(id=evidence_id, company_id=company.id)
        .first()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence record not found.")
    db.delete(record)
    db.commit()
    return Response(status_code=204)


@research_router.get("/settings", response_model=ResearchSettingsOut)
def get_research_settings(db: Session = Depends(get_db)):
    config = db.query(ResearchProviderConfig).filter_by(provider="tavily").first()
    return ResearchSettingsOut(
        web_search_configured=bool(config and config.encrypted_api_key),
        encryption_key_ready=encryption_key_ready(),
    )


@research_router.put("/settings/tavily", response_model=ResearchSettingsOut)
def update_tavily_settings(
    payload: TavilyKeyUpdate,
    db: Session = Depends(get_db),
):
    config = db.query(ResearchProviderConfig).filter_by(provider="tavily").first()
    if payload.clear_api_key:
        if config is not None:
            db.delete(config)
            db.commit()
        return get_research_settings(db)
    if payload.api_key is None or not payload.api_key.get_secret_value().strip():
        raise HTTPException(status_code=422, detail="Enter a Tavily API key or choose clear.")
    if not encryption_key_ready():
        raise HTTPException(
            status_code=503,
            detail="Secure research-key storage is unavailable. Configure a valid LLM_CONFIG_ENCRYPTION_KEY.",
        )
    encrypted_key = encrypt_api_key(payload.api_key.get_secret_value().strip())
    if config is None:
        config = ResearchProviderConfig(provider="tavily", encrypted_api_key=encrypted_key)
        db.add(config)
    else:
        config.encrypted_api_key = encrypted_key
    db.commit()
    return get_research_settings(db)


def _parse_pubmed_date(value: str | None) -> date | None:
    if not value:
        return None
    normalized = value.strip()
    for pattern in ("%Y %b %d", "%Y %b", "%Y"):
        try:
            return datetime.strptime(normalized, pattern).date()
        except ValueError:
            continue
    return None


async def _search_pubmed(
    client: httpx.AsyncClient,
    query: str,
    limit: int,
    retrieved_at: datetime,
) -> list[ResearchSourceOut]:
    search_response = await client.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        params={"db": "pubmed", "term": query, "retmode": "json", "retmax": limit},
    )
    search_response.raise_for_status()
    search_data = search_response.json()
    ids = search_data.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []
    summary_response = await client.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
        params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
    )
    summary_response.raise_for_status()
    summary = summary_response.json().get("result", {})
    results = []
    for pmid in ids:
        article = summary.get(pmid)
        if not article:
            continue
        doi = next(
            (
                item.get("value", "")
                for item in article.get("articleids", [])
                if item.get("idtype") == "doi"
            ),
            "",
        )
        results.append(ResearchSourceOut(
            provider="pubmed",
            title=article.get("title", "Untitled PubMed record").rstrip("."),
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            source_reference=f"PMID:{pmid}" + (f" · DOI:{doi}" if doi else ""),
            publication_date=_parse_pubmed_date(article.get("pubdate")),
            retrieved_at=retrieved_at,
            excerpt=(
                f"{article.get('fulljournalname') or article.get('source') or 'PubMed'}"
                + (f" · {article.get('pubdate')}" if article.get("pubdate") else "")
            ),
            limitations=EVIDENCE_LIMITATIONS,
        ))
    return results


async def _search_clinical_trials(
    client: httpx.AsyncClient,
    query: str,
    limit: int,
    retrieved_at: datetime,
) -> list[ResearchSourceOut]:
    response = await client.get(
        "https://clinicaltrials.gov/api/v2/studies",
        params={"query.term": query, "format": "json", "pageSize": limit},
    )
    response.raise_for_status()
    data = response.json()
    results = []
    for study in data.get("studies", []):
        protocol = study.get("protocolSection", {})
        identification = protocol.get("identificationModule", {})
        status = protocol.get("statusModule", {})
        nct_id = identification.get("nctId")
        if not nct_id:
            continue
        first_posted = status.get("studyFirstPostDateStruct", {}).get("date")
        try:
            published = date.fromisoformat(first_posted) if first_posted else None
        except ValueError:
            published = None
        results.append(ResearchSourceOut(
            provider="clinicaltrials",
            title=identification.get("briefTitle", nct_id),
            url=f"https://clinicaltrials.gov/study/{nct_id}",
            source_reference=nct_id,
            publication_date=published,
            retrieved_at=retrieved_at,
            excerpt=(
                f"Registry first posted: {first_posted or 'not stated'}. "
                f"Study status: {status.get('overallStatus', 'not stated')}."
            ),
            limitations=(
                "Registry entries describe study records, not proof of efficacy or "
                "independent validation. " + EVIDENCE_LIMITATIONS
            ),
        ))
    return results


async def _search_openfda(
    client: httpx.AsyncClient,
    query: str,
    limit: int,
    retrieved_at: datetime,
) -> list[ResearchSourceOut]:
    term = re.sub(r"[^a-zA-Z0-9 -]", " ", query).strip()
    if not term:
        return []
    response = await client.get(
        "https://api.fda.gov/device/510k.json",
        params={
            "search": f'device_name:"{term}"',
            "limit": limit,
        },
    )
    if response.status_code == 404:
        return []
    response.raise_for_status()
    data = response.json()
    results = []
    for item in data.get("results", []):
        k_number = item.get("k_number")
        if not k_number:
            continue
        decision_date = item.get("decision_date")
        try:
            published = datetime.strptime(decision_date, "%Y%m%d").date() if decision_date else None
        except ValueError:
            published = None
        results.append(ResearchSourceOut(
            provider="openfda",
            title=item.get("device_name", k_number),
            url=(
                "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm"
                f"?ID={quote(k_number)}"
            ),
            source_reference=f"FDA 510(k): {k_number}",
            publication_date=published,
            retrieved_at=retrieved_at,
            excerpt=item.get("decision_description", ""),
            limitations=(
                "A 510(k) database entry applies only to its specific device and "
                "regulatory record; it does not determine another product's pathway. "
                + EVIDENCE_LIMITATIONS
            ),
        ))
    return results


async def _search_tavily(
    client: httpx.AsyncClient,
    query: str,
    limit: int,
    retrieved_at: datetime,
    api_key: str,
) -> list[ResearchSourceOut]:
    response = await client.post(
        "https://api.tavily.com/search",
        json={
            "api_key": api_key,
            "query": query,
            "topic": "general",
            "search_depth": "advanced",
            "max_results": limit,
            "include_answer": False,
        },
    )
    response.raise_for_status()
    data = response.json()
    return [
        ResearchSourceOut(
            provider="tavily",
            title=item.get("title") or item.get("url") or "Untitled web result",
            url=item.get("url", ""),
            publication_date=None,
            retrieved_at=retrieved_at,
            excerpt=(item.get("content") or "")[:1200],
            limitations=EVIDENCE_LIMITATIONS,
        )
        for item in data.get("results", [])
        if item.get("url", "").startswith(("https://", "http://"))
    ]


@research_router.post("/search", response_model=ResearchSearchOut)
async def search_research_sources(
    payload: ResearchSearchRequest,
    db: Session = Depends(get_db),
):
    retrieved_at = datetime.now(timezone.utc)
    provider_config = db.query(ResearchProviderConfig).filter_by(provider="tavily").first()
    tavily_key = (
        decrypt_api_key(provider_config.encrypted_api_key)
        if provider_config is not None
        else ""
    )
    web_search_configured = bool(tavily_key)
    warnings = []
    selected = list(dict.fromkeys(payload.providers))
    if "tavily" in selected and not tavily_key:
        warnings.append("Web search is not configured. Add a Tavily key in Research settings.")
        selected.remove("tavily")

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
        searches = []
        for provider in selected:
            if provider == "pubmed":
                searches.append(("PubMed", _search_pubmed(client, payload.query, payload.limit_per_provider, retrieved_at)))
            elif provider == "clinicaltrials":
                searches.append(("ClinicalTrials.gov", _search_clinical_trials(client, payload.query, payload.limit_per_provider, retrieved_at)))
            elif provider == "openfda":
                searches.append(("openFDA", _search_openfda(client, payload.query, payload.limit_per_provider, retrieved_at)))
            elif provider == "tavily":
                searches.append(("Tavily web search", _search_tavily(
                    client, payload.query, payload.limit_per_provider, retrieved_at, tavily_key
                )))
        outcomes = await asyncio.gather(
            *(search for _, search in searches),
            return_exceptions=True,
        )

    results = []
    for (provider_name, _), outcome in zip(searches, outcomes):
        if isinstance(outcome, Exception):
            if isinstance(outcome, (httpx.HTTPError, json.JSONDecodeError, ValueError, KeyError)):
                warnings.append(f"{provider_name} search failed: {outcome}")
            else:
                raise outcome
        else:
            results.extend(outcome)
    if not results and warnings:
        raise HTTPException(
            status_code=502,
            detail="Research search failed. " + " ".join(warnings),
        )
    return ResearchSearchOut(
        query=payload.query,
        results=results,
        warnings=warnings,
        web_search_configured=web_search_configured,
    )
