"""Active-company resolution for the multi-company founder workspace.

Every company-owned record carries a ``company_id``. The client selects the
active company with the ``X-Company-Id`` header; when the header is absent the
workspace falls back to its first company so single-company clients keep
working unchanged.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .auth import get_current_user
from .company import ensure_company, seed_company_profile
from .database import get_db
from .models import Company

COMPANY_HEADER = "X-Company-Id"


def resolve_company(db: Session, company_id: int | None) -> Company:
    if company_id is None:
        return ensure_company(db)
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    return company


def get_active_company(
    x_company_id: int | None = Header(default=None, alias=COMPANY_HEADER),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> Company:
    user_id = user.get("sub")
    if x_company_id is not None:
        company = db.get(Company, x_company_id)
        if company is not None and company.owner_user_id == user_id:
            return company
        # Stale or foreign company id: fall back to the user's own company.
    return ensure_company(db, owner_user_id=user_id)


def create_company(
    db: Session,
    *,
    name: str,
    mission: str = "",
    strategic_context: str = "",
    owner: str = "Founder",
    owner_user_id: str | None = None,
    stage: str = "",
    seed: bool = False,
) -> Company:
    company = seed_company_profile(
        db,
        name=name,
        mission=mission,
        strategic_context=strategic_context,
        owner=owner,
        owner_user_id=owner_user_id,
        stage=stage,
        include_starters=seed,
    )
    return company
