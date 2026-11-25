import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, text

from app.database import ensure_database_compatibility


class DatabaseCompatibilityTests(unittest.TestCase):
    def test_existing_evidence_table_gets_missing_columns_without_losing_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = create_engine(f"sqlite:///{Path(temp_dir) / 'legacy.db'}")
            try:
                with engine.begin() as connection:
                    connection.execute(text(
                        "CREATE TABLE evidence_records ("
                        "id INTEGER PRIMARY KEY, claim TEXT NOT NULL)"
                    ))
                    connection.execute(text(
                        "INSERT INTO evidence_records (id, claim) "
                        "VALUES (1, 'Existing evidence claim')"
                    ))

                ensure_database_compatibility(engine)
                ensure_database_compatibility(engine)

                with engine.connect() as connection:
                    row = connection.execute(text(
                        "SELECT claim, source_provider, challenged_by, disputed_by "
                        "FROM evidence_records WHERE id = 1"
                    )).one()
                self.assertEqual(row.claim, "Existing evidence claim")
                self.assertEqual(row.source_provider, "manual")
                self.assertEqual(row.challenged_by, "[]")
                self.assertEqual(row.disputed_by, "[]")
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
