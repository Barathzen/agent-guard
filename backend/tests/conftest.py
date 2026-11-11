import sys
from pathlib import Path

# Ensure project root (agent-guard/) is importable as package context for `backend.*`
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
