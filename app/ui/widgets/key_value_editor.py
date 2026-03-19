"""
KangPaket — Reusable key-value table editor widget.
Used for Headers, Params, Body form-data, and x-www-form-urlencoded.
"""
from __future__ import annotations

import customtkinter as ctk


class _Row:
    """Internal state for a single key-value row."""

    def __init__(
        self,
        parent: ctk.CTkScrollableFrame,
        on_change: callable,
        allow_toggle: bool,
        row_idx: int,
    ) -> None:
        self._on_change   = on_change
        self._allow_toggle = allow_toggle

        self._enabled_var = ctk.BooleanVar(value=True)
        self._key_var     = ctk.StringVar()
        self._value_var   = ctk.StringVar()

        self._enabled_var.trace_add("write", lambda *_: on_change())
        self._key_var.trace_add("write",     lambda *_: on_change())
        self._value_var.trace_add("write",   lambda *_: on_change())

        self._frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self._frame.pack(fill="x", pady=1)

        if allow_toggle:
            self._chk = ctk.CTkCheckBox(
                self._frame,
                variable=self._enabled_var,
                text="",
                width=24,
                checkbox_width=16,
                checkbox_height=16,
                command=self._on_toggle,
            )
            self._chk.pack(side="left", padx=(0, 4))

        self._key_entry = ctk.CTkEntry(
            self._frame,
            textvariable=self._key_var,
            placeholder_text="Key",
            width=180,
            height=28,
            font=("Courier New", 12),
        )
        self._key_entry.pack(side="left", padx=(0, 4))

        self._val_entry = ctk.CTkEntry(
            self._frame,
            textvariable=self._value_var,
            placeholder_text="Value",
            height=28,
            font=("Courier New", 12),
        )
        self._val_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self._del_btn = ctk.CTkButton(
            self._frame,
            text="×",
            width=28,
            height=28,
            font=("Segoe UI", 14),
            fg_color="#3a3a3a",
            hover_color="#f93e3e",
            command=self._request_delete,
        )
        self._del_btn.pack(side="left")

        self._delete_callback: callable | None = None

    def _on_toggle(self) -> None:
        state = "normal" if self._enabled_var.get() else "disabled"
        self._key_entry.configure(state=state)
        self._val_entry.configure(state=state)

    def _request_delete(self) -> None:
        if self._delete_callback:
            self._delete_callback(self)

    def set_delete_callback(self, cb: callable) -> None:
        self._delete_callback = cb

    def get_key(self) -> str:
        return self._key_var.get()

    def get_value(self) -> str:
        return self._value_var.get()

    def is_enabled(self) -> bool:
        return self._enabled_var.get()

    def set_key(self, key: str) -> None:
        self._key_var.set(key)

    def set_value(self, value: str) -> None:
        self._value_var.set(value)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled_var.set(enabled)
        self._on_toggle()

    def destroy(self) -> None:
        self._frame.destroy()


class KeyValueEditor(ctk.CTkFrame):
    """
    Reusable key-value table widget.

    Usage:
        editor = KeyValueEditor(parent, columns=["Key", "Value"], allow_toggle=True)
        data = editor.get_data()   # -> dict[str, str]  (enabled rows only)
        editor.set_data({"foo": "bar"})
    """

    def __init__(
        self,
        parent,
        columns: list[str] | None = None,
        allow_toggle: bool = True,
        on_change: callable | None = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, corner_radius=0, fg_color="transparent", **kwargs)
        self._allow_toggle = allow_toggle
        self._on_change    = on_change or (lambda: None)
        self._rows: list[_Row] = []

        self._build_header(columns or ["Key", "Value"])
        self._build_scroll_area()
        self._build_footer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_data(self) -> dict[str, str]:
        """Return only enabled rows with non-empty keys."""
        result: dict[str, str] = {}
        for row in self._rows:
            if row.is_enabled() and row.get_key().strip():
                result[row.get_key().strip()] = row.get_value()
        return result

    def set_data(self, data: dict[str, str]) -> None:
        """Populate table from dict, replacing all existing rows."""
        self._clear_rows()
        for key, value in data.items():
            row = self._add_row()
            row.set_key(key)
            row.set_value(value)

    def clear(self) -> None:
        self._clear_rows()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_header(self, columns: list[str]) -> None:
        header = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        header.pack(fill="x")

        # Checkbox placeholder
        if self._allow_toggle:
            ctk.CTkLabel(header, text="", width=28).pack(side="left")

        ctk.CTkLabel(
            header,
            text=columns[0],
            font=("Segoe UI", 11, "bold"),
            width=180,
            anchor="w",
        ).pack(side="left", padx=(0, 4))

        ctk.CTkLabel(
            header,
            text=columns[1] if len(columns) > 1 else "Value",
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

    def _build_scroll_area(self) -> None:
        self._scroll = ctk.CTkScrollableFrame(
            self,
            corner_radius=0,
            fg_color="transparent",
            height=160,
        )
        self._scroll.pack(fill="both", expand=True, pady=(2, 0))

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        footer.pack(fill="x", pady=(4, 0))

        ctk.CTkButton(
            footer,
            text="+ Add Row",
            width=90,
            height=26,
            font=("Segoe UI", 11),
            fg_color="#2a2a2a",
            hover_color="#3a3a3a",
            command=self._add_row,
        ).pack(side="left")

    # ------------------------------------------------------------------
    # Row management
    # ------------------------------------------------------------------

    def _add_row(self) -> _Row:
        row = _Row(
            parent=self._scroll,
            on_change=self._on_change,
            allow_toggle=self._allow_toggle,
            row_idx=len(self._rows),
        )
        row.set_delete_callback(self._delete_row)
        self._rows.append(row)
        return row

    def _delete_row(self, row: _Row) -> None:
        if row in self._rows:
            self._rows.remove(row)
            row.destroy()
            self._on_change()

    def _clear_rows(self) -> None:
        for row in self._rows:
            row.destroy()
        self._rows.clear()
