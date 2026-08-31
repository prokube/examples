"""Prokube platform helpers shared across the Kubeflow examples.

These utilities abstract away logic specific to the prokube platform so that
notebooks and ``apply.py`` scripts can import them directly instead of wiring
up ``sys.path`` by hand.

Install once (editable) from the repo root::

    pip install -e .

Then import what you need::

    from pk_helpers import get_or_create_api_key, internal_predict_url
"""

from __future__ import annotations

from pk_helpers.api_key import get_or_create_api_key
from pk_helpers.kserve_url import internal_predict_url
from pk_helpers.mlflow_credentials import setup_mlflow_credentials

__all__ = [
    "get_or_create_api_key",
    "internal_predict_url",
    "setup_mlflow_credentials",
]
