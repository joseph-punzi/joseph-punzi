#!/usr/bin/env python3
"""Simple desktop UI for generating Salesforce release notes documents."""

from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from generate_release_notes_document import (
    DEFAULT_API_VERSION,
    DEFAULT_AUTH_TIMEOUT_SECONDS,
    DEFAULT_LOGIN_URL,
    DEFAULT_REDIRECT_HOST,
    DEFAULT_REDIRECT_PORT,
    SalesforceClient,
    default_output_path,
    generate_release_notes_document,
)


DEFAULT_RELEASE_NOTE_OBJECT = "Release_Note__c"
DEFAULT_RELEASE_LOOKUP_FIELD = "Release__r.Name"
DEFAULT_ACCOUNT_FIELD = "Account__c"
DEFAULT_NAME_FIELD = "Name"
DEFAULT_DETAILS_FIELD = "Details__c"


class ReleaseNotesGui:
    """Small Tkinter form to run browser-auth release note generation."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Release Notes Generator")
        self.root.geometry("760x460")
        self.root.minsize(700, 430)

        self.release_name_var = tk.StringVar()
        self.account_id_var = tk.StringVar()
        self.client_id_var = tk.StringVar(value=os.getenv("SF_CLIENT_ID", ""))
        self.login_url_var = tk.StringVar(
            value=os.getenv("SF_LOGIN_URL", DEFAULT_LOGIN_URL)
        )
        self.output_path_var = tk.StringVar()
        self.redirect_port_var = tk.StringVar(value=str(DEFAULT_REDIRECT_PORT))
        self.timeout_var = tk.StringVar(value=str(DEFAULT_AUTH_TIMEOUT_SECONDS))
        self.open_browser_var = tk.BooleanVar(value=True)

        self.generate_button: Optional[ttk.Button] = None
        self.status_text: Optional[tk.Text] = None
        self._build_ui()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        for col_idx in (0, 1, 2):
            frame.columnconfigure(col_idx, weight=1 if col_idx == 1 else 0)

        row = 0
        ttk.Label(frame, text="Release Name *").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.release_name_var, width=52).grid(
            row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=4
        )

        row += 1
        ttk.Label(frame, text="Account ID (optional)").grid(
            row=row, column=0, sticky="w", pady=4
        )
        ttk.Entry(frame, textvariable=self.account_id_var).grid(
            row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=4
        )

        row += 1
        ttk.Label(frame, text="Salesforce Client ID *").grid(
            row=row, column=0, sticky="w", pady=4
        )
        ttk.Entry(frame, textvariable=self.client_id_var).grid(
            row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=4
        )

        row += 1
        ttk.Label(frame, text="Salesforce Login URL").grid(
            row=row, column=0, sticky="w", pady=4
        )
        ttk.Entry(frame, textvariable=self.login_url_var).grid(
            row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=4
        )

        row += 1
        ttk.Label(frame, text="Output File").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.output_path_var).grid(
            row=row, column=1, sticky="ew", padx=(8, 8), pady=4
        )
        ttk.Button(frame, text="Browse...", command=self._choose_output_file).grid(
            row=row, column=2, sticky="e", pady=4
        )

        row += 1
        advanced_label = ttk.Label(
            frame, text="Advanced", font=("TkDefaultFont", 10, "bold")
        )
        advanced_label.grid(row=row, column=0, sticky="w", pady=(10, 4))

        row += 1
        ttk.Label(frame, text="Redirect Port").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.redirect_port_var, width=10).grid(
            row=row, column=1, sticky="w", padx=(8, 0), pady=4
        )

        row += 1
        ttk.Label(frame, text="Auth Timeout (seconds)").grid(
            row=row, column=0, sticky="w", pady=4
        )
        ttk.Entry(frame, textvariable=self.timeout_var, width=10).grid(
            row=row, column=1, sticky="w", padx=(8, 0), pady=4
        )

        row += 1
        ttk.Checkbutton(
            frame,
            text="Open browser automatically",
            variable=self.open_browser_var,
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=4)

        row += 1
        self.generate_button = ttk.Button(
            frame,
            text="Generate Release Notes Document",
            command=self._on_generate,
        )
        self.generate_button.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(12, 8))

        row += 1
        ttk.Label(frame, text="Status").grid(row=row, column=0, sticky="w")

        row += 1
        self.status_text = tk.Text(frame, height=10, wrap="word", state="disabled")
        self.status_text.grid(row=row, column=0, columnspan=3, sticky="nsew", pady=(4, 0))
        frame.rowconfigure(row, weight=1)

        self._log(
            "Ready. Enter release/account and Salesforce client ID, then click Generate."
        )

    def _choose_output_file(self) -> None:
        release_name = self.release_name_var.get().strip()
        account_id = self.account_id_var.get().strip() or None
        suggested = default_output_path(release_name or "release", account_id)
        selected = filedialog.asksaveasfilename(
            title="Save release notes document as...",
            defaultextension=".md",
            filetypes=[("Markdown files", "*.md"), ("All files", "*.*")],
            initialfile=suggested,
        )
        if selected:
            self.output_path_var.set(selected)

    def _set_busy(self, busy: bool) -> None:
        if self.generate_button is not None:
            state = "disabled" if busy else "normal"
            self.generate_button.configure(state=state)

    def _log(self, message: str) -> None:
        if self.status_text is None:
            return
        self.status_text.configure(state="normal")
        self.status_text.insert("end", f"{message}\n")
        self.status_text.see("end")
        self.status_text.configure(state="disabled")

    def _on_generate(self) -> None:
        release_name = self.release_name_var.get().strip()
        client_id = self.client_id_var.get().strip()
        account_id = self.account_id_var.get().strip() or None
        login_url = self.login_url_var.get().strip() or DEFAULT_LOGIN_URL
        output_path = self.output_path_var.get().strip() or None

        if not release_name:
            messagebox.showerror("Missing value", "Release Name is required.")
            return
        if not client_id:
            messagebox.showerror("Missing value", "Salesforce Client ID is required.")
            return

        try:
            redirect_port = int(self.redirect_port_var.get().strip())
            timeout_seconds = int(self.timeout_var.get().strip())
            if redirect_port < 1 or redirect_port > 65535:
                raise ValueError("Port out of range")
            if timeout_seconds < 30:
                raise ValueError("Timeout too small")
        except ValueError:
            messagebox.showerror(
                "Invalid advanced settings",
                "Redirect Port must be 1-65535 and timeout must be at least 30 seconds.",
            )
            return

        self._set_busy(True)
        self._log("Starting Salesforce browser login...")

        worker = threading.Thread(
            target=self._generate_in_background,
            args=(
                release_name,
                account_id,
                client_id,
                login_url,
                output_path,
                redirect_port,
                timeout_seconds,
                self.open_browser_var.get(),
            ),
            daemon=True,
        )
        worker.start()

    def _generate_in_background(
        self,
        release_name: str,
        account_id: Optional[str],
        client_id: str,
        login_url: str,
        output_path: Optional[str],
        redirect_port: int,
        timeout_seconds: int,
        open_browser: bool,
    ) -> None:
        try:
            client = SalesforceClient.from_browser_oauth(
                api_version=DEFAULT_API_VERSION,
                client_id=client_id,
                login_url=login_url,
                redirect_host=DEFAULT_REDIRECT_HOST,
                redirect_port=redirect_port,
                timeout_seconds=timeout_seconds,
                open_browser=open_browser,
            )
            self._queue_log("Salesforce authentication successful. Querying release notes...")
            written_path, record_count = generate_release_notes_document(
                client=client,
                release_name=release_name,
                account_id=account_id,
                output_path=output_path,
                release_note_object=DEFAULT_RELEASE_NOTE_OBJECT,
                release_lookup_field=DEFAULT_RELEASE_LOOKUP_FIELD,
                account_field=DEFAULT_ACCOUNT_FIELD,
                name_field=DEFAULT_NAME_FIELD,
                details_field=DEFAULT_DETAILS_FIELD,
            )
        except Exception as exc:  # pragma: no cover
            self._queue_error(str(exc))
            return

        self._queue_success(written_path, record_count)

    def _queue_log(self, message: str) -> None:
        self.root.after(0, lambda: self._log(message))

    def _queue_error(self, error_message: str) -> None:
        def _show() -> None:
            self._set_busy(False)
            self._log(f"ERROR: {error_message}")
            messagebox.showerror("Generation failed", error_message)

        self.root.after(0, _show)

    def _queue_success(self, output_path: str, record_count: int) -> None:
        def _show() -> None:
            self._set_busy(False)
            self.output_path_var.set(output_path)
            self._log(f"Done. Wrote {record_count} release notes to: {output_path}")
            messagebox.showinfo(
                "Document generated",
                f"Wrote {record_count} release notes to:\n{output_path}",
            )

        self.root.after(0, _show)


def main() -> int:
    root = tk.Tk()
    app = ReleaseNotesGui(root)
    del app  # retained by Tkinter callbacks
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
