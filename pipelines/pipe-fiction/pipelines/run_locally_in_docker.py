from kfp import local
from pipeline import example_pipeline
from utils import kfp_docker_monkey_patches

local.init(
    runner=local.DockerRunner(
        ports={"5678/tcp": 5678},
        environment={
            "KFP_DEBUG": "true",
        },
    )
)


result = example_pipeline()
