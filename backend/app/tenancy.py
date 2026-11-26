"""Active-company resolution for the multi-company founder workspace.

Every company-owned record carries a ``company_id``. The client selects the
active company with the ``X-Company-Id`` header. This module never creates a
company: companies are created explicitly (onboarding or the Companies view),
so deleting a company is final and cannot spawn a blank replacement on the
next request.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .auth import get_current_user
from .database import get_db
from .models import Company

COMPANY_HEADER = "X-Company-Id"


def _is_visible(company: Company, user_id: str) -> bool:
    """A company is visible to its owner, and to the first user that claims a
    legacy unowned row (adopted explicitly by header or by ``list_companies``).
    """
    return company.owner_user_id is None or company.owner_user_id == user_id


def get_active_company(
    x_company_id: int | None = Header(default=None, alias=COMPANY_HEADER),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> Company:
    user_id = user.get("sub")

    if x_company_id is not None:
        company = db.get(Company, x_company_id)
        if company is None or not _is_visible(company, user_id):
            # An explicit but stale/foreign id must fail loudly. Silently
            # falling back to another company makes the UI act on the wrong
            # workspace and hides the fact that the selection is invalid.
            raise HTTPException(404, "Company not found")
        if company.owner_user_id is None:
            company.owner_user_id = user_id
            db.commit()
        return company

    company = (
        db.query(Company)
        .filter(Company.owner_user_id == user_id)
        .order_by(Company.id.asc())
        .first()
    )
    if company is None:
        # Legacy rows created before ownership existed: adopt one only when it
        # is unambiguous. This never creates a company, so a deletion sticks.
        unowned = (
            db.query(Company)
            .filter(Company.owner_user_id.is_(None))
            .order_by(Company.id.asc())
            .all()
        )
        if len(unowned) == 1:
            company = unowned[0]
            company.owner_user_id = user_id
            db.commit()
    if company is None:
        raise HTTPException(
            404,
            "No company configured for this account. Complete onboarding first.",
        )
    return company
