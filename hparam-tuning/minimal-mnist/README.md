# Minimal Katib Example Using scikit-learn and MNIST

This example demonstrates the use of Katib for hyperparameter tuning with a 
simple scikit-learn model trained on the MNIST dataset.

## Steps
Generally, the following four steps are required to run a hyperparameter tuning 
experiment using custom training code. However, Steps 1 and 2 are covered in 
the corresponding image directory `./images/minimal-mnist/`:
1. Write the training code.
2. Create a Dockerfile for the training environment.
3. Build the training image.
4. Define the experiment YAML file for the Katib experiment.

For building the image (Step 3), instructions are available in the same 
directory.

For Step 4, you can use the example provided in this directory.

## Starting the Experiment

### Image Configuration
The YAML file uses the Prokube development registry by default:
```
europe-west3-docker.pkg.dev/prokube/development/minimal-mnist:latest
```

**If you don't have access to the prokube registry**, you need to:
1. Build your own image (see [../../images/minimal-mnist/README.md](../../images/minimal-mnist/README.md) for instructions)
2. Replace the `image` field in `katib-experiment.yaml` (line 73) with your own registry path

### Running the Experiment
```sh
kubectl create -f katib-experiment.yaml
```

## Deleting the Experiment
To delete the experiment from your Kubernetes cluster, run:

```sh
kubectl delete -f katib-experiment.yaml
```
