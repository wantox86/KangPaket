"""
KangPaket — JSON viewer widget with tag-based syntax highlighting.
Uses tkinter.Text internally (wrapped in a CTkFrame) to support color tags.
"""
from __future__ import annotations

import json
import re
import tkinter as tk
import customtkinter as ctk

from app.config import FONT_MONO

# Syntax highlight colors (dark theme)
_COLORS = {
    "key":     "#7dd3fc",   # light blue  — object keys
    "string":  "#86efac",   # light green — string values
    "number":  "#fb923c",   # orange      — numbers
    "boolean": "#c084fc",   # purple      — true / false
    "null":    "#c084fc",   # purple      — null
    "brace":   "#94a3b8",   # slate       — {  }  [  ]
    "colon":   "#94a3b8",   # slate       — :  ,
}

# Patterns applied in order (order matters — keys before strings)
_TOKEN_RE = re.compile(
    r'(?P<key>"(?:[^"\\]|\\.)*")\s*(?=:)'   # "key":
    r'|(?P<string>"(?:[^"\\]|\\.)*")'        # "string value"
    r'|(?P<number>-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)'
    r'|(?P<boolean>true|false)'
    r'|(?P<null>null)'
    r'|(?P<brace>[{}\[\]])'
    r'|(?P<colon>[,:])'
)


class JsonViewer(ctk.CTkFrame):
    """
    Syntax-highlighted JSON viewer.

    Public API:
        viewer.set_json(text: str)  — parse + display with highlighting
        viewer.set_raw(text: str)   — display as plain text (no highlight)
        viewer.clear()
        viewer.get_text() -> str
    """

    def __init__(self, parent, font_size: int = 12, **kwargs) -> None:
        super().__init__(parent, corner_radius=0, fg_color="transparent", **kwargs)
        self._font_size = font_size
        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        # Use tk.Text directly for full tag support
        self._text = tk.Text(
            self,
            font=(FONT_MONO, self._font_size),
            wrap="none",
            state="disabled",
            bg="#1e1e2e",
            fg="#cdd6f4",
            insertbackground="#cdd6f4",
            selectbackground="#313244",
            relief="flat",
            borderwidth=0,
            padx=8,
            pady=6,
        )

        # Scrollbars
        vsb = ctk.CTkScrollbar(self, command=self._text.yview)
        hsb = ctk.CTkScrollbar(self, orientation="horizontal", command=self._text.xview)
        self._text.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        self._text.pack(side="left", fill="both", expand=True)

        # Configure color tags
        for tag, color in _COLORS.items():
            self._text.tag_configure(tag, foreground=color)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_json(self, text: str) -> None:
        """Pretty-print and syntax-highlight JSON text."""
        try:
            parsed = json.loads(text)
            pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, ValueError):
            # Not valid JSON — fall back to raw display
            self.set_raw(text)
            return

        self._render_highlighted(pretty)

    def set_raw(self, text: str) -> None:
        """Display plain text without highlighting."""
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert("1.0", text)
        self._text.configure(state="disabled")

    def clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")

    def get_text(self) -> str:
        return self._text.get("1.0", "end-1c")

    # ------------------------------------------------------------------
    # Highlight engine
    # ------------------------------------------------------------------

    def _render_highlighted(self, text: str) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert("1.0", text)

        # Apply tags token by token
        for match in _TOKEN_RE.finditer(text):
            tag = match.lastgroup
            if tag is None:
                continue
            start_idx = self._offset_to_index(match.start())
            end_idx   = self._offset_to_index(match.end())
            self._text.tag_add(tag, start_idx, end_idx)

        self._text.configure(state="disabled")

    def _offset_to_index(self, offset: int) -> str:
        """Convert a character offset to tkinter Text index (line.col)."""
        content = self._text.get("1.0", "end-1c")
        lines   = content[:offset].split("\n")
        line    = len(lines)
        col     = len(lines[-1])
        return f"{line}.{col}"
