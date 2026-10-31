"""Authentication state management and JWT inspection helpers for Streamlit.
"""

import base64
import json
from typing import Any, Dict, Optional
import streamlit as st


def decode_jwt_payload_unverified(token: str) -> Dict[str, Any]:
    """Decode JWT payload without cryptographic verification for display purposes.

    Permissions and actual access control are enforced by the API server.
    """
    if not token or not isinstance(token, str):
        return {}
    parts = token.strip().split(".")
    if len(parts) < 2:
        return {}
    payload_b64 = parts[1]
    # Add padding if needed
    remainder = len(payload_b64) % 4
    if remainder != 0:
        payload_b64 += "=" * (4 - remainder)
    try:
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return {}


def is_logged_in() -> bool:
    """Return True if an access token is stored in session state."""
    return bool(st.session_state.get("token") or st.session_state.get("access_token"))


def get_token() -> Optional[str]:
    """Return the active JWT token from session state if available."""
    return st.session_state.get("token") or st.session_state.get("access_token")


def current_email() -> Optional[str]:
    """Return the user's email if logged in."""
    return st.session_state.get("email")


def current_role() -> Optional[str]:
    """Return the user's role (admin, manager, contributor) from state or token."""
    if "role" in st.session_state and st.session_state["role"]:
        return st.session_state["role"]
    token = get_token()
    if token:
        payload = decode_jwt_payload_unverified(token)
        return payload.get("role")
    return None


def current_org_name() -> str:
    """Return the active organization name, or fallback to sensible default."""
    if st.session_state.get("registered_org_name"):
        return str(st.session_state["registered_org_name"])
    if st.session_state.get("org_name"):
        return str(st.session_state["org_name"])
    token = get_token()
    if token:
        payload = decode_jwt_payload_unverified(token)
        if payload.get("org_name"):
            return str(payload["org_name"])
        if payload.get("org_id"):
            return f"Org #{payload['org_id']}"
    return "Acme Logistics GmbH"


def login(token: str, email: str, role: Optional[str] = None, org_name: Optional[str] = None) -> None:
    """Store token and user credentials in session state."""
    st.session_state["token"] = token
    st.session_state["access_token"] = token
    st.session_state["jwt"] = token  # compatibility with Tuba's page
    st.session_state["email"] = email
    if org_name:
        st.session_state["org_name"] = org_name
    if role:
        st.session_state["role"] = role
    else:
        payload = decode_jwt_payload_unverified(token)
        st.session_state["role"] = payload.get("role", "contributor")
        if not org_name and payload.get("org_name"):
            st.session_state["org_name"] = payload.get("org_name")


def logout() -> None:
    """Clear user session state on logout."""
    for key in ["token", "access_token", "jwt", "email", "role", "org_name", "registered_org_name"]:
        st.session_state.pop(key, None)
