import datetime
from kfp.client import Client
from kfp import compiler
from pipeline import container_components_pipeline


if __name__ == "__main__":
    client = Client()

    compiler.Compiler().compile(container_components_pipeline, "pipeline.yaml")

    run = client.create_run_from_pipeline_package(
        "pipeline.yaml",
        enable_caching=False,
        arguments={"input1": "Hello", "input2": "world!"},
        experiment_name="minimal-container-components-experiment",
        run_name=f"Simple pipeline {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    )
    print(f"KFP_RUN_ID={run.run_id}")
