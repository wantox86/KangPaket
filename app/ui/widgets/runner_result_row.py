"""
KangPaket — RunnerResultRow widget.
Two states: collapsed (default) and expanded (click to toggle).
"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont

import customtkinter as ctk

from app.config import METHOD_COLORS, status_color
from app.models.runner_model import RunItemResult

_STATUS_ICON  = {"success": "✅", "failed": "❌", "error": "⚠️",  "skipped": "⏭"}
_STATUS_COLOR = {"success": "#49cc90", "failed": "#f93e3e", "error": "#fca130", "skipped": "#64748b"}
_ROW_BG       = {"success": "#0d1f15", "failed": "#1f0d0d", "error": "#1f180d", "skipped": "#111118"}


_FONTS: dict = {}


def _font(widget, spec: tuple) -> tkfont.Font:
    f = _FONTS.get(spec)
    if f is None:
        f = _FONTS[spec] = tkfont.Font(widget, family=spec[0], size=spec[1])
    return f


def _fit(text: str, font: tkfont.Font, max_w: int) -> str:
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


class _ArrowItem:
    """Expand/collapse arrow drawn on the row canvas; mimics CTkLabel.configure(text=...)."""

    def __init__(self, canvas: tk.Canvas) -> None:
        self._c = canvas
        self._id = canvas.create_text(0, 15, text="▶", anchor="e", font=("Segoe UI", 10), fill="#64748b")

    def place(self, width: int) -> None:
        self._c.coords(self._id, width - 8, 15)

    def configure(self, text: str) -> None:
        self._c.itemconfigure(self._id, text=text)


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
        # The collapsed line is ONE tk.Canvas with text items (not ~8 CTk labels):
        # many CTk widgets per row are super-linear on macOS/Tk 9.
        item = self._item
        bg = _ROW_BG.get(item.status, "#111118")
        c = tk.Canvas(self, height=30, highlightthickness=0, bd=0, bg=bg)
        c.pack(fill="x", padx=6, pady=4)
        self._collapsed_frame = c

        f_name = _font(self, ("Segoe UI", 12))
        x = 4
        c.create_text(x + 14, 15, text=_STATUS_ICON.get(item.status, "?"), font=("Segoe UI", 13))
        x += 28
        c.create_text(x + 16, 15, text=f"#{self._index}", font=("Segoe UI", 11), fill="#64748b")
        x += 32
        method = getattr(item, "_method", "")
        if method:
            c.create_text(x + 20, 15, text=method[:4], font=("Segoe UI", 9, "bold"),
                          fill=METHOD_COLORS.get(method, "#61affe"))
            x += 36 + 6
        c.create_text(x, 15, text=_fit(item.profile_name, f_name, 180), anchor="w",
                      font=("Segoe UI", 12), fill="#dce4ee")
        x += 180 + 8

        if item.status_code is not None:
            c.create_text(x + 24, 15, text=str(item.status_code), font=("Segoe UI", 12, "bold"),
                          fill=status_color(item.status_code))
            x += 48
        if item.elapsed_ms is not None:
            elapsed = f"{item.elapsed_ms:.0f}ms" if item.elapsed_ms < 1000 else f"{item.elapsed_ms/1000:.2f}s"
            c.create_text(x + 30, 15, text=elapsed, font=("Segoe UI", 11), fill="#64748b")
            x += 60
        if item.size_bytes is not None:
            if item.size_bytes < 1024:
                size_str = f"{item.size_bytes}B"
            elif item.size_bytes < 1024 * 1024:
                size_str = f"{item.size_bytes/1024:.1f}KB"
            else:
                size_str = f"{item.size_bytes/(1024*1024):.1f}MB"
            c.create_text(x + 28, 15, text=size_str, font=("Segoe UI", 11), fill="#64748b")
            x += 56

        if item.status == "error" and item.error:
            short = item.error[:60] + ("…" if len(item.error) > 60 else "")
            c.create_text(x + 8, 15, text=short, anchor="w", font=("Segoe UI", 10), fill="#fca130")
        elif item.assertion_results:
            failed_a = [a for a in item.assertion_results if not a["passed"]]
            if failed_a:
                c.create_text(x + 8, 15, text=f"assertion: {failed_a[0]['name']} FAILED",
                              anchor="w", font=("Segoe UI", 10), fill="#f93e3e")

        # Expand indicator (right edge; the message text above is clipped by it)
        self._expand_arrow = _ArrowItem(c)
        c.bind("<Configure>", lambda e: self._expand_arrow.place(e.width))
        c.bind("<Button-1>", self._on_click)
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
