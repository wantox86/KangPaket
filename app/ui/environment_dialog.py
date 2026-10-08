"""
KangPaket — Environments editor dialog (Tools > Environments…).
Left: Globals + environment list. Right: variable table for the selection.
"""
from __future__ import annotations

import tkinter.messagebox as mb
import customtkinter as ctk

from app.core.environment_manager import EnvironmentManager
from app.models.environment_model import Environment
from app.ui.widgets.variable_editor import VariableEditor

_GLOBALS = "__globals__"


class EnvironmentDialog(ctk.CTkToplevel):
    def __init__(self, parent, manager: EnvironmentManager) -> None:
        super().__init__(parent)
        self.title("Environments — KangPaket")
        self.geometry("820x520")
        self.minsize(640, 400)
        self.grab_set()
        self.focus_set()

        self._mgr = manager
        self._selected: str = _GLOBALS
        self._buttons: dict[str, ctk.CTkButton] = {}

        self._build()
        self._refresh_list()
        self._load_selected()

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _: self._close())

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        left = ctk.CTkFrame(self, width=220, corner_radius=0)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        self._list = ctk.CTkScrollableFrame(left, corner_radius=0, fg_color="transparent")
        self._list.pack(fill="both", expand=True, padx=4, pady=4)

        btns = ctk.CTkFrame(left, fg_color="transparent")
        btns.pack(fill="x", padx=4, pady=(0, 6))
        for text, cmd in (
            ("Add", self._add), ("Rename", self._rename),
            ("Duplicate", self._duplicate), ("Delete", self._delete),
        ):
            ctk.CTkButton(
                btns, text=text, width=48, height=26, font=("Segoe UI", 11), command=cmd,
            ).pack(side="left", expand=True, fill="x", padx=1)

        right = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True, padx=8, pady=8)

        self._title = ctk.CTkLabel(right, text="", font=("Segoe UI", 13, "bold"), anchor="w")
        self._title.pack(fill="x")
        self._hint = ctk.CTkLabel(
            right, text="", font=("Segoe UI", 11), text_color="#94a3b8", anchor="w",
            justify="left", wraplength=540,
        )
        self._hint.pack(fill="x", pady=(0, 6))

        self._editor = VariableEditor(right, on_change=self._commit)
        self._editor.pack(fill="both", expand=True)

        ctk.CTkButton(right, text="Close", width=80, command=self._close).pack(
            anchor="e", pady=(6, 0)
        )

    def _refresh_list(self) -> None:
        for b in self._buttons.values():
            b.destroy()
        self._buttons.clear()
        entries = [(_GLOBALS, "Globals")] + [(e.id, e.name) for e in self._mgr.envs]
        for key, label in entries:
            if key != _GLOBALS and key == self._mgr.active_id:
                label += "  (active)"
            btn = ctk.CTkButton(
                self._list, text=label, anchor="w", height=28, font=("Segoe UI", 12),
                command=lambda k=key: self._select(k),
            )
            btn.pack(fill="x", pady=1)
            self._buttons[key] = btn
        self._highlight()

    def _highlight(self) -> None:
        for key, btn in self._buttons.items():
            sel = key == self._selected
            btn.configure(
                fg_color=("#3b8ed0", "#1f6aa5") if sel else "transparent",
                text_color=("white", "white") if sel else ("gray10", "gray90"),
            )

    # ------------------------------------------------------------------
    # Selection / persistence
    # ------------------------------------------------------------------

    def _current_env(self) -> Environment | None:
        return self._mgr.get(self._selected)

    def _select(self, key: str) -> None:
        self._mgr.changed()
        self._selected = key
        self._highlight()
        self._load_selected()

    def _load_selected(self) -> None:
        env = self._current_env()
        if env is None:
            self._selected = _GLOBALS
            self._title.configure(text="Globals")
            self._hint.configure(
                text="Available in every request. Active environment overrides Globals; "
                     "CSV rows in the Runner override both."
            )
            self._editor.set_variables(self._mgr.globals)
        else:
            self._title.configure(text=env.name)
            self._hint.configure(text="Use {{name}} in URL, headers, params, body, auth and assertions.")
            self._editor.set_variables(env.vars)
        self._highlight()

    def _commit(self) -> None:
        variables = self._editor.get_variables()
        env = self._current_env()
        if env is None:
            self._mgr.globals = variables
        else:
            env.vars = variables

    def _close(self) -> None:
        self._mgr.changed()
        self.destroy()

    # ------------------------------------------------------------------
    # Environment actions
    # ------------------------------------------------------------------

    def _ask_name(self, title: str) -> str | None:
        dlg = ctk.CTkInputDialog(text="Environment name:", title=title)
        name = (dlg.get_input() or "").strip()
        return name or None

    def _add(self) -> None:
        name = self._ask_name("New Environment")
        if not name:
            return
        env = self._mgr.add(Environment(self._mgr.unique_name(name)))
        self._select(env.id)
        self._refresh_list()

    def _rename(self) -> None:
        env = self._current_env()
        if env is None:
            return
        name = self._ask_name("Rename Environment")
        if not name or name == env.name:
            return
        env.name = self._mgr.unique_name(name)
        self._mgr.changed()
        self._refresh_list()
        self._load_selected()

    def _duplicate(self) -> None:
        env = self._current_env()
        if env is None:
            return
        self._commit()
        copy_env = Environment.from_dict(env.to_dict() | {"id": None, "name": self._mgr.unique_name(f"{env.name} copy")})
        self._mgr.add(copy_env)
        self._select(copy_env.id)
        self._refresh_list()

    def _delete(self) -> None:
        env = self._current_env()
        if env is None:
            return
        if not mb.askyesno("Delete Environment", f"Delete '{env.name}'?", parent=self):
            return
        self._mgr.envs.remove(env)
        self._selected = _GLOBALS
        self._mgr.changed()
        self._refresh_list()
        self._load_selected()
