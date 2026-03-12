"""
Keycloak authentication for remote KFP pipeline submission.

Obtains a user-scoped Bearer token using a pre-existing OIDC client that
has the Resource Owner Password Credentials (ROPC) grant enabled. The
admin creates this client once (via the Keycloak Admin UI); users then
authenticate with just their credentials and the client secret.

The returned token can be passed to the KFP Client via ``existing_token``.

Environment variables (for reference — callers pass values explicitly):
    KUBEFLOW_ENDPOINT:   Kubeflow URL (e.g. https://kubeflow.example.com)
    KUBEFLOW_USERNAME:   User email in the Keycloak realm
    KUBEFLOW_PASSWORD:   User password
    KEYCLOAK_URL:        Base URL where Keycloak /auth/ is reachable
                         (often same as KUBEFLOW_ENDPOINT)
    KFP_CLIENT_SECRET:   Client secret shared by the admin
    KEYCLOAK_REALM:      Keycloak realm name (default: "prokube")
    KFP_CLIENT_ID:       Client ID created by admin (default: "kfp-remote-user")
"""

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_DEFAULT_CLIENT_ID = "kfp-remote-user"


def get_user_token(
    keycloak_url: str,
    client_secret: str,
    username: str,
    password: str,
    realm: str = "prokube",
    client_id: str = _DEFAULT_CLIENT_ID,
) -> str:
    """
    Obtain a user-scoped Bearer token for authenticating with Kubeflow.

    Uses the Resource Owner Password Credentials grant against a Keycloak
    OIDC client that was pre-created by the admin. No admin credentials
    are needed.

    Args:
        keycloak_url:    Base URL where Keycloak ``/auth/`` is reachable
        client_secret:   Client secret shared by the admin
        username:        User email/username in the Keycloak realm
        password:        User password
        realm:           Keycloak realm name (default: "prokube")
        client_id:       Client ID created by admin (default: "kfp-remote-user")

    Returns:
        A Bearer access token string for ``Client(existing_token=...)``.
    """
    url = f"{keycloak_url}/auth/realms/{realm}/protocol/openid-connect/token"
    resp = requests.post(
        url,
        data={
            "grant_type": "password",
            "client_id": client_id,
            "client_secret": client_secret,
            "username": username,
            "password": password,
        },
        verify=False,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]
