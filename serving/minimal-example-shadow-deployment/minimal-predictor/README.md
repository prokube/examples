# Minimal predictor This custom predictor is a simple kserve predictor that multiplies all `values` from a
request with a factor. The factor can be defined through environment variables. 


## Run/Debug locally

First export all required environment variables. 

```bash 
export MODEL_NAME=model
export FACTOR=2
```

Run/debug the main.py
