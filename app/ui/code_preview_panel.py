"""
KangPaket — Code Preview panel (right-side rail, like Postman's code snippet view).

A thin toggle rail is always visible; expanding reveals a header (language
dropdown, resolve toggle, copy, collapse) and a read-only code viewer with a
line-number gutter and horizontal scroll. State (collapsed/width/language) is
persisted via SettingsManager.

ponytail: no syntax highlighting — tkinter has no native highlighter and a
    per-language regex tokenizer is a separate feature. Read-only text + line
    numbers carry the "code viewer" UX.
    add when: a user asks for coloured code.
ponytail: auto-refresh polls snapshot_profile() every ~300ms instead of wiring
    change callbacks into every editor widget.
    add when: profile edits become expensive to poll.
ponytail: variable resolution resolves only environment/global layers (stable),
    not system vars ($guid/$timestamp) which would flicker every poll.
    add when: preview should also expand system variables.
"""
from __future__ import annotations

import re
import tkinter as tk
import customtkinter as ctk

from app.config import FONT_MONO
from app.core.codegen import LANGUAGE_LABELS, LANGUAGES, generate
from app.core.environment_manager import EnvironmentManager
from app.core.settings_manager import SettingsManager
from app.models.request_model import RequestProfile

_VAR = re.compile(r"\{\{([^}]+)\}\}")

RAIL_WIDTH = 40
DEFAULT_WIDTH = 380
MIN_WIDTH = 280
POLL_MS = 300


def _resolve(text: str, layers: list[dict[str, str]]) -> str:
    def rep(m: re.Match) -> str:
        key = m.group(1).strip()
        for layer in layers:
            if key in layer:
                return str(layer[key])
        return m.group(0)
    return _VAR.sub(rep, text)


def _resolve_preview(profile: RequestProfile, layers: list[dict[str, str]]) -> RequestProfile:
    """Resolve env/global vars only; system vars are left raw (stable output)."""
    import copy
    p = copy.copy(profile)
    p.url = _resolve(p.url, layers)
    p.headers = {k: _resolve(v, layers) for k, v in p.headers.items()}
    p.params = {k: _resolve(v, layers) for k, v in p.params.items()}
    p.body_content = _resolve(p.body_content, layers)
    p.body_form = {k: _resolve(v, layers) for k, v in p.body_form.items()}
    p.auth_data = {k: _resolve(str(v), layers) for k, v in p.auth_data.items()}
    return p


