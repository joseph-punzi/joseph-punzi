#!/usr/bin/env bash
set -euo pipefail

python3 -m pip install --upgrade pyinstaller
pyinstaller --onefile --name release-notes-generator scripts/generate_release_notes_document.py

echo "Build complete."
echo "Executable path: dist/release-notes-generator"
