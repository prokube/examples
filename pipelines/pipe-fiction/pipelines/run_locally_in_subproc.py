from kfp import local
from pipeline import example_pipeline

local.init(runner=local.SubprocessRunner(use_venv=False))

result = example_pipeline()

