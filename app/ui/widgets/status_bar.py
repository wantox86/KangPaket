"""
KangPaket — Status bar widget (bottom of main window).
Shows: app info (left) | last request info (right).
"""
from __future__ import annotations

import customtkinter as ctk

from app.config import APP_VERSION


class StatusBar(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, height=26, corner_radius=0, **kwargs)
        self.pack_propagate(False)

        # Left: general message
        self._left_label = ctk.CTkLabel(
            self,
            text=f"KangPaket v{APP_VERSION}  —  Ready",
            font=("Segoe UI", 11),
            anchor="w",
            text_color="#94a3b8",
        )
        self._left_label.pack(side="left", padx=10)

        # Separator
        ctk.CTkFrame(self, width=1, corner_radius=0, fg_color="#333").pack(
            side="right", fill="y", padx=0
        )

        # Right: last request stats
        self._right_label = ctk.CTkLabel(
            self,
            text="",
            font=("Segoe UI", 11),
            anchor="e",
            text_color="#64748b",
        )
        self._right_label.pack(side="right", padx=10)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_text(self, text: str) -> None:
        """Set the left-side general message."""
        self._left_label.configure(text=text, text_color="#94a3b8")

    def set_error(self, text: str) -> None:
        """Show error message in red on left."""
        self._left_label.configure(text=text, text_color="#f93e3e")

    def set_request_info(self, method: str, url: str, status: int, elapsed: str, size: str) -> None:
        """Update right side with last request stats."""
        from app.config import status_color
        color = status_color(status) if status > 0 else "#f93e3e"
        self._right_label.configure(
            text=f"{method}  {status}  {elapsed}  {size}",
            text_color=color,
        )
        # Truncate long URLs for left label
        short_url = url if len(url) <= 60 else url[:57] + "…"
        self._left_label.configure(
            text=f"↩  {short_url}",
            text_color="#94a3b8",
        )

    def ready(self) -> None:
        self._left_label.configure(
            text=f"KangPaket v{APP_VERSION}  —  Ready",
            text_color="#94a3b8",
        )
        self._right_label.configure(text="")
