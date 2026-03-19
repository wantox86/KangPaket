"""
KangPaket — Postman Import Dialog.
Preview parsed requests, select/deselect items, choose target collection, confirm import.
"""
from __future__ import annotations

import customtkinter as ctk
import tkinter as tk

from app.core.postman_importer import PostmanImportResult
from app.core.profile_manager import ProfileManager
from app.models.request_model import RequestProfile
from app.config import METHOD_COLORS


class PostmanImportDialog(ctk.CTkToplevel):
    """
    Modal dialog shown after a Postman collection file is successfully parsed.

    After closing:
        dialog.imported_count -> int   (0 if cancelled)
        dialog.target_collection -> str
    """

    def __init__(
        self,
        parent,
        file_path: str,
        result: PostmanImportResult,
        profile_manager: ProfileManager,
        on_import_done: callable | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("Import from Postman Collection")
        self.geometry("680x640")
        self.minsize(580, 500)
        self.grab_set()
        self.focus_set()

        self._file_path      = file_path
        self._result         = result
        self._pm             = profile_manager
        self._on_import_done = on_import_done

        self.imported_count     = 0
        self.target_collection  = result.collection_name

        # Per-profile checkbox vars: index → BooleanVar
        self._check_vars: list[tuple[RequestProfile, ctk.BooleanVar]] = []
        self._warnings_expanded = False

        self._build()

        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width() // 2 - 340
        ph = parent.winfo_rooty() + parent.winfo_height() // 2 - 320
        self.geometry(f"680x640+{pw}+{ph}")

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _: self._cancel())

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        r = self._result

        # ── Header info ────────────────────────────────────────────────
        info_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#111118")
        info_frame.pack(fill="x", padx=0, pady=0)

        import os
        filename = os.path.basename(self._file_path)

        rows = [
            ("File",        filename),
            ("Collection",  r.collection_name),
            ("Found",       f"{r.total_items} request(s)"),
        ]
        for label, value in rows:
            row = ctk.CTkFrame(info_frame, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=2)
            ctk.CTkLabel(row, text=f"{label}:", width=90, anchor="w",
                         font=("Segoe UI", 11), text_color="#64748b").pack(side="left")
            ctk.CTkLabel(row, text=value, anchor="w",
                         font=("Segoe UI", 11)).pack(side="left")

        # Target collection selector
        col_row = ctk.CTkFrame(info_frame, fg_color="transparent")
        col_row.pack(fill="x", padx=16, pady=(4, 8))
        ctk.CTkLabel(col_row, text="Import to:", width=90, anchor="w",
                     font=("Segoe UI", 11), text_color="#64748b").pack(side="left")

        existing_cols = self._pm.get_collections() or []
        default_cols  = sorted(set(existing_cols + [r.collection_name]))

        self._target_col_var = ctk.StringVar(value=r.collection_name)
        ctk.CTkOptionMenu(
            col_row,
            variable=self._target_col_var,
            values=default_cols,
            width=200, height=26,
            font=("Segoe UI", 11),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(col_row, text="or type new:",
                     font=("Segoe UI", 10), text_color="#888").pack(side="left", padx=(0, 4))
        self._new_col_var = ctk.StringVar()
        ctk.CTkEntry(col_row, textvariable=self._new_col_var,
                     placeholder_text="New collection name",
                     height=26, font=("Segoe UI", 11), width=160).pack(side="left")

        ctk.CTkFrame(self, height=1, fg_color="#333").pack(fill="x")

        # ── Preview list ───────────────────────────────────────────────
        list_hdr = ctk.CTkFrame(self, fg_color="transparent")
        list_hdr.pack(fill="x", padx=12, pady=(6, 2))

        ctk.CTkLabel(list_hdr, text="PREVIEW REQUEST",
                     font=("Segoe UI", 10, "bold"), text_color="#64748b").pack(side="left")

        ctk.CTkButton(
            list_hdr, text="All", width=54, height=22,
            font=("Segoe UI", 10), fg_color="#374151", hover_color="#4b5563",
            command=lambda: self._select_all(True),
        ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(
            list_hdr, text="None", width=54, height=22,
            font=("Segoe UI", 10), fg_color="#374151", hover_color="#4b5563",
            command=lambda: self._select_all(False),
        ).pack(side="right")

        self._list_scroll = ctk.CTkScrollableFrame(
            self, corner_radius=0, fg_color="transparent", height=240
        )
        self._list_scroll.pack(fill="x", padx=8, pady=(0, 4))

        self._populate_list()

        ctk.CTkFrame(self, height=1, fg_color="#333").pack(fill="x")

        # ── Warnings section ───────────────────────────────────────────
        warn_count = len(self._result.warnings) + len(self._result.skipped)
        self._warn_toggle_btn = ctk.CTkButton(
            self,
            text=f"▶  WARNINGS ({warn_count})" if warn_count else "No warnings",
            anchor="w",
            font=("Segoe UI", 10, "bold"),
            fg_color="transparent",
            hover_color="#2a2a3e",
            text_color="#fca130" if warn_count else "#64748b",
            height=28,
            command=self._toggle_warnings,
            state="normal" if warn_count else "disabled",
        )
        self._warn_toggle_btn.pack(fill="x", padx=8, pady=(4, 0))

        self._warn_box = ctk.CTkTextbox(
            self, font=("Segoe UI", 10), height=90, wrap="word", state="disabled"
        )
        # Hidden by default

        ctk.CTkFrame(self, height=1, fg_color="#333").pack(fill="x", pady=(4, 0))

        # ── Footer buttons ─────────────────────────────────────────────
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=16, pady=10)

        ctk.CTkButton(
            footer, text="Cancel", width=90, height=34,
            fg_color="#374151", hover_color="#4b5563",
            command=self._cancel,
        ).pack(side="right", padx=(8, 0))

        self._import_btn = ctk.CTkButton(
            footer,
            text=self._import_btn_label(),
            width=160, height=34,
            font=("Segoe UI", 12, "bold"),
            fg_color="#2563eb", hover_color="#1d4ed8",
            command=self._do_import,
        )
        self._import_btn.pack(side="right")

    # ------------------------------------------------------------------
    # List population
    # ------------------------------------------------------------------

    def _populate_list(self) -> None:
        r = self._result

        # Skipped items (grey, disabled)
        for skip_name in r.skipped:
            row = ctk.CTkFrame(self._list_scroll, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkCheckBox(row, text="", state="disabled", width=24,
                            checkbox_width=16, checkbox_height=16).pack(side="left")
            ctk.CTkLabel(row, text="❌", width=20, font=("Segoe UI", 11)).pack(side="left")
            ctk.CTkLabel(row, text=skip_name, font=("Segoe UI", 11),
                         text_color="#64748b", anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(row, text="cannot be converted",
                         font=("Segoe UI", 9), text_color="#ef4444").pack(side="left", padx=4)

        # Valid profiles
        for profile in r.profiles:
            has_warning = self._profile_has_warning(profile)
            icon        = "⚠️" if has_warning else "✅"

            var = ctk.BooleanVar(value=True)
            var.trace_add("write", lambda *_: self._update_import_btn())

            row = ctk.CTkFrame(self._list_scroll, fg_color="transparent")
            row.pack(fill="x", pady=1)

            ctk.CTkCheckBox(
                row, text="", variable=var, width=24,
                checkbox_width=16, checkbox_height=16,
            ).pack(side="left")

            ctk.CTkLabel(row, text=icon, width=20, font=("Segoe UI", 11)).pack(side="left")

            mc = METHOD_COLORS.get(profile.method, "#61affe")
            ctk.CTkLabel(
                row, text=profile.method[:4],
                font=("Segoe UI", 9, "bold"), text_color=mc, width=34,
            ).pack(side="left")

            ctk.CTkLabel(
                row, text=profile.name,
                font=("Segoe UI", 11), anchor="w",
            ).pack(side="left", fill="x", expand=True)

            if has_warning:
                ctk.CTkLabel(
                    row, text="⚠ var/script",
                    font=("Segoe UI", 9), text_color="#fca130",
                ).pack(side="right", padx=4)

            self._check_vars.append((profile, var))

    def _profile_has_warning(self, profile: RequestProfile) -> bool:
        """Check if any warning message references this profile name."""
        return any(
            f"'{profile.name}'" in w or profile.url and "{{" in profile.url
            for w in self._result.warnings
        )

    # ------------------------------------------------------------------
    # Warnings toggle
    # ------------------------------------------------------------------

    def _toggle_warnings(self) -> None:
        self._warnings_expanded = not self._warnings_expanded
        if self._warnings_expanded:
            self._warn_toggle_btn.configure(
                text=self._warn_toggle_btn.cget("text").replace("▶", "▼")
            )
            self._warn_box.pack(fill="x", padx=8, pady=(0, 4))
            self._warn_box.configure(state="normal")
            self._warn_box.delete("1.0", "end")

            lines = []
            for w in self._result.warnings:
                lines.append(f"• {w}")
            for s in self._result.skipped:
                lines.append(f"• Skip: '{s}'")
            self._warn_box.insert("1.0", "\n".join(lines))
            self._warn_box.configure(state="disabled")
        else:
            self._warn_toggle_btn.configure(
                text=self._warn_toggle_btn.cget("text").replace("▼", "▶")
            )
            self._warn_box.pack_forget()

    # ------------------------------------------------------------------
    # Select helpers
    # ------------------------------------------------------------------

    def _select_all(self, value: bool) -> None:
        for _, var in self._check_vars:
            var.set(value)
        self._update_import_btn()

    def _selected_profiles(self) -> list[RequestProfile]:
        return [p for p, var in self._check_vars if var.get()]

    def _import_btn_label(self) -> str:
        n = len(self._selected_profiles())
        return f"Import {n} Request(s)" if n > 0 else "Import (0 selected)"

    def _update_import_btn(self) -> None:
        selected = self._selected_profiles()
        label    = self._import_btn_label()
        state    = "normal" if selected else "disabled"
        self._import_btn.configure(text=label, state=state)

    # ------------------------------------------------------------------
    # Import action
    # ------------------------------------------------------------------

    def _do_import(self) -> None:
        selected = self._selected_profiles()
        if not selected:
            return

        # Determine target collection
        new_col = self._new_col_var.get().strip()
        target  = new_col if new_col else self._target_col_var.get().strip()
        if not target:
            target = self._result.collection_name

        # Override collection on all selected profiles
        for profile in selected:
            profile.collection = target
            self._pm.save_profile(profile)

        self.imported_count    = len(selected)
        self.target_collection = target

        if self._on_import_done:
            self._on_import_done(self.imported_count, target)

        self.destroy()

    def _cancel(self) -> None:
        self.imported_count = 0
        self.destroy()
