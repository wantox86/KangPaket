"""
KangPaket — Sidebar: daftar profil grouped by collection,
search/filter, context menu (rename, duplicate, delete, move collection).
"""
from __future__ import annotations

import tkinter as tk
import customtkinter as ctk

from app.config import METHOD_COLORS, SIDEBAR_WIDTH
from app.core.profile_manager import ProfileManager
from app.models.request_model import RequestProfile


class Sidebar(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        profile_manager: ProfileManager,
        on_select: callable | None = None,
        on_new_request: callable | None = None,
        on_open_dialog: callable | None = None,
        on_run_collection: callable | None = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, width=SIDEBAR_WIDTH, corner_radius=0, **kwargs)
        self.pack_propagate(False)

        self._pm                 = profile_manager
        self._on_select          = on_select           # callback(RequestProfile)
        self._on_new_request     = on_new_request      # callback()
        self._on_open_dialog     = on_open_dialog      # callback(profile)
        self._on_run_collection  = on_run_collection   # callback(collection_name)

        # Track collapsed state per collection
        self._collapsed: dict[str, bool] = {}
        # Track currently selected profile id
        self._selected_id: str | None = None
        # Track all rendered profile buttons: id → CTkButton
        self._profile_btns: dict[str, ctk.CTkButton] = {}

        self._build_header()
        self._build_search()
        self._build_list_area()
        self.refresh()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_header(self) -> None:
        hdr = ctk.CTkFrame(self, corner_radius=0, height=40)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        ctk.CTkLabel(
            hdr, text="Requests",
            font=("Segoe UI", 13, "bold"), anchor="w",
        ).pack(side="left", padx=10, pady=8)

        ctk.CTkButton(
            hdr, text="+", width=28, height=28,
            font=("Segoe UI", 15, "bold"),
            fg_color="#2563eb", hover_color="#1d4ed8",
            command=self._on_new_request,
        ).pack(side="right", padx=6, pady=6)

        ctk.CTkFrame(self, height=1, corner_radius=0, fg_color="#333").pack(fill="x")

    def _build_search(self) -> None:
        search_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        search_frame.pack(fill="x", padx=6, pady=4)

        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._on_search_change())
        ctk.CTkEntry(
            search_frame,
            textvariable=self._search_var,
            placeholder_text="🔍  Search profiles…",
            height=28,
            font=("Segoe UI", 11),
        ).pack(fill="x")

    def _build_list_area(self) -> None:
        self._scroll = ctk.CTkScrollableFrame(
            self, corner_radius=0, fg_color="transparent"
        )
        self._scroll.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self, keep_selection: bool = True) -> None:
        """Reload semua profil dari disk dan re-render daftar."""
        self._profile_btns.clear()
        for widget in self._scroll.winfo_children():
            widget.destroy()

        query   = self._search_var.get().strip().lower() if hasattr(self, "_search_var") else ""
        grouped = self._pm.get_profiles_by_collection()

        if not grouped:
            ctk.CTkLabel(
                self._scroll,
                text="No profiles yet.\nClick + to start.",
                font=("Segoe UI", 11),
                text_color="#888",
                justify="center",
            ).pack(pady=24)
            return

        for collection, profiles in grouped.items():
            # Apply search filter
            filtered = [
                p for p in profiles
                if not query
                or query in p.name.lower()
                or query in p.url.lower()
                or query in p.method.lower()
            ]
            if query and not filtered:
                continue
            self._render_collection(collection, filtered)

    def select_profile(self, profile_id: str) -> None:
        """Highlight a profile row as selected."""
        self._selected_id = profile_id
        for pid, btn in self._profile_btns.items():
            if pid == profile_id:
                btn.configure(fg_color="#2563eb")
            else:
                btn.configure(fg_color="transparent")

    def get_collections(self) -> list[str]:
        return self._pm.get_collections()

    # ------------------------------------------------------------------
    # Render helpers
    # ------------------------------------------------------------------

    def _render_collection(
        self, collection: str, profiles: list[RequestProfile]
    ) -> None:
        is_collapsed = self._collapsed.get(collection, False)

        # Collection header row
        hdr = ctk.CTkFrame(self._scroll, corner_radius=4, fg_color="#1e1e2e")
        hdr.pack(fill="x", padx=4, pady=(4, 0))

        arrow = "▶" if is_collapsed else "▼"
        col_btn = ctk.CTkButton(
            hdr,
            text=f"{arrow}  {collection}  ({len(profiles)})",
            anchor="w",
            font=("Segoe UI", 11, "bold"),
            fg_color="transparent",
            hover_color="#2a2a3e",
            text_color="#94a3b8",
            height=28,
            command=lambda c=collection: self._toggle_collection(c),
        )
        col_btn.pack(side="left", fill="x", expand=True, padx=2)

        # Run collection button (▶)
        ctk.CTkButton(
            hdr,
            text="▶",
            width=24, height=24,
            font=("Segoe UI", 10),
            fg_color="transparent",
            hover_color="#16a34a",
            text_color="#49cc90",
            command=lambda c=collection: self._run_collection(c),
        ).pack(side="right", padx=2)

        if is_collapsed:
            return

        # Profile rows
        items_frame = ctk.CTkFrame(self._scroll, corner_radius=0, fg_color="transparent")
        items_frame.pack(fill="x", padx=4, pady=(0, 4))

        for profile in profiles:
            self._render_profile_row(items_frame, profile)

    def _render_profile_row(
        self, parent: ctk.CTkFrame, profile: RequestProfile
    ) -> None:
        is_selected = profile.id == self._selected_id
        row_color   = "#2563eb" if is_selected else "transparent"

        row = ctk.CTkFrame(parent, corner_radius=4, fg_color=row_color)
        row.pack(fill="x", pady=1)

        # Method badge (small colored label)
        method_color = METHOD_COLORS.get(profile.method, "#61affe")
        badge = ctk.CTkLabel(
            row,
            text=profile.method[:3],  # "GET", "POS", "PUT"…
            font=("Segoe UI", 9, "bold"),
            text_color=method_color,
            width=28,
            anchor="center",
        )
        badge.pack(side="left", padx=(4, 0), pady=4)

        # Profile name button
        btn = ctk.CTkButton(
            row,
            text=profile.name,
            anchor="w",
            font=("Segoe UI", 11),
            fg_color="transparent",
            hover_color="#2a3a5a",
            text_color="#e2e8f0",
            height=28,
            command=lambda p=profile: self._on_profile_click(p),
        )
        btn.pack(side="left", fill="x", expand=True)
        self._profile_btns[profile.id] = row  # track the row frame for highlight

        # Right-click context menu
        for widget in (row, badge, btn):
            widget.bind(
                "<Button-2>" if self._is_mac() else "<Button-3>",
                lambda event, p=profile: self._show_context_menu(event, p),
            )

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_context_menu(self, event: tk.Event, profile: RequestProfile) -> None:
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label="Open",
            command=lambda: self._on_profile_click(profile),
        )
        menu.add_separator()
        menu.add_command(
            label="Rename…",
            command=lambda: self._rename_profile(profile),
        )
        menu.add_command(
            label="Duplicate",
            command=lambda: self._duplicate_profile(profile),
        )
        menu.add_command(
            label="Move to Collection…",
            command=lambda: self._move_collection(profile),
        )
        menu.add_separator()
        menu.add_command(
            label="Delete",
            command=lambda: self._delete_profile(profile),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_profile_click(self, profile: RequestProfile) -> None:
        self._selected_id = profile.id
        self._highlight_selected()
        if self._on_select:
            self._on_select(profile)

    def _on_search_change(self) -> None:
        self.refresh(keep_selection=True)
        if self._selected_id:
            self._highlight_selected()

    def _toggle_collection(self, collection: str) -> None:
        self._collapsed[collection] = not self._collapsed.get(collection, False)
        self.refresh(keep_selection=True)

    def _rename_profile(self, profile: RequestProfile) -> None:
        from app.ui.profile_dialog import ProfileDialog
        dialog = ProfileDialog(
            self.winfo_toplevel(),
            title="Rename Profil",
            initial_name=profile.name,
            initial_collection=profile.collection,
            collections=self.get_collections(),
        )
        self.wait_window(dialog)
        if dialog.confirmed:
            profile.name       = dialog.name
            profile.collection = dialog.collection
            self._pm.save_profile(profile)
            self.refresh(keep_selection=True)

    def _duplicate_profile(self, profile: RequestProfile) -> None:
        new_profile = self._pm.duplicate_profile(profile)
        self.refresh(keep_selection=True)
        self._on_profile_click(new_profile)

    def _delete_profile(self, profile: RequestProfile) -> None:
        import tkinter.messagebox as mb
        if mb.askyesno(
            "Delete Profile",
            f"Delete '{profile.name}'?\nThis action cannot be undone.",
            icon="warning",
        ):
            self._pm.delete_profile(profile.id)
            if self._selected_id == profile.id:
                self._selected_id = None
            self.refresh(keep_selection=False)

    def _run_collection(self, collection: str) -> None:
        if self._on_run_collection:
            self._on_run_collection(collection)

    def _move_collection(self, profile: RequestProfile) -> None:
        from app.ui.profile_dialog import ProfileDialog
        dialog = ProfileDialog(
            self.winfo_toplevel(),
            title="Pindah Collection",
            initial_name=profile.name,
            initial_collection=profile.collection,
            collections=self.get_collections(),
        )
        self.wait_window(dialog)
        if dialog.confirmed:
            profile.collection = dialog.collection
            self._pm.save_profile(profile)
            self.refresh(keep_selection=True)

    # ------------------------------------------------------------------
    # Highlight
    # ------------------------------------------------------------------

    def _highlight_selected(self) -> None:
        for pid, row_frame in self._profile_btns.items():
            if pid == self._selected_id:
                row_frame.configure(fg_color="#1e3a5f")
            else:
                row_frame.configure(fg_color="transparent")

    # ------------------------------------------------------------------
    # Utils
    # ------------------------------------------------------------------

    @staticmethod
    def _is_mac() -> bool:
        import sys
        return sys.platform == "darwin"
