import base64
import json
import pytest
from unittest.mock import patch, MagicMock

from ui.auth_state import decode_jwt_payload_unverified, login, logout, is_logged_in, current_role
from ui.api_client import api_get, api_post


def create_test_token(payload: dict) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signature_b64 = "fakesignature"
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def test_decode_jwt_payload_unverified():
    payload = {"sub": "1", "email": "admin@carbonlens.com", "role": "admin", "org_id": "1"}
    token = create_test_token(payload)
    decoded = decode_jwt_payload_unverified(token)
    assert decoded["email"] == "admin@carbonlens.com"
    assert decoded["role"] == "admin"
    assert decoded["org_id"] == "1"


def test_decode_jwt_invalid_token():
    assert decode_jwt_payload_unverified("") == {}
    assert decode_jwt_payload_unverified("invalid-token") == {}
    assert decode_jwt_payload_unverified("abc.def") == {}


def test_auth_state_helpers():
    mock_session = {}
    with patch("streamlit.session_state", mock_session):
        assert not is_logged_in()
        assert current_role() is None

        payload = {"sub": "2", "email": "manager@carbonlens.com", "role": "manager"}
        token = create_test_token(payload)

        login(token=token, email="manager@carbonlens.com", role="manager")
        assert is_logged_in()
        assert mock_session.get("token") == token
        assert mock_session.get("access_token") == token
        assert mock_session.get("jwt") == token
        assert current_role() == "manager"

        logout()
        assert not is_logged_in()
        assert mock_session.get("token") is None
        assert current_role() is None


@patch("requests.get")
@patch("streamlit.rerun")
@patch("streamlit.warning")
def test_api_client_handles_401(mock_warning, mock_rerun, mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_get.return_value = mock_response

    mock_session = {"token": "some_expired_token"}
    with patch("streamlit.session_state", mock_session):
        ok, res = api_get("analytics/summary")
        assert ok is False
        assert mock_session.get("token") is None  # verified logout called
        mock_warning.assert_called_once()
        mock_rerun.assert_called_once()
