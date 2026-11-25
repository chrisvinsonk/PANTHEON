from uuid import uuid4

from sqlalchemy.orm import Session
from .company import (
    DEFAULT_COMPANY,
    STARTER_ASSUMPTIONS,
    STARTER_CONSTRAINTS,
    STARTER_PRIORITIES,
)
from .models import Company, Executive
from .agents.prompts import EXECUTIVES


def _with_ids(items: list[dict]) -> list[dict]:
    return [{"id": uuid4().hex[:8], **item} for item in items]


def seed_defaults(db: Session):
    company = db.query(Company).first()
    if not company:
        db.add(Company(
            name=DEFAULT_COMPANY["name"],
            mission=DEFAULT_COMPANY["mission"],
            strategic_context=DEFAULT_COMPANY["strategic_context"],
            owner=DEFAULT_COMPANY["owner"],
            stage=DEFAULT_COMPANY["stage"],
            strategic_priorities=_with_ids(STARTER_PRIORITIES),
            constraints=_with_ids(STARTER_CONSTRAINTS),
            financial_assumptions=_with_ids(STARTER_ASSUMPTIONS),
            approved_knowledge=[],
        ))
    elif company.name == DEFAULT_COMPANY["name"]:
        # Guarded starter backfill: only the seeded default company, and only
        # while every context list is still empty, so founder edits are never
        # overwritten.
        changed = False
        if not company.owner:
            company.owner = DEFAULT_COMPANY["owner"]
            changed = True
        if not company.stage:
            company.stage = DEFAULT_COMPANY["stage"]
            changed = True
        if not (
            company.strategic_priorities
            or company.constraints
            or company.financial_assumptions
            or company.approved_knowledge
        ):
            company.strategic_priorities = _with_ids(STARTER_PRIORITIES)
            company.constraints = _with_ids(STARTER_CONSTRAINTS)
            company.financial_assumptions = _with_ids(STARTER_ASSUMPTIONS)
            changed = True
        if changed:
            db.commit()
    for role, data in EXECUTIVES.items():
        if not db.query(Executive).filter_by(role=role).first():
            db.add(Executive(role=role, title=data["title"], mandate=data["mandate"], system_instruction=data["prompt"]))
    db.commit()
