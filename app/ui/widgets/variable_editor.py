"""
KangPaket — Variable table editor (enabled | key | value | secret | delete).
Same row pattern as KeyValueEditor, plus a "secret" column that masks the value.
"""
from __future__ import annotations

import customtkinter as ctk

from app.models.environment_model import Variable


class _VarRow:
    def __init__(self, parent, on_change, on_delete) -> None:
        self._enabled = ctk.BooleanVar(value=True)
        self._secret  = ctk.BooleanVar(value=False)
        self._key     = ctk.StringVar()
        self._value   = ctk.StringVar()
        for var in (self._enabled, self._secret, self._key, self._value):
            var.trace_add("write", lambda *_: on_change())
        self._secret.trace_add("write", lambda *_: self._apply_mask())

        self.frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.frame.pack(fill="x", pady=1)

        ctk.CTkCheckBox(
            self.frame, variable=self._enabled, text="", width=24,
            checkbox_width=16, checkbox_height=16,
        ).pack(side="left", padx=(0, 4))
        ctk.CTkEntry(
            self.frame, textvariable=self._key, placeholder_text="Variable",
            width=160, height=28, font=("Courier New", 12),
        ).pack(side="left", padx=(0, 4))
        self._val_entry = ctk.CTkEntry(
            self.frame, textvariable=self._value, placeholder_text="Value",
            height=28, font=("Courier New", 12),
        )
        self._val_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkCheckBox(
            self.frame, variable=self._secret, text="secret", width=64,
            checkbox_width=16, checkbox_height=16, font=("Segoe UI", 11),
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            self.frame, text="×", width=28, height=28, font=("Segoe UI", 14),
            fg_color="#3a3a3a", hover_color="#f93e3e",
            command=lambda: on_delete(self),
        ).pack(side="left")

    def _apply_mask(self) -> None:
        self._val_entry.configure(show="•" if self._secret.get() else "")

    def load(self, var: Variable) -> None:
        self._key.set(var.key)
        self._value.set(var.value)
        self._secret.set(var.secret)
        self._enabled.set(var.enabled)
        self._apply_mask()

    def to_variable(self) -> Variable:
        return Variable(
            key=self._key.get().strip(),
            value=self._value.get(),
            secret=self._secret.get(),
            enabled=self._enabled.get(),
        )


class VariableEditor(ctk.CTkFrame):
    def __init__(self, parent, on_change=None, **kwargs) -> None:
        super().__init__(parent, corner_radius=0, fg_color="transparent", **kwargs)
        self._on_change = on_change or (lambda: None)
        self._rows: list[_VarRow] = []
        self._loading = False

        ctk.CTkButton(
            self, text="+ Add Variable", width=110, height=26, font=("Segoe UI", 11),
            fg_color="#2a2a2a", hover_color="#3a3a3a", command=self._add_blank,
        ).pack(side="bottom", anchor="w", pady=(4, 0))
        self._scroll = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True)

    def get_variables(self) -> list[Variable]:
        return [r.to_variable() for r in self._rows if r.to_variable().key]

    def set_variables(self, variables: list[Variable]) -> None:
        self._loading = True
        for row in self._rows:
            row.frame.destroy()
        self._rows.clear()
        for var in variables:
            self._new_row().load(var)
        self._loading = False

    def _new_row(self) -> _VarRow:
        row = _VarRow(self._scroll, self._changed, self._delete_row)
        self._rows.append(row)
        return row

    def _add_blank(self) -> None:
        self._new_row()

    def _delete_row(self, row: _VarRow) -> None:
        self._rows.remove(row)
        row.frame.destroy()
        self._changed()

    def _changed(self) -> None:
        if not self._loading:
            self._on_change()
