# AGENTS.md

## Cursor Cloud specific instructions

### Project overview

Single-script Python CLI that queries Salesforce `Release_Note__c` records and renders them into a Markdown release-notes document. See `README.md` for full usage.

### Running tests

```bash
python3 -m pytest tests/ -v
```

Tests are pure-function unit tests (SOQL builder + Markdown renderer) with no network calls. They run offline in under a second.

### Lint

No dedicated linter is configured in the repo. Use `pyflakes` for quick static analysis:

```bash
python3 -m pyflakes scripts/ tests/
```

### Running the CLI

```bash
python3 scripts/generate_release_notes_document.py --release-name "Spring 2026" --account-id "001ABC123"
```

Requires Salesforce credentials via environment variables (see `README.md` for auth options). Without credentials the script exits with a clear error message listing which variables are missing.

### Key caveats

- **Zero third-party runtime dependencies.** The script uses only the Python standard library. `pytest` and `pyflakes` are dev-only tools.
- **No hot-reload or dev server.** This is a one-shot CLI tool; just re-run the script after changes.
- **Salesforce credentials required for E2E testing.** Unit tests cover the pure logic; full integration requires `SF_INSTANCE_URL` + `SF_ACCESS_TOKEN` (or the OAuth env vars).
