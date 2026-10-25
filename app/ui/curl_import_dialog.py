"""
KangPaket — Import from cURL dialog.
Paste a cURL command, pick a target collection, confirm. Parsing lives in
app/core/curl_import.py; this dialog only collects input and shows errors/warnings.
"""
from __future__ import annotations

import customtkinter as ctk

from app.core.curl_import import CurlImportResult, CurlParseError, parse_curl


class CurlImportDialog(ctk.CTkToplevel):
    """
    Modal dialog. After it closes:
        dialog.result      -> CurlImportResult | None  (None = cancelled)
        dialog.collection  -> str  (target collection)
    """

    def __init__(self, parent, collections: list[str], default_collection: str = "Default") -> None:
        super().__init__(parent)
        self.title("Import from cURL")
        self.geometry("640x460")
        self.minsize(520, 380)
        self.grab_set()
        self.focus_set()

        self.result: CurlImportResult | None = None
        self.collection = default_collection

        # Bottom bar first: keeps the buttons visible however small the window gets.
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(side="bottom", fill="x", padx=12, pady=(4, 12))
        ctk.CTkButton(bar, text="Import", width=0, command=self._import).pack(side="right")
        ctk.CTkButton(
            bar, text="Cancel", width=0, fg_color="transparent", border_width=1,
            text_color=("gray10", "gray90"), command=self.destroy,
        ).pack(side="right", padx=(0, 8))

        coll = ctk.CTkFrame(self, fg_color="transparent")
        coll.pack(side="bottom", fill="x", padx=12, pady=(4, 0))
        ctk.CTkLabel(coll, text="Collection:", font=("Segoe UI", 12)).pack(side="left", padx=(0, 8))
        self._coll_var = ctk.StringVar(value=default_collection)
        ctk.CTkComboBox(
            coll, variable=self._coll_var, values=collections or [default_collection], width=260,
        ).pack(side="left")

        self._msg = ctk.CTkLabel(
            self, text="", font=("Segoe UI", 11), anchor="w", justify="left", wraplength=600,
        )
        self._msg.pack(side="bottom", fill="x", padx=12, pady=(4, 0))

        ctk.CTkLabel(
            self,
            text="Paste a cURL command (e.g. Chrome/Firefox \"Copy as cURL (bash)\"). "
                 "It is only parsed, never executed.",
            font=("Segoe UI", 11), text_color="#94a3b8", anchor="w", justify="left", wraplength=600,
        ).pack(side="top", fill="x", padx=12, pady=(12, 4))

        self._text = ctk.CTkTextbox(self, font=("Courier New", 12), wrap="none")
        self._text.pack(side="top", fill="both", expand=True, padx=12)
        self._text.focus_set()

        self.bind("<Escape>", lambda _: self.destroy())

    def _import(self) -> None:
        try:
            res = parse_curl(self._text.get("1.0", "end"))
        except CurlParseError as e:
            self._msg.configure(text=f"Cannot import: {e}", text_color="#f93e3e")
            return
        self.result = res
        self.collection = self._coll_var.get().strip() or "Default"
        self.destroy()
