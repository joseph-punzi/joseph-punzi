#!/usr/bin/env python3
"""Generate a release notes document from Salesforce data.

This script queries Salesforce for release notes attached to a given release
name and writes a Markdown document containing the release note name and
details. Results are filtered to include:
  - release notes with no account assigned, and
  - release notes assigned to the provided account ID (if any).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import os
import re
import secrets
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


DEFAULT_API_VERSION = "v59.0"
DEFAULT_LOGIN_URL = "https://login.salesforce.com"
DEFAULT_REDIRECT_HOST = "localhost"
DEFAULT_REDIRECT_PORT = 1717
DEFAULT_AUTH_TIMEOUT_SECONDS = 300


def escape_soql(value: str) -> str:
    """Escape single quotes and backslashes in SOQL string literals."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def slugify(value: str) -> str:
    """Create a filesystem-safe slug for output file names."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    return slug or "release-notes"


def generate_pkce_verifier_and_challenge() -> tuple[str, str]:
    """Return a PKCE code verifier and S256 challenge."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode("utf-8").rstrip("=")
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("utf-8")).digest())
        .decode("utf-8")
        .rstrip("=")
    )
    return verifier, challenge


def build_browser_authorization_url(
    *,
    login_url: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
) -> str:
    """Build Salesforce browser OAuth authorization URL."""
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{login_url.rstrip('/')}/services/oauth2/authorize?{query}"


def build_release_notes_soql(
    release_name: str,
    account_id: Optional[str],
    *,
    release_note_object: str,
    release_lookup_field: str,
    account_field: str,
    name_field: str,
    details_field: str,
) -> str:
    """Build a SOQL query for release notes with account filtering rules."""
    safe_release_name = escape_soql(release_name)
    where_parts = [f"{release_lookup_field} = '{safe_release_name}'"]

    if account_id:
        safe_account_id = escape_soql(account_id)
        where_parts.append(
            f"({account_field} = null OR {account_field} = '{safe_account_id}')"
        )
    else:
        where_parts.append(f"{account_field} = null")

    where_clause = " AND ".join(where_parts)
    return (
        f"SELECT {name_field}, {details_field} "
        f"FROM {release_note_object} "
        f"WHERE {where_clause} "
        f"ORDER BY {name_field}"
    )


def render_release_notes_markdown(
    release_name: str,
    account_id: Optional[str],
    records: List[Dict[str, Any]],
    *,
    name_field: str,
    details_field: str,
) -> str:
    """Render queried release notes into a Markdown document."""
    lines: List[str] = [
        f"# Release Notes - {release_name}",
        "",
        f"- Release: `{release_name}`",
        f"- Account filter: `{account_id}`" if account_id else "- Account filter: none",
        "",
    ]

    if not records:
        lines.extend(["No release notes matched the selected filters.", ""])
        return "\n".join(lines)

    for index, record in enumerate(records, start=1):
        name = record.get(name_field) or "(Unnamed Release Note)"
        details = record.get(details_field) or "(No details provided)"
        lines.extend(
            [
                f"## {index}. {name}",
                "",
                str(details),
                "",
            ]
        )

    return "\n".join(lines)


def default_output_path(release_name: str, account_id: Optional[str]) -> str:
    """Return default markdown output path for a release/account combination."""
    name_slug = slugify(release_name)
    account_suffix = f"-{slugify(account_id)}" if account_id else ""
    return f"release-notes-{name_slug}{account_suffix}.md"


def generate_release_notes_document(
    *,
    client: "SalesforceClient",
    release_name: str,
    account_id: Optional[str],
    output_path: Optional[str],
    release_note_object: str,
    release_lookup_field: str,
    account_field: str,
    name_field: str,
    details_field: str,
) -> tuple[str, int]:
    """Query Salesforce and write release notes markdown file."""
    soql = build_release_notes_soql(
        release_name,
        account_id,
        release_note_object=release_note_object,
        release_lookup_field=release_lookup_field,
        account_field=account_field,
        name_field=name_field,
        details_field=details_field,
    )
    records = client.query_all(soql)
    document = render_release_notes_markdown(
        release_name,
        account_id,
        records,
        name_field=name_field,
        details_field=details_field,
    )

    resolved_output_path = output_path or default_output_path(release_name, account_id)
    with open(resolved_output_path, "w", encoding="utf-8") as file_handle:
        file_handle.write(document)
    return resolved_output_path, len(records)


