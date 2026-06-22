"""Google Workspace OAuth helpers for local personal-data adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from analytics_foundry.config import get_google_credentials_path, get_google_token_dir


def build_google_service(api_name: str, api_version: str, scopes: Iterable[str]):
    """Build a Google API service using local OAuth token files."""
    try:
        from google.auth.transport.requests import Request as GoogleAuthRequest
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Google adapters require optional dependencies: "
            "google-api-python-client google-auth-oauthlib google-auth-httplib2"
        ) from exc

    scope_list = list(scopes)
    token_dir = Path(get_google_token_dir())
    token_dir.mkdir(parents=True, exist_ok=True)
    token_path = token_dir / f"{api_name}_token.json"
    credentials_path = Path(get_google_credentials_path())

    credentials = None
    if token_path.is_file():
        credentials = Credentials.from_authorized_user_file(str(token_path), scope_list)
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(GoogleAuthRequest())
        else:
            if not credentials_path.is_file():
                raise RuntimeError(f"Google OAuth credentials file not found: {credentials_path}")
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), scope_list)
            credentials = flow.run_local_server(port=0)
        token_path.write_text(credentials.to_json(), encoding="utf-8")

    return build(api_name, api_version, credentials=credentials)
