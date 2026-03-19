# Release Notes Document Generator

This repository contains a small CLI utility that builds a release notes
document from Salesforce records.

## What it does

Given a **release name** and optional **account ID**, the script queries
Salesforce release note records and includes only records where:

1. the release note is linked to that release, and
2. the release note account is either:
   - empty (`null`), or
   - the account ID provided on input.

The generated document includes:

- Release Note Name
- Release Note Details

## Script location

`scripts/generate_release_notes_document.py`

## Authentication options

Set one of the following environment-variable groups:

### Option A: Existing token

- `SF_INSTANCE_URL`
- `SF_ACCESS_TOKEN`

### Option B: Username/password OAuth flow

- `SF_USERNAME`
- `SF_PASSWORD`
- `SF_SECURITY_TOKEN` (optional, but often required)
- `SF_CLIENT_ID`
- `SF_CLIENT_SECRET`
- `SF_LOGIN_URL` (optional, defaults to `https://login.salesforce.com`)

### Option C: Browser login (no auth env vars required)

This mode uses OAuth + PKCE and opens your browser for Salesforce login.

You only need a Salesforce Connected App **consumer key** (client ID).

## Salesforce Connected App setup (for browser mode)

In Salesforce, create/update a Connected App with OAuth enabled:

1. Enable OAuth settings
2. Set callback URL to:
   - `http://localhost:1717/callback`
3. Add OAuth scopes:
   - `Access and manage your data (api)`

Use the Connected App **Consumer Key** as `--sf-client-id`.

## Usage

```bash
python3 scripts/generate_release_notes_document.py \
  --release-name "Spring 2026" \
  --account-id "001xxxxxxxxxxxxAAA"
```

### Browser login usage (no auth env vars)

```bash
python3 scripts/generate_release_notes_document.py \
  --auth-method browser \
  --sf-client-id "YOUR_CONNECTED_APP_CONSUMER_KEY" \
  --release-name "Spring 2026" \
  --account-id "001xxxxxxxxxxxxAAA"
```

The script starts a local callback server at `localhost:1717`, opens your
browser to Salesforce login, then continues automatically after sign-in.

## Simple desktop UI

Run the UI directly:

```bash
python3 scripts/release_notes_gui.py
```

In the app:

1. Enter Release Name
2. (Optional) Enter Account ID
3. Enter Salesforce Client ID (Connected App consumer key)
4. Click **Generate Release Notes Document**

The app opens Salesforce login in your browser and writes the markdown file
after successful authentication.

### Optional arguments

- `--output`: output file path (default auto-generated markdown file name)
- `--release-note-object`: Salesforce object API name (default `Release_Note__c`)
- `--release-lookup-field`: field path to release name (default `Release__r.Name`)
- `--account-field`: account lookup field API name (default `Account__c`)
- `--name-field`: release note title field (default `Name`)
- `--details-field`: release note details field (default `Details__c`)
- `--api-version`: Salesforce API version (default `v59.0`)
- `--auth-method`: `auto` (default), `env`, or `browser`
- `--sf-client-id`: Connected App consumer key (required for browser mode)
- `--sf-login-url`: login URL (default `https://login.salesforce.com`)
- `--redirect-host`: local callback host (default `localhost`)
- `--redirect-port`: local callback port (default `1717`)
- `--auth-timeout-seconds`: wait time for OAuth callback (default `300`)
- `--no-open-browser`: print auth URL instead of opening browser automatically

## Build as desktop executable

You can package UI + CLI executables using PyInstaller.

### macOS / Linux

```bash
./scripts/build_desktop_executable.sh
```

Output binaries:

- `dist/release-notes-generator-ui` (desktop UI)
- `dist/release-notes-generator-cli` (command line)

### Windows (PowerShell)

```powershell
py -m pip install --upgrade pyinstaller
pyinstaller --onefile --windowed --name release-notes-generator-ui scripts/release_notes_gui.py
pyinstaller --onefile --name release-notes-generator-cli scripts/generate_release_notes_document.py
```

Output binaries:

- `dist\release-notes-generator-ui.exe`
- `dist\release-notes-generator-cli.exe`

## Example output

```md
# Release Notes - Spring 2026

- Release: `Spring 2026`
- Account filter: `001xxxxxxxxxxxxAAA`

## 1. Improved Dashboard Filtering

Added multi-select behavior for dashboard filter chips and improved persistence.

## 2. Export Performance Enhancements

Reduced export generation time for large reports.
```
