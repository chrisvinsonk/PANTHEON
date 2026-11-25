"""Programme 4 — Founder workspace company context and configuration."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..company import (
    add_assumption,
    add_constraint,
    add_knowledge,
    add_priority,
    company_status,
    delete_assumption,
    delete_constraint,
    delete_knowledge,
    delete_priority,
    governance_snapshot,
    serialize_company,
    touch,
    update_assumption,
    update_constraint,
    update_knowledge,
    update_priority,
)
from ..database import get_db
from ..models import Company, EvidenceRecord
from ..schemas import (
    CompanyConstraintIn,
    CompanyConstraintOut,
    CompanyConstraintUpdate,
    CompanyContextOut,
    CompanyFinancialAssumptionIn,
    CompanyFinancialAssumptionOut,
    CompanyFinancialAssumptionUpdate,
    CompanyKnowledgeIn,
    CompanyKnowledgeOut,
    CompanyKnowledgeUpdate,
    CompanyOut,
    CompanyPriorityIn,
    CompanyPriorityOut,
    CompanyPriorityUpdate,
    CompanyUpdate,
    GovernanceOut,
)
from ..tenancy import get_active_company

router = APIRouter(
    prefix="/api/company",
    tags=["company workspace"],
    dependencies=[Depends(get_current_user)],
)


def _out(company) -> CompanyOut:
    return CompanyOut.model_validate(serialize_company(company))


def _item_out(schema, item: dict):
    return schema.model_validate(item)


@router.get("", response_model=CompanyOut)
def get_company(
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    return _out(company)


@router.patch("", response_model=CompanyOut)
def update_company(
    payload: CompanyUpdate, db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    touch(company)
    db.commit()
    db.refresh(company)
    return _out(company)


@router.get("/context", response_model=CompanyContextOut)
def get_company_context(
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    return CompanyContextOut.model_validate(company_status(db, company))


@router.get("/governance", response_model=GovernanceOut)
def get_governance(
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    return GovernanceOut.model_validate(governance_snapshot(db, company.id))


# ---------------------------------------------------------------------------
# Strategic priorities
# ---------------------------------------------------------------------------


@router.post("/priorities", response_model=CompanyPriorityOut, status_code=201)
def create_priority(
    payload: CompanyPriorityIn, db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    item = add_priority(company, payload)
    db.commit()
    return _item_out(CompanyPriorityOut, item)


@router.patch("/priorities/{item_id}", response_model=CompanyPriorityOut)
def patch_priority(
    item_id: str,
    payload: CompanyPriorityUpdate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    item = update_priority(company, item_id, payload)
    if item is None:
        raise HTTPException(404, "Priority not found")
    db.commit()
    return _item_out(CompanyPriorityOut, item)


@router.delete("/priorities/{item_id}", status_code=204)
def remove_priority(
    item_id: str, db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    if not delete_priority(company, item_id):
        raise HTTPException(404, "Priority not found")
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------


@router.post("/constraints", response_model=CompanyConstraintOut, status_code=201)
def create_constraint(
    payload: CompanyConstraintIn, db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    item = add_constraint(company, payload)
    db.commit()
    return _item_out(CompanyConstraintOut, item)


@router.patch("/constraints/{item_id}", response_model=CompanyConstraintOut)
def patch_constraint(
    item_id: str,
    payload: CompanyConstraintUpdate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    item = update_constraint(company, item_id, payload)
    if item is None:
        raise HTTPException(404, "Constraint not found")
    db.commit()
    return _item_out(CompanyConstraintOut, item)


@router.delete("/constraints/{item_id}", status_code=204)
def remove_constraint(
    item_id: str, db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    if not delete_constraint(company, item_id):
        raise HTTPException(404, "Constraint not found")
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Financial assumptions
# ---------------------------------------------------------------------------


@router.post(
    "/financial-assumptions",
    response_model=CompanyFinancialAssumptionOut,
    status_code=201,
)
def create_assumption(
    payload: CompanyFinancialAssumptionIn,
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    item = add_assumption(company, payload)
    db.commit()
    return _item_out(CompanyFinancialAssumptionOut, item)


@router.patch(
    "/financial-assumptions/{item_id}",
    response_model=CompanyFinancialAssumptionOut,
)
def patch_assumption(
    item_id: str,
    payload: CompanyFinancialAssumptionUpdate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    item = update_assumption(company, item_id, payload)
    if item is None:
        raise HTTPException(404, "Financial assumption not found")
    db.commit()
    return _item_out(CompanyFinancialAssumptionOut, item)


@router.delete("/financial-assumptions/{item_id}", status_code=204)
def remove_assumption(
    item_id: str, db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    if not delete_assumption(company, item_id):
        raise HTTPException(404, "Financial assumption not found")
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Approved knowledge
# ---------------------------------------------------------------------------


@router.post("/knowledge", response_model=CompanyKnowledgeOut, status_code=201)
def create_knowledge(
    payload: CompanyKnowledgeIn, db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    if payload.evidence_id is not None:
        evidence = db.get(EvidenceRecord, payload.evidence_id)
        if evidence is None:
            raise HTTPException(404, "Evidence record not found")
    item = add_knowledge(company, payload)
    db.commit()
    return _item_out(CompanyKnowledgeOut, item)


@router.patch("/knowledge/{item_id}", response_model=CompanyKnowledgeOut)
def patch_knowledge(
    item_id: str,
    payload: CompanyKnowledgeUpdate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    if payload.evidence_id is not None:
        evidence = db.get(EvidenceRecord, payload.evidence_id)
        if evidence is None:
            raise HTTPException(404, "Evidence record not found")
    item = update_knowledge(company, item_id, payload)
    if item is None:
        raise HTTPException(404, "Knowledge entry not found")
    db.commit()
    return _item_out(CompanyKnowledgeOut, item)


@router.delete("/knowledge/{item_id}", status_code=204)
def remove_knowledge(
    item_id: str, db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    if not delete_knowledge(company, item_id):
        raise HTTPException(404, "Knowledge entry not found")
    db.commit()
    return Response(status_code=204)
