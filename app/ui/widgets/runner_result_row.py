"""
KangPaket — RunnerResultRow widget.
Two states: collapsed (default) and expanded (click to toggle).
"""
from __future__ import annotations

import customtkinter as ctk

from app.config import METHOD_COLORS, status_color
from app.models.runner_model import RunItemResult

_STATUS_ICON  = {"success": "✅", "failed": "❌", "error": "⚠️",  "skipped": "⏭"}
_STATUS_COLOR = {"success": "#49cc90", "failed": "#f93e3e", "error": "#fca130", "skipped": "#64748b"}
_ROW_BG       = {"success": "#0d1f15", "failed": "#1f0d0d", "error": "#1f180d", "skipped": "#111118"}


class RunnerResultRow(ctk.CTkFrame):
    """
    One result row in the runner window.
    Clicking anywhere on the row toggles between collapsed and expanded.

    Parameters
    ----------
    on_open_main : callable(profile_id) — called when "Open in Main Window" is clicked
    """

    def __init__(
        self,
        parent,
        item: RunItemResult,
        index: int,
        on_open_main: callable | None = None,
        **kwargs,
    ) -> None:
        bg = _ROW_BG.get(item.status, "#111118")
        super().__init__(parent, corner_radius=6, fg_color=bg, **kwargs)

        self._item         = item
        self._index        = index
        self._on_open_main = on_open_main
        self._expanded     = False

        self._build_collapsed()

    # ------------------------------------------------------------------
    # Collapsed view
    # ------------------------------------------------------------------

    def _build_collapsed(self) -> None:
        self._collapsed_frame = ctk.CTkFrame(
            self, corner_radius=0, fg_color="transparent"
        )
        self._collapsed_frame.pack(fill="x", padx=6, pady=4)

        item = self._item
        status_color_val = _STATUS_COLOR.get(item.status, "#888")

        # Status icon
        ctk.CTkLabel(
            self._collapsed_frame,
            text=_STATUS_ICON.get(item.status, "?"),
            font=("Segoe UI", 13),
            width=28,
        ).pack(side="left")

        # Index
        ctk.CTkLabel(
            self._collapsed_frame,
            text=f"#{self._index}",
            font=("Segoe UI", 11),
            text_color="#64748b",
            width=32,
        ).pack(side="left")

        # Method badge
        method = getattr(item, "_method", "")
        if method:
            mc = METHOD_COLORS.get(method, "#61affe")
            ctk.CTkLabel(
                self._collapsed_frame,
                text=method[:4],
                font=("Segoe UI", 9, "bold"),
                text_color=mc,
                width=36,
            ).pack(side="left", padx=(2, 4))

        # Profile name
        ctk.CTkLabel(
            self._collapsed_frame,
            text=item.profile_name,
            font=("Segoe UI", 12),
            anchor="w",
            width=180,
        ).pack(side="left", padx=(0, 8))

        # Status code
        if item.status_code is not None:
            sc_color = status_color(item.status_code)
            ctk.CTkLabel(
                self._collapsed_frame,
                text=str(item.status_code),
                font=("Segoe UI", 12, "bold"),
                text_color=sc_color,
                width=48,
            ).pack(side="left")

        # Elapsed
        if item.elapsed_ms is not None:
            elapsed = f"{item.elapsed_ms:.0f}ms" if item.elapsed_ms < 1000 else f"{item.elapsed_ms/1000:.2f}s"
            ctk.CTkLabel(
                self._collapsed_frame,
                text=elapsed,
                font=("Segoe UI", 11),
                text_color="#64748b",
                width=60,
            ).pack(side="left")

        # Size
        if item.size_bytes is not None:
            if item.size_bytes < 1024:
                size_str = f"{item.size_bytes}B"
            elif item.size_bytes < 1024 * 1024:
                size_str = f"{item.size_bytes/1024:.1f}KB"
            else:
                size_str = f"{item.size_bytes/(1024*1024):.1f}MB"
            ctk.CTkLabel(
                self._collapsed_frame,
                text=size_str,
                font=("Segoe UI", 11),
                text_color="#64748b",
                width=56,
            ).pack(side="left")

        # Short failure message (right side)
        if item.status == "error" and item.error:
            short = item.error[:60] + ("…" if len(item.error) > 60 else "")
            ctk.CTkLabel(
                self._collapsed_frame,
                text=short,
                font=("Segoe UI", 10),
                text_color="#fca130",
                anchor="w",
            ).pack(side="left", padx=8, fill="x", expand=True)
        elif item.assertion_results:
            failed_a = [a for a in item.assertion_results if not a["passed"]]
            if failed_a:
                ctk.CTkLabel(
                    self._collapsed_frame,
                    text=f"assertion: {failed_a[0]['name']} FAILED",
                    font=("Segoe UI", 10),
                    text_color="#f93e3e",
                    anchor="w",
                ).pack(side="left", padx=8, fill="x", expand=True)

        # Expand indicator
        self._expand_arrow = ctk.CTkLabel(
            self._collapsed_frame,
            text="▶",
            font=("Segoe UI", 10),
            text_color="#64748b",
            width=16,
        )
        self._expand_arrow.pack(side="right", padx=4)

        # Bind click to toggle
        for widget in self._collapsed_frame.winfo_children():
            widget.bind("<Button-1>", self._on_click)
        self._collapsed_frame.bind("<Button-1>", self._on_click)
        self.bind("<Button-1>", self._on_click)

    # ------------------------------------------------------------------
    # Expanded view
    # ------------------------------------------------------------------

    def _build_expanded(self) -> None:
        self._expanded_frame = ctk.CTkFrame(
            self, corner_radius=0, fg_color="transparent"
        )
        self._expanded_frame.pack(fill="x", padx=10, pady=(0, 8))

        item = self._item

        # Error detail
        if item.error:
            ctk.CTkLabel(
                self._expanded_frame,
                text="Error:",
                font=("Segoe UI", 11, "bold"),
                text_color="#fca130",
                anchor="w",
            ).pack(fill="x", pady=(4, 2))
            err_box = ctk.CTkTextbox(
                self._expanded_frame,
                font=("Courier New", 11),
                height=60,
                wrap="word",
            )
            err_box.pack(fill="x")
            err_box.insert("1.0", item.error)
            err_box.configure(state="disabled")

        # Assertion table
        if item.assertion_results:
            ctk.CTkLabel(
                self._expanded_frame,
                text="Assertions:",
                font=("Segoe UI", 11, "bold"),
                anchor="w",
            ).pack(fill="x", pady=(8, 2))

            # Header
            hdr = ctk.CTkFrame(self._expanded_frame, corner_radius=0, fg_color="#1e1e2e")
            hdr.pack(fill="x")
            for text, w in [("Assertion", 280), ("Expected", 120), ("Actual", 120), ("Result", 70)]:
                ctk.CTkLabel(
                    hdr, text=text,
                    font=("Segoe UI", 10, "bold"),
                    width=w, anchor="w",
                ).pack(side="left", padx=6, pady=3)

            for a in item.assertion_results:
                row = ctk.CTkFrame(
                    self._expanded_frame, corner_radius=0, fg_color="transparent"
                )
                row.pack(fill="x", pady=1)
                result_icon  = "✅" if a["passed"] else "❌"
                result_color = "#49cc90" if a["passed"] else "#f93e3e"
                for text, w, color in [
                    (a["name"],     280, "#e2e8f0"),
                    (a["expected"], 120, "#94a3b8"),
                    (a["actual"],   120, "#94a3b8"),
                    (result_icon,    70, result_color),
                ]:
                    ctk.CTkLabel(
                        row, text=text, font=("Courier New", 10),
                        width=w, anchor="w", text_color=color,
                        wraplength=w - 8,
                    ).pack(side="left", padx=6, pady=2)

        # Open in Main Window button
        btn_row = ctk.CTkFrame(self._expanded_frame, corner_radius=0, fg_color="transparent")
        btn_row.pack(fill="x", pady=(8, 0))

        ctk.CTkButton(
            btn_row,
            text="Open in Main Window",
            width=160, height=28,
            font=("Segoe UI", 11),
            fg_color="#374151", hover_color="#4b5563",
            command=self._open_in_main,
        ).pack(side="left")

        ctk.CTkButton(
            btn_row,
            text="▲ Collapse",
            width=90, height=28,
            font=("Segoe UI", 11),
            fg_color="transparent", hover_color="#2a2a3e",
            command=self._on_click,
        ).pack(side="left", padx=8)

    # ------------------------------------------------------------------
    # Toggle & actions
    # ------------------------------------------------------------------

    def _on_click(self, _event=None) -> None:
        self._expanded = not self._expanded
        if self._expanded:
            self._expand_arrow.configure(text="▼")
            self._build_expanded()
        else:
            self._expand_arrow.configure(text="▶")
            if hasattr(self, "_expanded_frame"):
                self._expanded_frame.destroy()

    def _open_in_main(self) -> None:
        if self._on_open_main:
            self._on_open_main(self._item.profile_id)
