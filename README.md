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

## Usage

```bash
python3 scripts/generate_release_notes_document.py \
  --release-name "Spring 2026" \
  --account-id "001xxxxxxxxxxxxAAA"
```

### Optional arguments

- `--output`: output file path (default auto-generated markdown file name)
- `--release-note-object`: Salesforce object API name (default `Release_Note__c`)
- `--release-lookup-field`: field path to release name (default `Release__r.Name`)
- `--account-field`: account lookup field API name (default `Account__c`)
- `--name-field`: release note title field (default `Name`)
- `--details-field`: release note details field (default `Details__c`)
- `--api-version`: Salesforce API version (default `v59.0`)

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