class _Tooltip:
    """Minimal hover tooltip (tkinter has none built-in)."""

    def __init__(self, widget, text: str) -> None:
        self._widget = widget
        self._text = text
        self._tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _e=None) -> None:
        if self._tip is not None:
            return
        x = self._widget.winfo_rootx() + self._widget.winfo_width() + 6
        y = self._widget.winfo_rooty()
        self._tip = tk.Toplevel(self._widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        ctk.CTkLabel(self._tip, text=self._text, fg_color="#1f2937",
                     text_color="#e5e7eb", corner_radius=4).pack(padx=6, pady=3)

    def _hide(self, _e=None) -> None:
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


class CodePreviewPanel(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        settings: SettingsManager,
        environments: EnvironmentManager,
        request_panel,
        **kwargs,
    ) -> None:
        super().__init__(parent, corner_radius=0, fg_color="transparent", **kwargs)
        self._settings = settings
        self._environments = environments
        self._request_panel = request_panel

        self._collapsed = bool(settings.get("code_preview_collapsed", True))
        self._width = int(settings.get("code_preview_width", DEFAULT_WIDTH))
        self._language = settings.get("code_preview_language", "curl")
        if self._language not in LANGUAGES:
            self._language = "curl"
        self._resolve_vars = bool(settings.get("code_preview_resolve", False))

        self._last_sig: tuple | None = None
        self._drag_start_x = 0
        self._drag_start_w = 0

        self._build_rail()
        self._build_content()

        self.pack_propagate(False)
        self._apply_width()
        self.after(POLL_MS, self._poll)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_rail(self) -> None:
        self._rail = ctk.CTkFrame(self, width=RAIL_WIDTH, corner_radius=0,
                                  fg_color="transparent")
        self._rail.pack(side="left", fill="y")
        self._rail.pack_propagate(False)

        self._toggle_btn = ctk.CTkButton(
            self._rail, text="</>", width=30, height=30,
            font=(FONT_MONO, 12, "bold"),
            fg_color="transparent", hover_color=("gray85", "gray25"),
            text_color=("gray20", "gray80"),
            command=self.toggle,
        )
        self._toggle_btn.pack(padx=5, pady=6)
        _Tooltip(self._toggle_btn, "Code snippet")

    def _build_content(self) -> None:
        self._content = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")

        # Resize handle (left edge of the expanded panel)
        self._handle = ctk.CTkFrame(self._content, width=4, corner_radius=0,
                                    fg_color="transparent")
        self._handle.pack(side="left", fill="y")
        self._handle.bind("<Button-1>", self._start_resize)
        self._handle.bind("<B1-Motion>", self._do_resize)
        self._handle.bind("<ButtonRelease-1>", self._end_resize)

        self._body = ctk.CTkFrame(self._content, corner_radius=0, fg_color="transparent")
        self._body.pack(side="left", fill="both", expand=True)

        # Header
        header = ctk.CTkFrame(self._body, corner_radius=0, fg_color="transparent")
        header.pack(fill="x", padx=(6, 4), pady=(6, 4))

        self._lang_var = ctk.StringVar(value=LANGUAGE_LABELS.get(self._language, "cURL"))
        self._lang_menu = ctk.CTkOptionMenu(
            header, variable=self._lang_var,
            values=[LANGUAGE_LABELS[k] for k in LANGUAGES],
            width=170, height=28, font=("Segoe UI", 11),
            command=self._on_language_change,
        )
        self._lang_menu.pack(side="left", padx=(0, 6))

        self._resolve_var = ctk.BooleanVar(value=self._resolve_vars)
        ctk.CTkCheckBox(
            header, text="Resolve {{var}}", variable=self._resolve_var,
            font=("Segoe UI", 10), command=self._on_resolve_toggle,
        ).pack(side="left", padx=(0, 6))

        self._copy_btn = ctk.CTkButton(
            header, text="Copy", width=56, height=28, font=("Segoe UI", 11),
            command=self._copy,
        )
        self._copy_btn.pack(side="right", padx=(0, 2))

        self._collapse_btn = ctk.CTkButton(
            header, text="❯", width=28, height=28, font=("Segoe UI", 11),
            fg_color="transparent", hover_color=("gray85", "gray25"),
            text_color=("gray20", "gray80"), command=self.toggle,
        )
        self._collapse_btn.pack(side="right", padx=(0, 4))

        # Code viewer: gutter + textbox sharing the y-scrollbar
        viewer = ctk.CTkFrame(self._body, corner_radius=0, fg_color="transparent")
        viewer.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        self._gutter = tk.Text(
            viewer, width=4, bd=0, wrap="none", cursor="arrow",
            takefocus=0, highlightthickness=0, font=(FONT_MONO, 11), padx=4, pady=2,
        )
        self._gutter.pack(side="left", fill="y")
        self._gutter.configure(state="disabled")

        self._code = ctk.CTkTextbox(
            viewer, font=(FONT_MONO, 11), wrap="none",
            activate_scrollbars=True,
        )
        self._code.pack(side="left", fill="both", expand=True)
        self._code.configure(state="disabled")

        # Match gutter colours to the code textbox and sync vertical scroll.
        self._sync_gutter_colors()
        self._code._textbox.configure(yscrollcommand=self._on_code_scroll)
        self._code.bind("<MouseWheel>", lambda e: None)  # keep default (scrollbar drives)

    def _sync_gutter_colors(self) -> None:
        bg = self._code._textbox.cget("bg")
        fg = self._code._textbox.cget("fg")
        self._gutter.configure(bg=bg, fg=fg, selectbackground=bg)

    # ------------------------------------------------------------------
    # Width / layout
    # ------------------------------------------------------------------

    def _apply_width(self) -> None:
        if self._collapsed:
            self._content.pack_forget()
            self.configure(width=RAIL_WIDTH)
        else:
            self._content.pack(side="left", fill="both", expand=True)
            self.configure(width=self._width)
        self._toggle_btn.configure(text="</>" if self._collapsed else "❮")

    def toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._settings.set("code_preview_collapsed", self._collapsed)
        self._apply_width()
        if not self._collapsed:
            self._poll()

    # ------------------------------------------------------------------
    # Resize
    # ------------------------------------------------------------------

    def _start_resize(self, e) -> None:
        self._drag_start_x = e.x_root
        self._drag_start_w = self._width

    def _do_resize(self, e) -> None:
        delta = self._drag_start_x - e.x_root   # dragging left grows the panel
        new_w = max(MIN_WIDTH, self._drag_start_w + delta)
        screen_w = self.winfo_screenwidth()
        new_w = min(new_w, int(screen_w * 0.6))
        if new_w != self._width:
            self._width = new_w
            self.configure(width=self._width)

    def _end_resize(self, _e) -> None:
        self._settings.set("code_preview_width", self._width)

    # ------------------------------------------------------------------
    # Header actions
    # ------------------------------------------------------------------

    def _on_language_change(self, label: str) -> None:
        for key, lbl in LANGUAGE_LABELS.items():
            if lbl == label:
                self._language = key
                break
        self._settings.set("code_preview_language", self._language)
        self._last_sig = None
        self._poll()

    def _on_resolve_toggle(self) -> None:
        self._resolve_vars = self._resolve_var.get()
        self._settings.set("code_preview_resolve", self._resolve_vars)
        self._last_sig = None
        self._poll()

    def _copy(self) -> None:
        text = self._code.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)
        self._copy_btn.configure(text="✓", fg_color="#16a34a", hover_color="#16a34a")
        self.after(1500, lambda: self._copy_btn.configure(
            text="Copy", fg_color=("#3a7ebf", "#1f538d"),
            hover_color=("#325882", "#14375e")))

    # ------------------------------------------------------------------
    # Auto-refresh (debounced poll)
    # ------------------------------------------------------------------

    def _poll(self) -> None:
        if self._collapsed:
            self.after(POLL_MS, self._poll)
            return
        profile = self._request_panel.snapshot_profile()
        layers = self._environments.layers()
        if self._resolve_vars:
            profile = _resolve_preview(profile, layers)
        sig = self._signature(profile)
        if sig != self._last_sig:
            self._last_sig = sig
            self._render(generate(self._language, profile))
        self.after(POLL_MS, self._poll)

    @staticmethod
    def _signature(p: RequestProfile) -> tuple:
        return (
            p.method, p.url, tuple(sorted(p.headers.items())),
            tuple(sorted(p.params.items())), p.body_type, p.body_content,
            tuple(sorted(p.body_form.items())), p.auth_type,
            tuple(sorted(p.auth_data.items())),
        )

    def _render(self, text: str) -> None:
        self._code.configure(state="normal")
        self._code.delete("1.0", "end")
        self._code.insert("1.0", text)
        self._code.configure(state="disabled")

        n = text.count("\n") + (1 if text else 0)
        self._gutter.configure(state="normal")
        self._gutter.delete("1.0", "end")
        if n:
            self._gutter.insert("1.0", "\n".join(str(i) for i in range(1, n + 1)))
        self._gutter.configure(state="disabled")
        self._on_code_scroll("1.0", "1.0")

    def _on_code_scroll(self, first, last) -> None:
        try:
            self._gutter.yview_moveto(float(first))
        except (tk.TclError, ValueError):
            pass
