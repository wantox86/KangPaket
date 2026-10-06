"""
KangPaket — Assertion editor widget.
Used by the request panel's Assertions tab to define the checks that the
Collection Runner evaluates against each response.
"""
from __future__ import annotations

import json

import customtkinter as ctk

from app.config import ASSERTION_TYPES, ASSERTION_LABELS, FONT_MONO, FONT_UI


def _label_to_type(label: str) -> str:
    for atype, lbl in ASSERTION_LABELS.items():
        if lbl == label:
            return atype
    return ASSERTION_TYPES[0]


class _AssertionRow:
    """Internal state for a single assertion row."""

    def __init__(self, parent, on_change: callable) -> None:
        self._on_change = on_change

        self._type_var  = ctk.StringVar(value=ASSERTION_LABELS[ASSERTION_TYPES[0]])
        self._field_var = ctk.StringVar()
        self._value_var = ctk.StringVar()

        self._field_var.trace_add("write", lambda *_: on_change())
        self._value_var.trace_add("write", lambda *_: on_change())

        self._frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self._frame.pack(fill="x", pady=1)

        self._type_menu = ctk.CTkOptionMenu(
            self._frame,
            variable=self._type_var,
            values=[ASSERTION_LABELS[t] for t in ASSERTION_TYPES],
            width=200,
            height=28,
            font=(FONT_UI, 11),
            command=self._on_type_change,
        )
        self._type_menu.pack(side="left", padx=(0, 4))

        self._field_entry = ctk.CTkEntry(
            self._frame,
            textvariable=self._field_var,
            placeholder_text="Path / Header",
            width=140,
            height=28,
            font=(FONT_MONO, 12),
        )

        self._value_entry = ctk.CTkEntry(
            self._frame,
            textvariable=self._value_var,
            placeholder_text="Expected value",
            height=28,
            font=(FONT_MONO, 12),
        )
        self._value_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self._del_btn = ctk.CTkButton(
            self._frame,
            text="×",
            width=28,
            height=28,
            font=(FONT_UI, 14),
            fg_color="#3a3a3a",
            hover_color="#f93e3e",
            command=self._request_delete,
        )
        self._del_btn.pack(side="left")

        self._delete_callback: callable | None = None
        self._sync_fields()

    # ---- type-dependent field visibility ----

    def _needs_field(self) -> bool:
        return _label_to_type(self._type_var.get()) in (
            "body_json_path_equals",
            "header_equals",
        )

    def _sync_fields(self) -> None:
        atype = _label_to_type(self._type_var.get())

        if self._needs_field():
            self._field_entry.configure(
                placeholder_text="JSON path" if atype == "body_json_path_equals" else "Header name"
            )
            self._field_entry.pack(side="left", padx=(0, 4), before=self._value_entry)
        else:
            self._field_entry.pack_forget()

        placeholders = {
            "status_code_equals":      "200",
            "status_code_in":          "200, 201, 204",
            "response_time_less_than": "500  (ms)",
            "body_contains":           "substring",
            "body_json_path_equals":   "expected value",
            "header_exists":           "Content-Type",
            "header_equals":           "application/json",
        }
        self._value_entry.configure(placeholder_text=placeholders.get(atype, "Expected value"))

    def _on_type_change(self, _value: str) -> None:
        self._sync_fields()
        self._on_change()

    # ---- delete ----

    def _request_delete(self) -> None:
        if self._delete_callback:
            self._delete_callback(self)

    def set_delete_callback(self, cb: callable) -> None:
        self._delete_callback = cb

    # ---- data ----

    def get_data(self) -> dict | None:
        """Serialise this row into an assertion dict, or None when incomplete."""
        atype = _label_to_type(self._type_var.get())
        raw   = self._value_var.get().strip()
        field = self._field_var.get().strip()

        if atype == "status_code_equals":
            try:
                return {"type": atype, "value": int(raw)}
            except ValueError:
                return None

        if atype == "status_code_in":
            codes: list[int] = []
            for part in raw.split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    codes.append(int(part))
                except ValueError:
                    return None
            return {"type": atype, "values": codes} if codes else None

        if atype == "response_time_less_than":
            try:
                return {"type": atype, "value": int(float(raw))}
            except ValueError:
                return None

        if atype == "body_json_path_equals":
            if not field:
                return None
            try:
                value = json.loads(raw)
            except (ValueError, TypeError):
                value = raw
            return {"type": atype, "path": field, "value": value}

        if atype == "header_equals":
            if not field:
                return None
            return {"type": atype, "header": field, "value": raw}

        # body_contains, header_exists
        return {"type": atype, "value": raw} if raw else None

    def set_data(self, data: dict) -> None:
        atype = data.get("type", ASSERTION_TYPES[0])
        self._type_var.set(ASSERTION_LABELS.get(atype, ASSERTION_LABELS[ASSERTION_TYPES[0]]))
        self._sync_fields()

        if atype == "status_code_in":
            self._value_var.set(", ".join(str(v) for v in data.get("values", [])))
        elif atype == "body_json_path_equals":
            self._field_var.set(data.get("path", ""))
            value = data.get("value")
            self._value_var.set(value if isinstance(value, str) else json.dumps(value))
        elif atype == "header_equals":
            self._field_var.set(data.get("header", ""))
            self._value_var.set(str(data.get("value", "")))
        else:
            self._value_var.set(str(data.get("value", "")))

    def destroy(self) -> None:
        self._frame.destroy()


