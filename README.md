# examples
prokube.ai platform examples — Notebooks, Pipelines, Serving, Experiment Tracking, Hyperparameter Tuning, and more

For full platform documentation, see [docs.prokube.ai](https://docs.prokube.ai/).

## Brief description
```py
.
├── .github          # workflows to build images
├── hparam-tuning    # hyperparameter tuning examples (Katib)
├── images           # custom container images used by examples
├── mlflow           # MLflow experiment tracking examples
├── notebooks        # Jupyter notebook examples (Dask, MNIST VAE, etc.)
├── pipelines        # Kubeflow Pipelines examples
├── rstudio          # RStudio examples
├── serving          # model serving examples (KServe, vLLM, shadow deployments)
```

## Note about storage
Storage on Kubernetes is a complex topic and a deep dive is outside the scope of this repository. There are two types
of storage you might encounter here — block and object storage.

### Block storage
The usual type of storage a Kubernetes pod might mount to persist data. An example in the context of this repo are
notebook volumes.

### Object storage
Object storage is any S3-like type of storage. Pipelines use object storage
extensively to store intermediate and final task/pipeline artifacts. Furthermore, KServe can be configured
to serve models directly from object storage.

prokube.ai comes pre-configured with integrated object storage. Alternatively, admins can configure pipelines
to use other instances of object storage (e.g. self-hosted MinIO, AWS S3, GCS, etc.).
Many S3 libraries use environment variables for their configuration — those are usually:
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `S3_ENDPOINT`. They are likely already
available in your environment. You can also ask your admin about them.

## Platform compatibility

Some examples require a minimum prokube platform version. If an example is not listed, no specific version requirement is known.

| Example | Min platform version | Notes |
|---|---|---|
| `serving/minimal-s3-model` | v1.7.0 | Requires s3creds secret with KServe support |

## Contributing
All code contributions should go via pull requests. Make sure your code is clearly documented and that it adheres
to established standards (e.g. PEP).

### Jupyter notebooks
Since this repo contains Jupyter notebooks we use [nbstripout](https://github.com/kynan/nbstripout) as
[pre-commit](https://pre-commit.com/) hook so all notebooks are stripped of cell outputs. Set it up locally for
yourself with:
```shell
pip install --upgrade nbstripout
pip install pre-commit
pre-commit install
```
This should enable the hooks.
Use `pre-commit run --all-files` to run the hooks.
