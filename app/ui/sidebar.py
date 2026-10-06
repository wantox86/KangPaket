"""
KangPaket — Sidebar: daftar profil grouped by collection,
search/filter, context menu (rename, duplicate, delete, move collection).
"""
from __future__ import annotations

import sys
import tkinter as tk
import tkinter.font as tkfont
import customtkinter as ctk

from app.config import METHOD_COLORS, SIDEBAR_WIDTH
from app.core.profile_manager import ProfileManager
from app.models.request_model import RequestProfile


# Layout constants for the canvas-drawn list (pixels)
_ROW_H = 28          # profile row height
_ROW_GAP = 1         # gap between profile rows
_HDR_H = 32          # collection header height
_HDR_GAP = 4         # gap above a collection header
_PAD_X = 4

_C_HDR_BG    = "#1e1e2e"
_C_HDR_TEXT  = "#94a3b8"
_C_HDR_HOVER = "#2a2a3e"
_C_ROW_TEXT  = "#e2e8f0"
_C_ROW_HOVER = "#2a3a5a"
_C_SELECTED  = "#2563eb"
_C_SELECTED_CLICK = "#1e3a5f"


class Sidebar(ctk.CTkFrame):
    """Daftar profil.

    List digambar langsung di satu ``tk.Canvas`` (item canvas, bukan widget
    per baris). Pada macOS/Tk 9 biaya map/layout ratusan widget CTk
    (apalagi di dalam CTkScrollableFrame) tumbuh super-linear: 100 baris
    ~50 detik, 600 baris hang. Canvas item tidak punya biaya itu.
    """

    def __init__(
        self,
        parent,
        profile_manager: ProfileManager,
        on_select: callable | None = None,
        on_new_request: callable | None = None,
        on_open_dialog: callable | None = None,
        on_run_collection: callable | None = None,
        on_delete: callable | None = None,
        on_delete_collection: callable | None = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, width=SIDEBAR_WIDTH, corner_radius=0, **kwargs)
        self.pack_propagate(False)

        self._pm                      = profile_manager
        self._on_select               = on_select             # callback(RequestProfile)
        self._on_new_request          = on_new_request        # callback()
        self._on_open_dialog          = on_open_dialog        # callback(profile)
        self._on_run_collection       = on_run_collection     # callback(collection_name)
        self._on_delete               = on_delete             # callback(profile_id: str)
        self._on_delete_collection    = on_delete_collection  # callback(deleted_ids: list[str])

        # Track collapsed state per collection
        self._collapsed: dict[str, bool] = {}
        # Track currently selected profile id
        self._selected_id: str | None = None
        # Track all rendered profile rows: id → canvas rect item id
        self._profile_btns: dict[str, int] = {}
        self._row_normal: dict[str, str] = {}      # id → warna normal row (untuk hover restore)
        self._hits: dict[int, dict] = {}           # canvas item id → hit record
        self._hover_rec: dict | None = None
        self._grouped: dict[str, list[RequestProfile]] = {}
        self._drawn_width = 0
        self._redraw_job: str | None = None

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
        self._f_hdr  = tkfont.Font(self, family="Segoe UI", size=11, weight="bold")
        self._f_row  = tkfont.Font(self, family="Segoe UI", size=11)
        self._f_badge = tkfont.Font(self, family="Segoe UI", size=9, weight="bold")
        self._f_btn  = tkfont.Font(self, family="Segoe UI", size=10)
        self._f_empty = tkfont.Font(self, family="Segoe UI", size=11)

        self._scrollbar = ctk.CTkScrollbar(self, orientation="vertical", command=self._canvas_yview)
        self._scrollbar.pack(side="right", fill="y")
        self._canvas = tk.Canvas(
            self, highlightthickness=0, bd=0, bg=self._canvas_bg(),
            yscrollcommand=self._scrollbar.set, yscrollincrement=_ROW_H // 2,
        )
        self._canvas.pack(side="left", fill="both", expand=True)

        c = self._canvas
        c.bind("<Configure>", self._on_canvas_configure)
        c.bind("<Motion>", self._on_motion)
        c.bind("<Leave>", lambda e: self._set_hover(None))
        c.bind("<ButtonRelease-1>", self._on_left_click)
        c.bind("<Button-2>" if self._is_mac() else "<Button-3>", self._on_right_click)
        if "linux" in sys.platform:
            c.bind("<Button-4>", lambda e: self._wheel(-3))
            c.bind("<Button-5>", lambda e: self._wheel(3))
        elif self._is_mac():
            c.bind("<MouseWheel>", lambda e: self._wheel(-e.delta))
        else:
            c.bind("<MouseWheel>", lambda e: self._wheel(-3 * (e.delta // 120 or (1 if e.delta > 0 else -1))))

    def _canvas_bg(self) -> str:
        return self._apply_appearance_mode(self.cget("fg_color"))

    def _set_appearance_mode(self, mode_string):
        super()._set_appearance_mode(mode_string)
        if hasattr(self, "_canvas"):
            self._canvas.configure(bg=self._canvas_bg())
            self._redraw()

    def _canvas_yview(self, *args) -> None:
        if self._content_h() > self._canvas.winfo_height():
            self._canvas.yview(*args)

    def _wheel(self, units: int) -> None:
        if self._content_h() > self._canvas.winfo_height():
            self._canvas.yview_scroll(int(units), "units")

    def _content_h(self) -> int:
        return getattr(self, "_total_h", 0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self, keep_selection: bool = True) -> None:
        """Reload semua profil dari disk dan re-render daftar."""
        self._grouped = self._pm.get_profiles_by_collection()
        self._redraw()

    def select_profile(self, profile_id: str) -> None:
        """Highlight a profile row as selected."""
        self._selected_id = profile_id
        for pid in self._profile_btns:
            self._set_row_color(pid, _C_SELECTED if pid == profile_id else self._canvas_bg())

    def get_collections(self) -> list[str]:
        return self._pm.get_collections()

    # ------------------------------------------------------------------
    # Render helpers
    # ------------------------------------------------------------------

    def _visible_groups(self) -> list[tuple[str, list[RequestProfile]]]:
        query = self._search_var.get().strip().lower() if hasattr(self, "_search_var") else ""
        out = []
        for collection, profiles in self._grouped.items():
            filtered = [
                p for p in profiles
                if not query
                or query in p.name.lower()
                or query in p.url.lower()
                or query in p.method.lower()
            ]
            if query and not filtered:
                continue
            out.append((collection, filtered))
        return out

    def _fit(self, text: str, font: tkfont.Font, max_w: int) -> str:
        if max_w <= 0:
            return ""
        if font.measure(text) <= max_w:
            return text
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if font.measure(text[:mid] + "…") <= max_w:
                lo = mid
            else:
                hi = mid - 1
        return text[:lo] + "…"

    def _redraw(self) -> None:
        """Gambar ulang seluruh list dari cache ``self._grouped`` (tanpa baca disk)."""
        if self._redraw_job is not None:
            try:
                self.after_cancel(self._redraw_job)
            except Exception:
                pass
            self._redraw_job = None

        c = self._canvas
        top = c.yview()[0]
        c.delete("all")
        self._profile_btns.clear()
        self._row_normal.clear()
        self._hits.clear()
        self._hover_rec = None

        w = c.winfo_width()
        if w <= 1:
            w = SIDEBAR_WIDTH - 16
        self._drawn_width = w
        bg = self._canvas_bg()

        groups = self._visible_groups()
        if not self._grouped:
            c.create_text(
                w // 2, 40, text="No profiles yet.\nClick + to start.",
                font=self._f_empty, fill="#888", justify="center",
            )
            self._total_h = 0
            c.configure(scrollregion=(0, 0, w, 0))
            return

        y = 0
        for collection, profiles in groups:
            y = self._draw_collection(y, w, collection, profiles, bg)
        self._total_h = y + 4
        c.configure(scrollregion=(0, 0, w, max(self._total_h, c.winfo_height())))
        c.yview_moveto(top)

    def _reg_hit(self, rec: dict, *item_ids: int) -> None:
        for i in item_ids:
            self._hits[i] = rec

    def _draw_collection(
        self, y: int, w: int, collection: str, profiles: list[RequestProfile], bg: str
    ) -> int:
        c = self._canvas
        is_collapsed = self._collapsed.get(collection, False)

        y += _HDR_GAP
        x0, x1 = _PAD_X, w - _PAD_X
        hdr_rect = c.create_rectangle(x0, y, x1, y + _HDR_H, fill=_C_HDR_BG, outline="")
        arrow = "▶" if is_collapsed else "▼"
        label = f"{arrow}  {collection}  ({len(profiles)})"
        text_x = x0 + 8
        text_w = (x1 - 62) - text_x
        hdr_text = c.create_text(
            text_x, y + _HDR_H // 2, text=self._fit(label, self._f_hdr, text_w),
            anchor="w", font=self._f_hdr, fill=_C_HDR_TEXT,
        )
        self._reg_hit(
            {"kind": "toggle", "collection": collection, "count": len(profiles),
             "rect": hdr_rect, "normal": _C_HDR_BG, "hover": _C_HDR_HOVER},
            hdr_rect, hdr_text,
        )

        # Small buttons on the right: ▶ run, × delete
        by0, by1 = y + 4, y + _HDR_H - 4
        for kind, glyph, color, hover, bx1 in (
            ("delete", "×", "#f87171", "#7f1d1d", x1 - 4),
            ("run",    "▶", "#49cc90", "#16a34a", x1 - 4 - 26),
        ):
            r = c.create_rectangle(bx1 - 24, by0, bx1, by1, fill=_C_HDR_BG, outline="")
            t = c.create_text(
                bx1 - 12, (by0 + by1) // 2, text=glyph, fill=color,
                font=self._f_btn if kind == "run" else self._f_hdr,
            )
            self._reg_hit(
                {"kind": kind, "collection": collection, "count": len(profiles),
                 "rect": r, "normal": _C_HDR_BG, "hover": hover},
                r, t,
            )
        # Right-click on header body/buttons -> collection menu (handled via record)

        y += _HDR_H
        if is_collapsed:
            return y

        y += 0
        for profile in profiles:
            y = self._draw_profile_row(y, w, profile, bg)
        return y + 4

    def _draw_profile_row(self, y: int, w: int, profile: RequestProfile, bg: str) -> int:
        c = self._canvas
        y += _ROW_GAP
        x0, x1 = _PAD_X, w - _PAD_X
        color = _C_SELECTED if profile.id == self._selected_id else bg
        rect = c.create_rectangle(x0, y, x1, y + _ROW_H, fill=color, outline="")
        mid = y + _ROW_H // 2
        badge = c.create_text(
            x0 + 18, mid, text=profile.method[:3], font=self._f_badge,
            fill=METHOD_COLORS.get(profile.method, "#61affe"),
        )
        name_x = x0 + 40
        name = c.create_text(
            name_x, mid, text=self._fit(profile.name, self._f_row, x1 - 6 - name_x),
            anchor="w", font=self._f_row, fill=_C_ROW_TEXT,
        )
        self._profile_btns[profile.id] = rect
        self._row_normal[profile.id] = color
        self._reg_hit(
            {"kind": "profile", "profile": profile, "rect": rect, "hover": _C_ROW_HOVER},
            rect, badge, name,
        )
        return y + _ROW_H

    def _set_row_color(self, pid: str, color: str) -> None:
        self._row_normal[pid] = color
        rect = self._profile_btns.get(pid)
        if rect is not None:
            self._canvas.itemconfigure(rect, fill=color)

    # ------------------------------------------------------------------
    # Canvas events (satu set binding untuk semua baris — tidak ada binding per item)
    # ------------------------------------------------------------------

    def _hit_at(self, event: tk.Event) -> dict | None:
        c = self._canvas
        x, y = c.canvasx(event.x), c.canvasy(event.y)
        for item in reversed(c.find_overlapping(x, y, x, y)):
            rec = self._hits.get(item)
            if rec is not None:
                return rec
        return None

    def _rec_normal(self, rec: dict) -> str:
        if rec["kind"] == "profile":
            return self._row_normal.get(rec["profile"].id, self._canvas_bg())
        return rec["normal"]

    def _set_hover(self, rec: dict | None) -> None:
        old = self._hover_rec
        if old is rec:
            return
        c = self._canvas
        if old is not None:
            c.itemconfigure(old["rect"], fill=self._rec_normal(old))
        if rec is not None:
            c.itemconfigure(rec["rect"], fill=rec["hover"])
        c.configure(cursor="hand2" if rec is not None else "")
        self._hover_rec = rec

    def _on_motion(self, event: tk.Event) -> None:
        self._set_hover(self._hit_at(event))

    def _on_left_click(self, event: tk.Event) -> None:
        rec = self._hit_at(event)
        if rec is None:
            return
        kind = rec["kind"]
        if kind == "profile":
            self._on_profile_click(rec["profile"])
        elif kind == "toggle":
            self._toggle_collection(rec["collection"])
        elif kind == "run":
            self._run_collection(rec["collection"])
        elif kind == "delete":
            self._delete_collection(rec["collection"])

    def _on_right_click(self, event: tk.Event) -> None:
        rec = self._hit_at(event)
        if rec is None:
            return
        if rec["kind"] == "profile":
            self._show_context_menu(event, rec["profile"])
        else:
            self._show_collection_menu(event, rec["collection"], rec["count"])

    def _on_canvas_configure(self, event: tk.Event) -> None:
        if event.width != self._drawn_width and self._redraw_job is None:
            self._redraw_job = self.after(30, self._redraw)

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
        self._redraw()
        if self._selected_id:
            self._highlight_selected()

    def _toggle_collection(self, collection: str) -> None:
        self._collapsed[collection] = not self._collapsed.get(collection, False)
        self._redraw()

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
            deleted_id = profile.id
            self._pm.delete_profile(deleted_id)
            if self._selected_id == deleted_id:
                self._selected_id = None
            self.refresh(keep_selection=False)
            if self._on_delete:
                self._on_delete(deleted_id)

    def _show_collection_menu(self, event: tk.Event, collection: str, count: int) -> None:
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label=f"Run '{collection}'",
            command=lambda: self._run_collection(collection),
        )
        menu.add_separator()
        menu.add_command(
            label=f"Delete Collection ({count} request{'s' if count != 1 else ''})",
            command=lambda: self._delete_collection(collection),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _delete_collection(self, collection: str) -> None:
        import tkinter.messagebox as mb
        profiles = self._pm.get_profiles_by_collection().get(collection, [])
        count = len(profiles)
        msg = (
            f"Delete collection '{collection}'?\n\n"
            f"This will permanently delete {count} request{'s' if count != 1 else ''}.\n"
            "This action cannot be undone."
        )
        if not mb.askyesno("Delete Collection", msg, icon="warning"):
            return

        deleted_ids = self._pm.delete_collection(collection)

        # Clear selection if active profile was in this collection
        if self._selected_id in deleted_ids:
            self._selected_id = None

        self.refresh(keep_selection=False)

        if self._on_delete_collection:
            self._on_delete_collection(deleted_ids)

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
        bg = self._canvas_bg()
        for pid in self._profile_btns:
            self._set_row_color(pid, _C_SELECTED_CLICK if pid == self._selected_id else bg)

    # ------------------------------------------------------------------
    # Utils
    # ------------------------------------------------------------------

    @staticmethod
    def _is_mac() -> bool:
        import sys
        return sys.platform == "darwin"
