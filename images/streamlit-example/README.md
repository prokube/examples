# Kubeflow Streamlit Example

A Streamlit demo app that runs both as a Kubeflow notebook and as a standalone Kubernetes deployment with Istio. The app includes interactive widgets (slider, text input) and data visualization.

## Converting Your Existing Streamlit App

To convert your existing Streamlit app to work with Kubeflow, you need to address **URL path prefixing** and **port configuration**. The key challenge is that Kubeflow serves apps under path prefixes (like `/streamlit/` or `/notebook/<namespace>/<name>/`) rather than at the root URL.

This template solves this with an **entrypoint script** (`entrypoint.sh`) that dynamically configures Streamlit's `baseUrlPath` based on the `NB_PREFIX` environment variable.

**Required steps for all deployment options:**

1. Copy the `entrypoint.sh` script and reference it in your Dockerfile's CMD
2. Ensure your app runs on **port 8888** (Kubeflow notebook standard)
3. Set `STREAMLIT_SERVER_ENABLE_CORS=false` and `STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false` for Istio compatibility

**Additional steps for standalone deployment (Option 2 only):**

4. In the Kubernetes manifest (`k8s/streamlit-manifests.yaml`), set the `NB_PREFIX` env var to match your VirtualService prefix (e.g., `/streamlit`)
5. Create an Istio `AuthorizationPolicy` to allow traffic from the ingress gateway

The entrypoint script handles all the Streamlit configuration automatically, so your application code remains unchanged.

## Building the Docker Image

**For Mac (especially Apple Silicon)**, specify platform for Linux AMD64:
```bash
docker build --platform linux/amd64 -t <registry>/streamlit-demo:latest .
docker push <registry>/streamlit-demo:latest
```

**For Linux AMD64 hosts**:
```bash
docker build -t <registry>/streamlit-demo:latest .
docker push <registry>/streamlit-demo:latest
```

If you push to a different registry, update the image reference in `k8s/streamlit-manifests.yaml` at line 29 (the `image:` field in the Deployment spec). The default image is `europe-west3-docker.pkg.dev/prokube/development/streamlit-example:latest`.

## Deployment Options

### Option 1: Kubeflow Notebook (Recommended)

Deploy as a custom notebook image through the Kubeflow UI:

1. Open the Kubeflow Central Dashboard
2. Navigate to **Notebooks** in the left sidebar
3. Click **New Notebook**
4. Fill in the notebook configuration:
   - **Name**: Choose a name (e.g., `streamlit-demo`)
   - **Custom Image**: Enable and enter the image URL:
     ```
     europe-west3-docker.pkg.dev/prokube/development/streamlit-example:latest
     ```
   - Leave other settings as default (or adjust CPU/memory as needed)
5. Click **Launch**
6. Once running, click **Connect** to open the Streamlit app

The image automatically detects the `NB_PREFIX` environment variable set by Kubeflow and configures Streamlit with the correct base URL path.

**Access URL**: `https://<kubeflow-host>/notebook/<namespace>/<notebook-name>/`

**Troubleshooting**:
- Ensure the URL has a trailing slash
- Check browser console for websocket connection errors
- Verify the pod is running: `kubectl get pods -n <namespace>`

### Option 2: Standalone Deployment

Deploy as a standalone service accessible via a path prefix on your Kubeflow ingress:

```bash
kubectl apply -f k8s/streamlit-manifests.yaml
```

**Configuration required before deploying:**

The manifest (`k8s/streamlit-manifests.yaml`) contains default values that work out of the box with a path-based URL. The app will be available at:

```
https://<your-kubeflow-host>/streamlit/
```

For example, if your Kubeflow is at `https://kubeflow.example.com`, the Streamlit app will be at `https://kubeflow.example.com/streamlit/`.

**What the manifest creates:**
- **Namespace**: `streamlitdemo` with Istio injection enabled
- **Deployment**: Single replica running the Streamlit app on port 8888
- **Service**: Exposes the app internally on port 80
- **VirtualService**: Routes `/streamlit/` traffic through the Kubeflow gateway
- **AuthorizationPolicy**: Allows traffic from the Istio ingress gateway

**Customization options:**

To deploy to a different namespace or with a different name, update all occurrences of `streamlitdemo` (namespace) and `streamlit-demo` (resource name) throughout the manifest.

To change the URL path (e.g., from `/streamlit/` to `/myapp/`):
1. Update the `NB_PREFIX` env var in the Deployment (line 37)
2. Update the `readinessProbe` and `livenessProbe` paths (lines 40, 46)
3. Update the VirtualService URI matches (lines 79, 85)

## Notes

- Istio sidecar injection is enabled via `sidecar.istio.io/inject: "true"` on the Pod template. Adjust or disable it if deploying outside Kubeflow.
- The entrypoint script (`entrypoint.sh`) dynamically configures Streamlit based on whether `NB_PREFIX` is set.
