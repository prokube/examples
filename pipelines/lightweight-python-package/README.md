# Containerized Components Example

This example demonstrates how to use lightweight components with a custom base image that contains
your Python package pre-installed. This approach combines the best of both worlds:

- **Fast startup**: No `pip install` at runtime since dependencies are baked into the image
- **Clean code**: Business logic lives in a proper Python package, separate from pipeline wiring
- **Reusability**: The same functions can be used outside of Kubeflow Pipelines
- **Simple components**: Lightweight component decorators handle artifact I/O automatically

## Project Structure

```
lightweight-python-package/
├── src/
│   └── mobile_price_classification/   # Python package with business logic
│       ├── __init__.py
│       ├── read_data.py
│       ├── split_data.py
│       ├── fit_scaler.py
│       ├── tune_hyperparams.py
│       ├── train_model.py
│       ├── evaluate_model.py
│       └── test_model.py
├── Dockerfile                         # Builds image with package installed
├── pyproject.toml                     # Package configuration
├── pipeline.py                        # Pipeline definition using base_image
└── submit-cluster.py                  # Submit from within cluster
```

## How It Works

Instead of defining all code inline in the component decorator:

```python
@dsl.component(
    packages_to_install=["pandas", "scikit-learn"],
    base_image="python:3.9",
)
def train_model(...):
    # All the code here...
```

We use a custom base image with our package pre-installed:

```python
COMPONENTS_IMAGE = "<your-registry>/mobile-price-classification:v1"

@dsl.component(base_image=COMPONENTS_IMAGE)
def train_model(train_x: Input[Dataset], ...):
    from mobile_price_classification import train_model as _train_model
    _train_model(train_x.path, ...)
```

## Getting Started

### 1. Build and Push the Docker Image

```sh
# Build the image (use --platform linux/amd64 when building on ARM Macs)
docker build --platform linux/amd64 -t <your-registry>/mobile-price-classification:v1 .

# Push to your registry
docker push <your-registry>/mobile-price-classification:v1
```

### 2. Update the Image Reference

Edit `pipeline.py` and update `COMPONENTS_IMAGE` to point to your registry:

```python
COMPONENTS_IMAGE = "<your-registry>/mobile-price-classification:v1"
```

### 3. Prepare the Dataset

Follow the same dataset preparation steps as in the lightweight components example:
1. Download the dataset from Kaggle
2. Upload to your default MinIO bucket (`<namespace>-data`)

### 4. Run the Pipeline

**From within the cluster (e.g., from a Kubeflow Notebook):**

```sh
python submit-cluster.py
```

## Comparison with Other Approaches

| Approach               | Startup Time       | Code Organization   | Artifact Handling | Classes, imports, etc. |
|------------------------|--------------------|---------------------|-------------------|------------------------|
| Lightweight Components | Slow (pip install) | Inline in decorator | Automatic         | No                     |
| Container Components   | Fast               | Separate scripts    | Manual            | Yes                    |
| **This Approach**      | Fast               | Proper package      | Automatic         | Yes                    |

## When to Use This Pattern

- When you want to use proper Python code organization (classes, multiple files, imports between modules) - lightweight components require everything to be defined inline within the function
- When you have reusable ML code that you want to use both inside and outside of pipelines
- When startup time matters (large dependencies like TensorFlow, PyTorch)
- When you want clean separation between business logic and pipeline orchestration
- When you're working in a team and want proper package structure with tests
