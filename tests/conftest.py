"""Shared test configuration for running pytest from any working directory."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "model"
# `pytest` and `python -m pytest` can construct sys.path differently. Add both
# explicitly so importing the application works in local runs and CI.
for candidate in (ROOT, MODEL_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
