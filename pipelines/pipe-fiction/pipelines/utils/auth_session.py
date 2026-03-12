"""
Keycloak authentication for remote KFP pipeline submission.

This module provides a way to obtain a Bearer token for Kubeflow
when the cluster uses Keycloak as the identity provider.

The workflow is:
1. Get an admin token from Keycloak (master realm).
2. Create a temporary OIDC client with direct access grants.
3. Use that client to obtain a user access token.
4. Clean up the temporary client.
5. Pass the token to the KFP Client via ``existing_token``.

Requirements:
- KEYCLOAK_ADMIN_PASSWORD must be provided (or kubectl access to read the secret).
- The user must exist in the Keycloak realm.

Environment variables:
    KUBEFLOW_ENDPOINT:        Kubeflow URL (e.g. https://kubeflow.example.com)
    KUBEFLOW_USERNAME:        User email in the Keycloak realm
    KUBEFLOW_PASSWORD:        User password
    KEYCLOAK_URL:             Base URL where Keycloak /auth/ is reachable
                              (often same as KUBEFLOW_ENDPOINT)
    KEYCLOAK_ADMIN_PASSWORD:  Keycloak admin password
    KEYCLOAK_REALM:           Keycloak realm name (default: "prokube")
"""

import json
import logging

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# Name of the temporary OIDC client created for authentication
_TEMP_CLIENT_ID = "kfp-cli-tmp"


def _get_admin_token(keycloak_url: str, admin_password: str) -> str:
    """Get an admin access token from the Keycloak master realm."""
    url = f"{keycloak_url}/auth/realms/master/protocol/openid-connect/token"
    resp = requests.post(
        url,
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": "admin",
            "password": admin_password,
        },
        verify=False,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _create_temp_client(keycloak_url: str, realm: str, headers: dict) -> None:
    """Create a temporary OIDC client with direct access grants enabled."""
    client_data = {
        "clientId": _TEMP_CLIENT_ID,
        "enabled": True,
        "publicClient": False,
        "protocol": "openid-connect",
        "directAccessGrantsEnabled": True,
        "serviceAccountsEnabled": True,
        "standardFlowEnabled": False,
    }
    url = f"{keycloak_url}/auth/admin/realms/{realm}/clients"
    resp = requests.post(
        url, headers=headers, data=json.dumps(client_data), verify=False, timeout=30
    )
    if resp.status_code == 409:
        logger.debug("Temporary client '%s' already exists", _TEMP_CLIENT_ID)
    elif resp.status_code == 201:
        logger.debug("Created temporary client '%s'", _TEMP_CLIENT_ID)
    else:
        raise RuntimeError(
            f"Failed to create temp client: {resp.status_code} {resp.text}"
        )


def _get_client_internal_id(keycloak_url: str, realm: str, headers: dict) -> str:
    """Get the internal UUID of the temporary client."""
    url = f"{keycloak_url}/auth/admin/realms/{realm}/clients"
    resp = requests.get(url, headers=headers, verify=False, timeout=30)
    resp.raise_for_status()
    clients = resp.json()
    client = next((c for c in clients if c["clientId"] == _TEMP_CLIENT_ID), None)
    if not client:
        raise RuntimeError(f"Could not find client '{_TEMP_CLIENT_ID}'")
    return client["id"]


def _get_client_secret(
    keycloak_url: str, realm: str, headers: dict, client_uuid: str
) -> str:
    """Get the secret for the temporary client."""
    url = (
        f"{keycloak_url}/auth/admin/realms/{realm}/clients/{client_uuid}/client-secret"
    )
    resp = requests.get(url, headers=headers, verify=False, timeout=30)
    resp.raise_for_status()
    return resp.json()["value"]


def _get_user_token(
    keycloak_url: str,
    realm: str,
    client_secret: str,
    username: str,
    password: str,
) -> str:
    """Get a user access token using the temporary client credentials."""
    url = f"{keycloak_url}/auth/realms/{realm}/protocol/openid-connect/token"
    resp = requests.post(
        url,
        data={
            "grant_type": "password",
            "client_id": _TEMP_CLIENT_ID,
            "client_secret": client_secret,
            "username": username,
            "password": password,
        },
        verify=False,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _delete_temp_client(keycloak_url: str, realm: str, headers: dict) -> None:
    """Delete the temporary client to clean up."""
    try:
        client_uuid = _get_client_internal_id(keycloak_url, realm, headers)
        url = f"{keycloak_url}/auth/admin/realms/{realm}/clients/{client_uuid}"
        resp = requests.delete(url, headers=headers, verify=False, timeout=30)
        if resp.status_code == 204:
            logger.debug("Deleted temporary client '%s'", _TEMP_CLIENT_ID)
        else:
            logger.warning(
                "Failed to delete temp client: %s %s", resp.status_code, resp.text
            )
    except Exception as e:
        logger.warning("Could not clean up temporary client: %s", e)


def get_keycloak_token(
    keycloak_url: str,
    admin_password: str,
    username: str,
    password: str,
    realm: str = "prokube",
) -> str:
    """
    Obtain a Keycloak user access token for authenticating with Kubeflow.

    This creates a temporary OIDC client in Keycloak, uses it to get a user
    token via the Resource Owner Password Credentials grant, then cleans up
    the temp client.

    The returned token can be passed to the KFP Client via ``existing_token``.

    NOTE: This requires Keycloak admin credentials. The temporary client is
    created and deleted within this function call.

    Args:
        keycloak_url:    Keycloak base URL (e.g. https://keycloak.example.com)
        admin_password:  Keycloak admin password
        username:        User email/username in the Keycloak realm
        password:        User password
        realm:           Keycloak realm name (default: "prokube")

    Returns:
        A Bearer access token string.
    """
    admin_token = _get_admin_token(keycloak_url, admin_password)
    admin_headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    }

    try:
        _create_temp_client(keycloak_url, realm, admin_headers)
        client_uuid = _get_client_internal_id(keycloak_url, realm, admin_headers)
        client_secret = _get_client_secret(
            keycloak_url, realm, admin_headers, client_uuid
        )
        user_token = _get_user_token(
            keycloak_url, realm, client_secret, username, password
        )
    finally:
        _delete_temp_client(keycloak_url, realm, admin_headers)

    return user_token
