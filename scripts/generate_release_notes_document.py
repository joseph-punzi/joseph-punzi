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
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


DEFAULT_API_VERSION = "v59.0"


def escape_soql(value: str) -> str:
    """Escape single quotes and backslashes in SOQL string literals."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def slugify(value: str) -> str:
    """Create a filesystem-safe slug for output file names."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    return slug or "release-notes"


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
        login_url = os.getenv("SF_LOGIN_URL", "https://login.salesforce.com")

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
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    soql = build_release_notes_soql(
        args.release_name,
        args.account_id,
        release_note_object=args.release_note_object,
        release_lookup_field=args.release_lookup_field,
        account_field=args.account_field,
        name_field=args.name_field,
        details_field=args.details_field,
    )

    client = SalesforceClient.from_environment(api_version=args.api_version)
    records = client.query_all(soql)

    document = render_release_notes_markdown(
        args.release_name,
        args.account_id,
        records,
        name_field=args.name_field,
        details_field=args.details_field,
    )

    output_path = args.output
    if not output_path:
        name_slug = slugify(args.release_name)
        account_suffix = f"-{slugify(args.account_id)}" if args.account_id else ""
        output_path = f"release-notes-{name_slug}{account_suffix}.md"

    with open(output_path, "w", encoding="utf-8") as file_handle:
        file_handle.write(document)

    print(f"Wrote {len(records)} release notes to {output_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
