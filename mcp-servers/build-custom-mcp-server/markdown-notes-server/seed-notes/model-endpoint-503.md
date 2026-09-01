# Model Endpoint 503

## Symptoms

- Client requests to a model endpoint return `503`.
- The endpoint is listed in the UI, but predictions fail.

## Checks

1. Check whether the backing pod is running.
2. Check recent pod events for image pull, quota, or readiness errors.
3. Check the model server logs.
4. Confirm that the endpoint is not scaling from zero and still warming up.

## Escalate

Escalate to the platform owner if pods cannot be scheduled because of quota or node capacity.
