"""Application package compatibility for root and backend-directory launches."""

from pathlib import Path
import sys

repository_root = Path(__file__).resolve().parents[2]
if str(repository_root) not in sys.path:
    sys.path.insert(0, str(repository_root))
