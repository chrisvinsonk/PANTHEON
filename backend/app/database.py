from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import get_settings

class Base(DeclarativeBase):
    pass

settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def ensure_database_compatibility(bind: Engine = engine) -> None:
    inspector = inspect(bind)
    table_names = inspector.get_table_names()
    with bind.begin() as connection:
        if "evidence_records" in table_names:
            columns = {column["name"] for column in inspector.get_columns("evidence_records")}
            compatibility_columns = {
                "source_provider": "VARCHAR(32) NOT NULL DEFAULT 'manual'",
                "challenged_by": "JSON NOT NULL DEFAULT '[]'",
                "disputed_by": "JSON NOT NULL DEFAULT '[]'",
            }
            for name, definition in compatibility_columns.items():
                if name not in columns:
                    connection.execute(text(
                        f"ALTER TABLE evidence_records ADD COLUMN {name} {definition}"
                    ))
        if "board_meetings" in table_names:
            columns = {column["name"] for column in inspector.get_columns("board_meetings")}
            if "include_memory" not in columns:
                connection.execute(text(
                    "ALTER TABLE board_meetings ADD COLUMN include_memory BOOLEAN NOT NULL DEFAULT 1"
                ))
        if "companies" in table_names:
            columns = {column["name"] for column in inspector.get_columns("companies")}
            compatibility_columns = {
                "owner": "VARCHAR(160) NOT NULL DEFAULT ''",
                "owner_user_id": "VARCHAR(128)",
                "onboarded": "BOOLEAN NOT NULL DEFAULT 0",
                "stage": "VARCHAR(40) NOT NULL DEFAULT ''",
                "strategic_priorities": "JSON NOT NULL DEFAULT '[]'",
                "constraints": "JSON NOT NULL DEFAULT '[]'",
                "financial_assumptions": "JSON NOT NULL DEFAULT '[]'",
                "approved_knowledge": "JSON NOT NULL DEFAULT '[]'",
                "updated_at": "DATETIME",
            }
            for name, definition in compatibility_columns.items():
                if name not in columns:
                    connection.execute(text(
                        f"ALTER TABLE companies ADD COLUMN {name} {definition}"
                    ))

        # Multi-company scoping: every company-owned record carries its company.
        for table in (
            "board_meetings",
            "evidence_records",
            "decision_records",
            "executive_feedback",
            "operational_artifacts",
        ):
            if table not in table_names:
                continue
            columns = {column["name"] for column in inspector.get_columns(table)}
            if "company_id" not in columns:
                connection.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN company_id INTEGER REFERENCES companies(id)"
                ))


def backfill_company_scope(bind: Engine = engine, company_id: int | None = None) -> None:
    """Attach legacy rows to a company so scoped queries never hide existing data."""
    if company_id is None:
        return
    with bind.begin() as connection:
        for table in (
            "board_meetings",
            "evidence_records",
            "decision_records",
            "executive_feedback",
            "operational_artifacts",
        ):
            connection.execute(
                text(f"UPDATE {table} SET company_id = :company_id WHERE company_id IS NULL"),
                {"company_id": company_id},
            )

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
