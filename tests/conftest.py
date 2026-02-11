from pathlib import Path
import sys

# Ensure the repository root (one level up from tests/) is on sys.path so tests can import `src`
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
