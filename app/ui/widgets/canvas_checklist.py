"""
KangPaket — CanvasChecklist: scrollable checklist drawn on a single tk.Canvas.

Per-row CTk widgets are super-linear on macOS/Tk 9 (50 rows ~4s, 600 rows
hang), so rows are drawn as canvas items instead. State lives in the
``BooleanVar`` passed per row, so callers keep using ``var.get()/set()``.
"""
from __future__ import annotations

import sys
import tkinter as tk
import tkinter.font as tkfont

import customtkinter as ctk

_ROW_H = 22
_C_TEXT = "#e2e8f0"
_C_URL = "#64748b"
_C_BOX_ON = "#3b82f6"
_C_BOX_OFF = "#94a3b8"
_C_HOVER = "#2a2a3e"


class CanvasChecklist(ctk.CTkFrame):
    def __init__(self, parent, height: int = 110, **kwargs) -> None:
        super().__init__(parent, corner_radius=0, fg_color="transparent", height=height, **kwargs)
        self.pack_propagate(False)
        self._f_row = tkfont.Font(self, family="Segoe UI", size=11)
        self._f_badge = tkfont.Font(self, family="Segoe UI", size=9, weight="bold")
        self._f_url = tkfont.Font(self, family="Segoe UI", size=9)
        self._f_box = tkfont.Font(self, family="Segoe UI", size=13)

        self._scrollbar = ctk.CTkScrollbar(self, orientation="vertical", command=self._yview)
        self._scrollbar.pack(side="right", fill="y")
        self._canvas = tk.Canvas(
            self, highlightthickness=0, bd=0, bg=self._bg(),
            yscrollcommand=self._scrollbar.set, yscrollincrement=_ROW_H,
        )
        self._canvas.pack(side="left", fill="both", expand=True)
        c = self._canvas
        c.bind("<ButtonRelease-1>", self._on_click)
        c.bind("<Motion>", self._on_motion)
        c.bind("<Leave>", lambda e: self._set_hover(None))
        c.bind("<Configure>", lambda e: self._update_region())
        if "linux" in sys.platform:
            c.bind("<Button-4>", lambda e: self._wheel(-3))
            c.bind("<Button-5>", lambda e: self._wheel(3))
        elif sys.platform == "darwin":
            c.bind("<MouseWheel>", lambda e: self._wheel(-e.delta))
        else:
            c.bind("<MouseWheel>", lambda e: self._wheel(-3 * (e.delta // 120 or (1 if e.delta > 0 else -1))))

        self._rows: list[dict] = []     # per row: {"var", "box", "rect"}
        self._rect_to_row: dict[int, dict] = {}
        self._hover: dict | None = None
        self._total_h = 0

    def _bg(self) -> str:
        return self._apply_appearance_mode(self.cget("fg_color")) if self.cget("fg_color") != "transparent" \
            else self._apply_appearance_mode(self.cget("bg_color"))

    def _set_appearance_mode(self, mode_string):
        super()._set_appearance_mode(mode_string)
        if hasattr(self, "_canvas"):
            self._canvas.configure(bg=self._bg())

    # -- scrolling ------------------------------------------------------

    def _update_region(self) -> None:
        h = max(self._total_h, self._canvas.winfo_height())
        self._canvas.configure(scrollregion=(0, 0, self._canvas.winfo_width(), h))

    def _yview(self, *args) -> None:
        if self._total_h > self._canvas.winfo_height():
            self._canvas.yview(*args)

    def _wheel(self, units: int) -> None:
        if self._total_h > self._canvas.winfo_height():
            self._canvas.yview_scroll(int(units), "units")

    # -- content --------------------------------------------------------

    def clear(self) -> None:
        self._canvas.delete("all")
        self._rows.clear()
        self._rect_to_row.clear()
        self._hover = None
        self._total_h = 0
        self._update_region()

    def set_message(self, text: str) -> None:
        self.clear()
        self._canvas.create_text(
            12, 14, text=text, anchor="nw", font=self._f_row, fill="#888",
        )

    def set_rows(self, rows: list[tuple[str, str, str, tk.BooleanVar, str]]) -> None:
        """rows: (method, name, url, var, method_color), in display order."""
        self.clear()
        c = self._canvas
        bg = self._bg()
        y = 0
        for method, name, url, var, mcolor in rows:
            rect = c.create_rectangle(0, y, 4000, y + _ROW_H, fill=bg, outline="")
            mid = y + _ROW_H // 2
            box = c.create_text(
                6, mid, text="☑" if var.get() else "☐", anchor="w", font=self._f_box,
                fill=_C_BOX_ON if var.get() else _C_BOX_OFF,
            )
            c.create_text(34, mid, text=method[:4], anchor="w", font=self._f_badge, fill=mcolor)
            name_x = 76
            name_w = min(self._f_row.measure(name), 300)
            c.create_text(name_x, mid, text=name if name_w < 300 else name[:45] + "…",
                          anchor="w", font=self._f_row, fill=_C_TEXT)
            url_short = url[:50] + ("…" if len(url) > 50 else "")
            c.create_text(name_x + name_w + 12, mid, text=url_short, anchor="w",
                          font=self._f_url, fill=_C_URL)
            row = {"var": var, "box": box, "rect": rect, "bg": bg, "y": y}
            self._rows.append(row)
            self._rect_to_row[rect] = row
            var.trace_add("write", lambda *_a, r=row: self._sync(r))
            y += _ROW_H
        self._total_h = y
        self._update_region()
        c.yview_moveto(0)

    def _sync(self, row: dict) -> None:
        on = bool(row["var"].get())
        try:
            self._canvas.itemconfigure(
                row["box"], text="☑" if on else "☐", fill=_C_BOX_ON if on else _C_BOX_OFF,
            )
        except tk.TclError:
            pass

    # -- events ---------------------------------------------------------

    def _row_at(self, event: tk.Event) -> dict | None:
        c = self._canvas
        y = c.canvasy(event.y)
        i = int(y // _ROW_H)
        if 0 <= i < len(self._rows) and y < self._total_h:
            return self._rows[i]
        return None

    def _set_hover(self, row: dict | None) -> None:
        if row is self._hover:
            return
        if self._hover is not None:
            self._canvas.itemconfigure(self._hover["rect"], fill=self._hover["bg"])
        if row is not None:
            self._canvas.itemconfigure(row["rect"], fill=_C_HOVER)
        self._hover = row

    def _on_motion(self, event: tk.Event) -> None:
        self._set_hover(self._row_at(event))

    def _on_click(self, event: tk.Event) -> None:
        row = self._row_at(event)
        if row is not None:
            row["var"].set(not row["var"].get())
