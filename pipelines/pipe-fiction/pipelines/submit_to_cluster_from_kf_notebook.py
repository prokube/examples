from kfp.client import Client
from pipeline import example_pipeline

client = Client()

run = client.create_run_from_pipeline_func(
    example_pipeline,
)