@dataclass
class SalesforceConnection:
    """Authentication and endpoint details for Salesforce API usage."""

    instance_url: str
    access_token: str
    api_version: str = DEFAULT_API_VERSION

    @property
    def query_endpoint(self) -> str:
        return (
            f"{self.instance_url}/services/data/{self.api_version}/query/"
        )


class SalesforceClient:
    """Minimal Salesforce REST API client for SOQL queries."""

    def __init__(self, connection: SalesforceConnection) -> None:
        self.connection = connection

    @classmethod
    def from_environment(cls, api_version: str) -> "SalesforceClient":
        instance_url = os.getenv("SF_INSTANCE_URL")
        access_token = os.getenv("SF_ACCESS_TOKEN")

        if instance_url and access_token:
            return cls(
                SalesforceConnection(
                    instance_url=instance_url.rstrip("/"),
                    access_token=access_token,
                    api_version=api_version,
                )
            )

        username = os.getenv("SF_USERNAME")
        password = os.getenv("SF_PASSWORD")
        security_token = os.getenv("SF_SECURITY_TOKEN", "")
        client_id = os.getenv("SF_CLIENT_ID")
        client_secret = os.getenv("SF_CLIENT_SECRET")
        login_url = os.getenv("SF_LOGIN_URL", DEFAULT_LOGIN_URL)

        missing = [
            name
            for name, value in [
                ("SF_INSTANCE_URL", instance_url),
                ("SF_ACCESS_TOKEN", access_token),
                ("SF_USERNAME", username),
                ("SF_PASSWORD", password),
                ("SF_CLIENT_ID", client_id),
                ("SF_CLIENT_SECRET", client_secret),
            ]
            if not value
        ]

        if missing and not (username and password and client_id and client_secret):
            joined = ", ".join(missing)
            raise RuntimeError(
                "Missing Salesforce credentials. Provide either "
                "SF_INSTANCE_URL + SF_ACCESS_TOKEN, or username/password OAuth vars. "
                f"Unset values: {joined}"
            )

        token_response = cls._request_password_grant_token(
            login_url=login_url.rstrip("/"),
            username=username or "",
            password=(password or "") + security_token,
            client_id=client_id or "",
            client_secret=client_secret or "",
        )

        return cls(
            SalesforceConnection(
                instance_url=token_response["instance_url"],
                access_token=token_response["access_token"],
                api_version=api_version,
            )
        )

    @classmethod
    def from_browser_oauth(
        cls,
        *,
        api_version: str,
        client_id: str,
        login_url: str,
        redirect_host: str,
        redirect_port: int,
        timeout_seconds: int,
        open_browser: bool,
    ) -> "SalesforceClient":
        """Authenticate with Salesforce through browser OAuth + PKCE."""
        state = secrets.token_urlsafe(24)
        code_verifier, code_challenge = generate_pkce_verifier_and_challenge()

        with OAuthCallbackServer(
            host=redirect_host,
            port=redirect_port,
            expected_state=state,
        ) as callback_server:
            auth_url = build_browser_authorization_url(
                login_url=login_url,
                client_id=client_id,
                redirect_uri=callback_server.redirect_uri,
                state=state,
                code_challenge=code_challenge,
            )

            if open_browser:
                opened = webbrowser.open(auth_url)
                if opened:
                    print("Opened Salesforce login in your browser.")
                else:
                    print("Could not open browser automatically. Open this URL manually:")
                    print(auth_url)
            else:
                print("Open this URL in your browser to authenticate:")
                print(auth_url)

            authorization_code = callback_server.wait_for_code(timeout_seconds)

        token_response = cls._request_authorization_code_token(
            login_url=login_url.rstrip("/"),
            client_id=client_id,
            code=authorization_code,
            code_verifier=code_verifier,
            redirect_uri=callback_server.redirect_uri,
        )

        return cls(
            SalesforceConnection(
                instance_url=token_response["instance_url"],
                access_token=token_response["access_token"],
                api_version=api_version,
            )
        )

    @staticmethod
    def _request_password_grant_token(
        *,
        login_url: str,
        username: str,
        password: str,
        client_id: str,
        client_secret: str,
    ) -> Dict[str, Any]:
        payload = urllib.parse.urlencode(
            {
                "grant_type": "password",
                "client_id": client_id,
                "client_secret": client_secret,
                "username": username,
                "password": password,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url=f"{login_url}/services/oauth2/token",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Salesforce authentication failed ({exc.code}): {body}"
            ) from exc

    @staticmethod
    def _request_authorization_code_token(
        *,
        login_url: str,
        client_id: str,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> Dict[str, Any]:
        payload = urllib.parse.urlencode(
            {
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url=f"{login_url}/services/oauth2/token",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Salesforce browser authentication failed ({exc.code}): {body}"
            ) from exc

    def query_all(self, soql: str) -> List[Dict[str, Any]]:
        query_url = f"{self.connection.query_endpoint}?q={urllib.parse.quote(soql)}"
        records: List[Dict[str, Any]] = []

        while query_url:
            payload = self._request_json(query_url)
            records.extend(payload.get("records", []))
            next_url = payload.get("nextRecordsUrl")
            query_url = (
                f"{self.connection.instance_url}{next_url}" if next_url else ""
            )

        return records

    def _request_json(self, url: str) -> Dict[str, Any]:
        request = urllib.request.Request(
            url=url,
            headers={
                "Authorization": f"Bearer {self.connection.access_token}",
                "Content-Type": "application/json",
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Salesforce query failed ({exc.code}): {body}") from exc


@dataclass
class OAuthCallbackContext:
    """Holds callback state for browser-based OAuth."""

    expected_state: str
    authorization_code: Optional[str] = None
    error: Optional[str] = None
    event: threading.Event = field(default_factory=threading.Event)


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Capture OAuth callback requests from Salesforce."""

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Not found")
            return

        context: OAuthCallbackContext = self.server.oauth_context  # type: ignore[attr-defined]
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        error = params.get("error", [None])[0]
        error_description = params.get("error_description", [None])[0]

        if error:
            context.error = (
                f"Salesforce returned OAuth error '{error}': {error_description or 'Unknown'}"
            )
            body = "Authentication failed. You can close this tab."
        elif state != context.expected_state:
            context.error = "OAuth state mismatch. Authentication was rejected."
            body = "Authentication failed due to state mismatch. Close this tab."
        elif not code:
            context.error = "OAuth callback did not include an authorization code."
            body = "Authentication failed (missing authorization code). Close this tab."
        else:
            context.authorization_code = code
            body = "Authentication succeeded. You can close this tab and return to the app."

        context.event.set()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = (
            "<!DOCTYPE html><html><body>"
            f"<p>{body}</p>"
            "</body></html>"
        )
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress callback server logs to keep CLI output clean."""
        del format, args


class OAuthCallbackServer:
    """Small local web server used to receive OAuth browser callbacks."""

    def __init__(self, *, host: str, port: int, expected_state: str) -> None:
        self.context = OAuthCallbackContext(expected_state=expected_state, event=threading.Event())
        self._server = http.server.ThreadingHTTPServer((host, port), OAuthCallbackHandler)
        self._server.oauth_context = self.context  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self.redirect_uri = f"http://{host}:{self._server.server_port}/callback"

    def __enter__(self) -> "OAuthCallbackServer":
        self._thread.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.shutdown()
        del exc_type, exc, tb

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)

    def wait_for_code(self, timeout_seconds: int) -> str:
        completed = self.context.event.wait(timeout=timeout_seconds)
        if not completed:
            raise RuntimeError(
                "Timed out waiting for Salesforce browser login callback. "
                "Try again and complete login in the opened browser."
            )
        if self.context.error:
            raise RuntimeError(self.context.error)
        if not self.context.authorization_code:
            raise RuntimeError("OAuth callback completed without an authorization code.")
        return self.context.authorization_code


def build_salesforce_client(args: argparse.Namespace) -> SalesforceClient:
    """Build authenticated Salesforce client from selected auth method."""
    auth_method = args.auth_method
    browser_client_id = args.sf_client_id or os.getenv("SF_CLIENT_ID")

    if auth_method == "env":
        return SalesforceClient.from_environment(api_version=args.api_version)

    if auth_method == "browser":
        if not browser_client_id:
            raise RuntimeError(
                "Browser auth requires --sf-client-id (or SF_CLIENT_ID env var)."
            )
        return SalesforceClient.from_browser_oauth(
            api_version=args.api_version,
            client_id=browser_client_id,
            login_url=args.sf_login_url,
            redirect_host=args.redirect_host,
            redirect_port=args.redirect_port,
            timeout_seconds=args.auth_timeout_seconds,
            open_browser=not args.no_open_browser,
        )

    # auto mode: try environment-based auth if env credentials exist, otherwise browser auth.
    has_token_auth = bool(os.getenv("SF_INSTANCE_URL") and os.getenv("SF_ACCESS_TOKEN"))
    has_password_auth = bool(
        os.getenv("SF_USERNAME")
        and os.getenv("SF_PASSWORD")
        and os.getenv("SF_CLIENT_ID")
        and os.getenv("SF_CLIENT_SECRET")
    )
    if has_token_auth or has_password_auth:
        return SalesforceClient.from_environment(api_version=args.api_version)
    if browser_client_id:
        return SalesforceClient.from_browser_oauth(
            api_version=args.api_version,
            client_id=browser_client_id,
            login_url=args.sf_login_url,
            redirect_host=args.redirect_host,
            redirect_port=args.redirect_port,
            timeout_seconds=args.auth_timeout_seconds,
            open_browser=not args.no_open_browser,
        )

    raise RuntimeError(
        "No usable Salesforce auth found. Either provide environment credentials "
        "or run browser auth with --sf-client-id."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a release notes markdown document from Salesforce data."
        )
    )
    parser.add_argument("--release-name", required=True, help="Release name filter")
    parser.add_argument(
        "--account-id",
        default=None,
        help=(
            "Account ID to include in addition to global notes. "
            "If omitted, only notes with no account are included."
        ),
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Output markdown file path. "
            "Default: release-notes-<release-name>[-<account-id>].md"
        ),
    )
    parser.add_argument(
        "--release-note-object",
        default="Release_Note__c",
        help="Salesforce API name for the release note object",
    )
    parser.add_argument(
        "--release-lookup-field",
        default="Release__r.Name",
        help="Lookup field path from release note to release name",
    )
    parser.add_argument(
        "--account-field",
        default="Account__c",
        help="Salesforce account lookup field API name on release note object",
    )
    parser.add_argument(
        "--name-field",
        default="Name",
        help="Salesforce field API name for release note title",
    )
    parser.add_argument(
        "--details-field",
        default="Details__c",
        help="Salesforce field API name for release note details",
    )
    parser.add_argument(
        "--api-version",
        default=DEFAULT_API_VERSION,
        help="Salesforce REST API version to query (e.g. v59.0)",
    )
    parser.add_argument(
        "--auth-method",
        choices=["auto", "env", "browser"],
        default="auto",
        help=(
            "Salesforce authentication method. "
            "'auto' tries env credentials first and falls back to browser auth."
        ),
    )
    parser.add_argument(
        "--sf-client-id",
        default=None,
        help=(
            "Salesforce Connected App consumer key for browser auth "
            "(required for --auth-method browser)."
        ),
    )
    parser.add_argument(
        "--sf-login-url",
        default=os.getenv("SF_LOGIN_URL", DEFAULT_LOGIN_URL),
        help=(
            "Salesforce login URL for OAuth (e.g. login.salesforce.com or test.salesforce.com)."
        ),
    )
    parser.add_argument(
        "--redirect-host",
        default=DEFAULT_REDIRECT_HOST,
        help="Local callback host for browser OAuth flow",
    )
    parser.add_argument(
        "--redirect-port",
        default=DEFAULT_REDIRECT_PORT,
        type=int,
        help="Local callback port for browser OAuth flow",
    )
    parser.add_argument(
        "--auth-timeout-seconds",
        default=DEFAULT_AUTH_TIMEOUT_SECONDS,
        type=int,
        help="Seconds to wait for OAuth callback before timing out",
    )
    parser.add_argument(
        "--no-open-browser",
        action="store_true",
        help="Print login URL instead of opening a browser automatically",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = build_salesforce_client(args)
    output_path, record_count = generate_release_notes_document(
        client=client,
        release_name=args.release_name,
        account_id=args.account_id,
        output_path=args.output,
        release_note_object=args.release_note_object,
        release_lookup_field=args.release_lookup_field,
        account_field=args.account_field,
        name_field=args.name_field,
        details_field=args.details_field,
    )
    print(f"Wrote {record_count} release notes to {output_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
