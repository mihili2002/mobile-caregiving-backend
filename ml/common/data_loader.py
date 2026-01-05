"""Shared data loading utilities for ML training code."""
from pathlib import Path
import pandas as pd


def load_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(Path(path))
