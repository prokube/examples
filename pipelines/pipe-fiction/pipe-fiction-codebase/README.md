# Pipe Fiction Codebase

A simple Python package demonstrating ML code organization for KFP (Kubeflow Pipelines) development.

## Package Structure

```
pipe_fiction/
├── data_generator.py    # Generate sample text data
└── data_processor.py    # Process and analyze text data
```

## Installation

Install dependencies and the package in development mode:

```bash
uv sync
source .venv/bin/activate
```

## Usage Example

```python
from pipe_fiction.data_generator import DataGenerator
from pipe_fiction.data_processor import DataProcessor

# Generate sample data
generator = DataGenerator()
lines = generator.create_sample_data()

# Process the data
processor = DataProcessor()
processed_data = processor.process_lines(lines)
summary = processor.get_summary(processed_data)

print(f"Processed {summary['total_lines']} lines with {summary['total_words']} words")
```

## Docker Image

Build the Docker image with the package pre-installed:

```bash
docker buildx build --platform linux/amd64 \
  -t <your-registry>/pipe-fiction:latest .
```

This image can then be used as the `base_image` in KFP components, allowing them to import from `pipe_fiction` without code duplication.
