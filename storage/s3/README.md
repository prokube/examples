# S3 Object Storage Access

These examples show how to write and read the Iris dataset from prokube.ai's integrated S3 object storage.
You only need to set the bucket name in the example.

## Python

Open `python/s3_access.ipynb` in a pk notebook.

The notebook uses the platform configuration directly:

```python
import s3fs

s3 = s3fs.S3FileSystem()

with s3.open("<bucketname>/<objectname>", "rb") as f:
    print(f.read())
```

## R

Run `r/s3_access.R` in pk RStudio.

The R example uses `aws.s3`. It sets `use_https = FALSE` because this example is for the preconfigured internal MinIO endpoint, where cluster traffic is protected by the platform. Do not use `use_https = FALSE` for external S3 endpoints.
