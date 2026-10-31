"""HTTP API Client helper for Streamlit UI.

Attaches Authorization header, sets a 5-second timeout,
and automatically handles 401 Unauthorized by logging out and showing a notification.
"""

import os
from typing import Any, Dict, Optional, Tuple
import requests
import streamlit as st

from ui.auth_state import get_token, logout

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
DEFAULT_TIMEOUT = 5


def get_headers(extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    headers = {}
    token = get_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
    return headers


def handle_401_response():
    logout()
    st.warning("Your session has expired. Please log in again.")
    st.rerun()


def api_get(path: str, params: Optional[Dict[str, Any]] = None, timeout: int = DEFAULT_TIMEOUT) -> Tuple[bool, Any]:
    """Execute GET request against API. Returns (success_bool, json_or_error_dict)."""
    url = f"{API_URL}/{path.lstrip('/')}"
    headers = get_headers()
    try:
        res = requests.get(url, headers=headers, params=params, timeout=timeout)
        if res.status_code == 401:
            handle_401_response()
            return False, {"detail": "Session expired"}
        if res.status_code >= 200 and res.status_code < 300:
            try:
                return True, res.json()
            except Exception:
                return True, res.content
        try:
            return False, res.json()
        except Exception:
            return False, {"detail": res.text, "status_code": res.status_code}
    except requests.RequestException as exc:
        return False, {"detail": f"API not reachable: {exc}"}


def api_post(
    path: str,
    json_data: Optional[Dict[str, Any]] = None,
    form_data: Optional[Dict[str, Any]] = None,
    files: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Tuple[bool, Any]:
    """Execute POST request against API. Returns (success_bool, json_or_error_dict)."""
    url = f"{API_URL}/{path.lstrip('/')}"
    headers = get_headers()
    try:
        if files is not None:
            res = requests.post(url, headers=headers, files=files, timeout=timeout)
        elif form_data is not None:
            res = requests.post(url, headers=headers, data=form_data, timeout=timeout)
        else:
            res = requests.post(url, headers=headers, json=json_data, timeout=timeout)
        if res.status_code == 401:
            handle_401_response()
            return False, {"detail": "Session expired"}
        if res.status_code >= 200 and res.status_code < 300:
            try:
                return True, res.json()
            except Exception:
                return True, res.content
        try:
            return False, res.json()
        except Exception:
            return False, {"detail": res.text, "status_code": res.status_code}
    except requests.RequestException as exc:
        return False, {"detail": f"API not reachable: {exc}"}


def api_delete(path: str, timeout: int = DEFAULT_TIMEOUT) -> Tuple[bool, Any]:
    """Execute DELETE request against API. Returns (success_bool, json_or_error_dict)."""
    url = f"{API_URL}/{path.lstrip('/')}"
    headers = get_headers()
    try:
        res = requests.delete(url, headers=headers, timeout=timeout)
        if res.status_code == 401:
            handle_401_response()
            return False, {"detail": "Session expired"}
        if res.status_code >= 200 and res.status_code < 300:
            try:
                return True, res.json() if res.content else None
            except Exception:
                return True, None
        try:
            return False, res.json()
        except Exception:
            return False, {"detail": res.text, "status_code": res.status_code}
    except requests.RequestException as exc:
        return False, {"detail": f"API not reachable: {exc}"}
