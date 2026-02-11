from pathlib import Path
import sys
import pytest
import os

# Ensure the repository root (one level up from tests/) is on sys.path so tests can import `src`
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

@pytest.fixture(scope="session", autouse=True)
def ensure_clean_deliveries_db():
    """
    Ensure tests start with a clean deliveries DB. This deletes the data/deliveries.db file
    if it exists in the repo workspace. Only intended for dev/test environments.
    """
    db_path = Path(REPO_ROOT) / "data" / "deliveries.db"
    if db_path.exists():
        try:
            db_path.unlink()
            print(f"Removed existing test DB: {db_path}")
        except Exception as exc:
            # If unlink fails, attempt to delete rows instead
            try:
                import sqlite3
                conn = sqlite3.connect(str(db_path))
                cur = conn.cursor()
                cur.execute("DELETE FROM deliveries;")
                conn.commit()
                conn.close()
                print(f"Cleared deliveries table in DB: {db_path}")
            except Exception as exc2:
                # don't fail collection for interesting reasons, surface both errors
                raise RuntimeError(f"Failed to remove or clear test DB: {exc}; {exc2}")
    yield
    # optional: cleanup after tests (commented out)
    # if db_path.exists():
    #     db_path.unlink()
