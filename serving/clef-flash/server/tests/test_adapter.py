from pathlib import Path

import pytest

from clef_server.adapter import ClefAdapter


def test_adapter_loads_released_joint_schema_interface(tmp_path: Path) -> None:
    (tmp_path / "joint_schema_model.py").write_text(
        """
from dataclasses import dataclass

@dataclass(frozen=True)
class Marker:
    value: str

def load_release_model(path, device):
    return Marker(f"{path}:{device}"), "processor"

def systemone(model, processor, request):
    return {
        "model": request["model"],
        "answers": {},
        "usage": {"input_tokens": 1, "output_tokens": 0},
    }
"""
    )

    adapter = ClefAdapter.load(tmp_path, "test-device")
    result = adapter.decide({"model": "clef-flash", "state": "test", "questions": {}})

    assert result["model"] == "clef-flash"
    assert result["usage"] == {"input_tokens": 1, "output_tokens": 0}


def test_adapter_rejects_missing_model_directory(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="directory does not exist"):
        ClefAdapter.load(tmp_path / "missing", "cuda")


def test_adapter_rejects_missing_joint_schema_module(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="joint schema module is missing"):
        ClefAdapter.load(tmp_path, "cuda")
