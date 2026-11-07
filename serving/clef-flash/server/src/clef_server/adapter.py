import importlib.util
import os
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast


class DecisionAdapter(Protocol):
    model_name: str

    def decide(self, request: dict[str, object]) -> dict[str, object]: ...


SystemOne = Callable[[object, object, dict[str, object]], dict[str, object]]


class ClefAdapter:
    model_name = "clef-flash"

    def __init__(
        self,
        model: object,
        processor: object,
        systemone: SystemOne,
    ) -> None:
        self._model = model
        self._processor = processor
        self._systemone = systemone

    @classmethod
    def from_environment(cls) -> "ClefAdapter":
        path = Path(os.environ.get("MODEL_PATH", "/mnt/models/clef-flash"))
        device = os.environ.get("MODEL_DEVICE", "cuda")
        return cls.load(path, device)

    @classmethod
    def load(cls, path: Path, device: str) -> "ClefAdapter":
        if not path.is_dir():
            raise RuntimeError("CLEF model directory does not exist")

        module_path = path / "joint_schema_model.py"
        if not module_path.is_file():
            raise RuntimeError("CLEF joint schema module is missing")

        module = _load_module(module_path)
        loader = getattr(module, "load_release_model", None)
        systemone = getattr(module, "systemone", None)
        if not callable(loader) or not callable(systemone):
            raise RuntimeError("CLEF joint schema module has an invalid interface")

        model, processor = loader(path, device=device)
        return cls(model, processor, cast(SystemOne, systemone))

    def decide(self, request: dict[str, object]) -> dict[str, object]:
        return self._systemone(self._model, self._processor, request)


def _load_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("clef_joint_schema_model", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load CLEF joint schema module")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    return module
