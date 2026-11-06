# This file is intentionally minimal and acts as a scaffold for future implementation.
# It does not claim a trained model or verified runtime.

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def project_root() -> Path:
    return ROOT


def status() -> str:
    return "PLANNED" 
