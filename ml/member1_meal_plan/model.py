"""Model definition for vitals prediction.

This file contains a small example model definition used during training.
"""
from sklearn.ensemble import RandomForestRegressor


def build_model():
    return RandomForestRegressor(n_estimators=10)
