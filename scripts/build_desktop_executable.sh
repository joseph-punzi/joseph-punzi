#!/usr/bin/env bash
set -euo pipefail

python3 -m pip install --upgrade pyinstaller
pyinstaller --onefile --windowed --name release-notes-generator-ui scripts/release_notes_gui.py
pyinstaller --onefile --name release-notes-generator-cli scripts/generate_release_notes_document.py

echo "Build complete."
echo "UI executable:  dist/release-notes-generator-ui"
echo "CLI executable: dist/release-notes-generator-cli"
