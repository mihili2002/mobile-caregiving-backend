"""Common preprocessing helpers used by ML team members."""
import numpy as np


def normalize_array(x):
    x = np.array(x, dtype=float)
    return (x - x.mean()) / (x.std() + 1e-8)