class AssertionEditor(ctk.CTkFrame):
    """
    Editor for a list of runner assertions.

    Usage:
        editor = AssertionEditor(parent)
        editor.get_data()            # -> list[dict]
        editor.set_data([{...}])
    """

    def __init__(self, parent, on_change: callable | None = None, **kwargs) -> None:
        super().__init__(parent, corner_radius=0, fg_color="transparent", **kwargs)
        self._on_change = on_change or (lambda: None)
        self._rows: list[_AssertionRow] = []

        self._build_header()
        self._build_scroll_area()
        self._build_footer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_data(self) -> list[dict]:
        """Return well-formed assertion dicts; incomplete rows are skipped."""
        result: list[dict] = []
        for row in self._rows:
            data = row.get_data()
            if data is not None:
                result.append(data)
        return result

    def set_data(self, assertions: list[dict]) -> None:
        self._clear_rows()
        for assertion in assertions or []:
            row = self._add_row()
            row.set_data(assertion)

    def clear(self) -> None:
        self._clear_rows()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        header.pack(fill="x")

        ctk.CTkLabel(
            header, text="Assertion", font=(FONT_UI, 11, "bold"), width=200, anchor="w"
        ).pack(side="left", padx=(0, 4))
        ctk.CTkLabel(
            header, text="Expected", font=(FONT_UI, 11, "bold"), anchor="w"
        ).pack(side="left", fill="x", expand=True)

    def _build_scroll_area(self) -> None:
        self._scroll = ctk.CTkScrollableFrame(
            self, corner_radius=0, fg_color="transparent", height=160
        )
        self._scroll.pack(fill="both", expand=True, pady=(2, 0))

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        footer.pack(fill="x", pady=(4, 0))

        ctk.CTkButton(
            footer,
            text="+ Add Assertion",
            width=120,
            height=26,
            font=(FONT_UI, 11),
            fg_color="#2a2a2a",
            hover_color="#3a3a3a",
            command=self._add_row_and_notify,
        ).pack(side="left")

        ctk.CTkLabel(
            footer,
            text="Evaluated by the Collection Runner after each response.",
            font=(FONT_UI, 10),
            text_color="#888",
        ).pack(side="left", padx=8)

    # ------------------------------------------------------------------
    # Row management
    # ------------------------------------------------------------------

    def _add_row(self) -> _AssertionRow:
        row = _AssertionRow(parent=self._scroll, on_change=self._on_change)
        row.set_delete_callback(self._delete_row)
        self._rows.append(row)
        return row

    def _add_row_and_notify(self) -> None:
        self._add_row()
        self._on_change()

    def _delete_row(self, row: _AssertionRow) -> None:
        if row in self._rows:
            self._rows.remove(row)
            row.destroy()
            self._on_change()

    def _clear_rows(self) -> None:
        for row in self._rows:
            row.destroy()
        self._rows.clear()
