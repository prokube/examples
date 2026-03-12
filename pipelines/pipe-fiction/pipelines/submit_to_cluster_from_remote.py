"""
Submit a KFP pipeline to a remote Kubeflow cluster using Keycloak authentication.

Prerequisites:
    A Keycloak admin must have created an OIDC client with Direct Access Grants
    enabled and shared the client secret with you (see README for details).

Required environment variables:
    KUBEFLOW_ENDPOINT:   Kubeflow URL (e.g. https://kubeflow.example.com)
    KUBEFLOW_USERNAME:   User email in the Keycloak realm
    KUBEFLOW_PASSWORD:   User password
    KEYCLOAK_URL:        Base URL where Keycloak /auth/ is reachable
                         (often same as KUBEFLOW_ENDPOINT)
    KFP_CLIENT_SECRET:   Client secret provided by the admin

Optional environment variables:
    KEYCLOAK_REALM:      Keycloak realm name (default: "prokube")
    KFP_CLIENT_ID:       Client ID created by admin (default: "kfp-remote-user")
    KUBEFLOW_NAMESPACE:  KFP namespace (default: derived from username)
    IMAGE_TAG:           Docker image for the pipeline components
"""

import os

import truststore

from kfp.client import Client
from pipeline import example_pipeline
from utils.auth_session import get_user_token

truststore.inject_into_ssl()

# Authenticate via Keycloak (requires a pre-created OIDC client — see README)
token = get_user_token(
    keycloak_url=os.environ["KEYCLOAK_URL"],
    client_secret=os.environ["KFP_CLIENT_SECRET"],
    username=os.environ["KUBEFLOW_USERNAME"],
    password=os.environ["KUBEFLOW_PASSWORD"],
    realm=os.environ.get("KEYCLOAK_REALM", "prokube"),
    client_id=os.environ.get("KFP_CLIENT_ID", "kfp-remote-user"),
)

namespace = os.environ.get("KUBEFLOW_NAMESPACE") or os.environ[
    "KUBEFLOW_USERNAME"
].split("@")[0].replace(".", "-")

client = Client(
    host=f"{os.environ['KUBEFLOW_ENDPOINT']}/pipeline",
    namespace=namespace,
    existing_token=token,
    verify_ssl=False,
)

run = client.create_run_from_pipeline_func(
    example_pipeline,
    enable_caching=False,
)
