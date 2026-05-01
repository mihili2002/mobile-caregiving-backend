"""Utility helpers for ML training (logging, saving artifacts)."""
from pathlib import Path


def ensure_dir(path: str):
    Path(path).mkdir(parents=True, exist_ok=True)
