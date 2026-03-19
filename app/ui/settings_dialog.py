"""
KangPaket — Settings dialog (modal).
Semua pengaturan global: timeout, SSL, redirect, theme, font, proxy.
"""
from __future__ import annotations

import customtkinter as ctk

from app.core.settings_manager import SettingsManager, DEFAULT_SETTINGS


class SettingsDialog(ctk.CTkToplevel):
    """
    Modal dialog pengaturan global.

    Setelah ditutup, cek:
        dialog.saved -> bool  (True jika user klik Save)
    """

    def __init__(self, parent, settings: SettingsManager, on_apply=None) -> None:
        super().__init__(parent)
        self.title("Settings")
        self.resizable(False, False)
        self.grab_set()
        self.focus_set()

        self._settings = settings
        self._on_apply = on_apply   # callback() dipanggil setelah save
        self.saved     = False

        self._build()

        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width() // 2 - 280
        ph = parent.winfo_rooty() + parent.winfo_height() // 2 - 320
        self.geometry(f"560x640+{pw}+{ph}")

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _: self._cancel())

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        # Scrollable content
        scroll = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        s = self._settings

        # ---- Section: HTTP Defaults ----
        self._section(scroll, "HTTP Defaults")

        self._default_timeout_var = ctk.DoubleVar(value=s.get("default_timeout", 30.0))
        self._row(scroll, "Default Timeout (seconds)", self._default_timeout_var,
                  widget="entry", note="0 = no timeout")

        self._follow_redirects_var = ctk.BooleanVar(value=s.get("follow_redirects", True))
        self._row(scroll, "Follow Redirects", self._follow_redirects_var, widget="check")

        self._verify_ssl_var = ctk.BooleanVar(value=s.get("verify_ssl", True))
        self._row(scroll, "Verify SSL", self._verify_ssl_var, widget="check")

        self._max_size_var = ctk.IntVar(value=s.get("max_response_size_mb", 10))
        self._row(scroll, "Max Response Size (MB)", self._max_size_var,
                  widget="entry")

        # ---- Section: Appearance ----
        self._section(scroll, "Appearance")

        self._theme_var = ctk.StringVar(value=s.get("theme", "dark"))
        self._row(scroll, "Theme", self._theme_var,
                  widget="option", values=["dark", "light", "system"])

        self._font_size_var = ctk.IntVar(value=s.get("font_size", 13))
        self._row(scroll, "Font Size", self._font_size_var,
                  widget="entry", note="applies to URL, body, response areas")

        # ---- Section: Collection ----
        self._section(scroll, "Collection")

        self._default_col_var = ctk.StringVar(value=s.get("default_collection", "Default"))
        self._row(scroll, "Default Collection", self._default_col_var, widget="entry")

        # ---- Section: Proxy ----
        self._section(scroll, "Proxy")

        self._proxy_enabled_var = ctk.BooleanVar(value=s.get("proxy_enabled", False))
        self._row(scroll, "Enable Proxy", self._proxy_enabled_var, widget="check")

        self._proxy_http_var = ctk.StringVar(value=s.get("proxy_http", ""))
        self._row(scroll, "HTTP Proxy", self._proxy_http_var,
                  widget="entry", note="e.g. http://127.0.0.1:8080")

        self._proxy_https_var = ctk.StringVar(value=s.get("proxy_https", ""))
        self._row(scroll, "HTTPS Proxy", self._proxy_https_var,
                  widget="entry", note="e.g. http://127.0.0.1:8080")

        # ---- Buttons ----
        btn_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=12)

        ctk.CTkButton(
            btn_frame, text="Reset Default", width=120, height=34,
            fg_color="#374151", hover_color="#4b5563",
            command=self._reset_defaults,
        ).pack(side="left")

        ctk.CTkButton(
            btn_frame, text="Cancel", width=90, height=34,
            fg_color="#374151", hover_color="#4b5563",
            command=self._cancel,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            btn_frame, text="Save", width=90, height=34,
            fg_color="#2563eb", hover_color="#1d4ed8",
            command=self._save,
        ).pack(side="right")

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _section(self, parent, title: str) -> None:
        ctk.CTkLabel(
            parent, text=title,
            font=("Segoe UI", 12, "bold"),
            anchor="w", text_color="#94a3b8",
        ).pack(fill="x", padx=20, pady=(14, 2))
        ctk.CTkFrame(parent, height=1, corner_radius=0, fg_color="#333").pack(
            fill="x", padx=20, pady=(0, 6)
        )

    def _row(
        self, parent, label: str, var,
        widget: str = "entry",
        values: list[str] | None = None,
        note: str = "",
    ) -> None:
        row = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=3)

        ctk.CTkLabel(
            row, text=label, font=("Segoe UI", 12),
            width=200, anchor="w",
        ).pack(side="left")

        if widget == "check":
            ctk.CTkCheckBox(row, text="", variable=var, width=28).pack(side="left")

        elif widget == "option":
            ctk.CTkOptionMenu(
                row, variable=var, values=values or [],
                width=140, height=28, font=("Segoe UI", 12),
            ).pack(side="left")

        elif widget == "entry":
            ctk.CTkEntry(
                row, textvariable=var,
                width=140, height=28, font=("Courier New", 12),
            ).pack(side="left")

        if note:
            ctk.CTkLabel(
                row, text=note, font=("Segoe UI", 10),
                text_color="#666", anchor="w",
            ).pack(side="left", padx=8)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _save(self) -> None:
        # Validate numeric fields
        try:
            timeout = float(self._default_timeout_var.get())
            if timeout < 0:
                raise ValueError
        except (ValueError, tk_error):
            self._show_error("Default Timeout must be a number ≥ 0.")
            return

        try:
            font_size = int(self._font_size_var.get())
            if not (8 <= font_size <= 32):
                raise ValueError
        except ValueError:
            self._show_error("Font Size must be between 8 and 32.")
            return

        try:
            max_mb = int(self._max_size_var.get())
            if max_mb < 1:
                raise ValueError
        except ValueError:
            self._show_error("Max Response Size must be at least 1 MB.")
            return

        new_settings = {
            "default_timeout":      timeout,
            "follow_redirects":     self._follow_redirects_var.get(),
            "verify_ssl":           self._verify_ssl_var.get(),
            "max_response_size_mb": max_mb,
            "theme":                self._theme_var.get(),
            "font_size":            font_size,
            "default_collection":   self._default_col_var.get().strip() or "Default",
            "proxy_enabled":        self._proxy_enabled_var.get(),
            "proxy_http":           self._proxy_http_var.get().strip(),
            "proxy_https":          self._proxy_https_var.get().strip(),
        }

        self._settings.save_settings(new_settings)
        self.saved = True

        if self._on_apply:
            self._on_apply()

        self.destroy()

    def _reset_defaults(self) -> None:
        self._default_timeout_var.set(DEFAULT_SETTINGS["default_timeout"])
        self._follow_redirects_var.set(DEFAULT_SETTINGS["follow_redirects"])
        self._verify_ssl_var.set(DEFAULT_SETTINGS["verify_ssl"])
        self._max_size_var.set(DEFAULT_SETTINGS["max_response_size_mb"])
        self._theme_var.set(DEFAULT_SETTINGS["theme"])
        self._font_size_var.set(DEFAULT_SETTINGS["font_size"])
        self._default_col_var.set(DEFAULT_SETTINGS["default_collection"])
        self._proxy_enabled_var.set(DEFAULT_SETTINGS["proxy_enabled"])
        self._proxy_http_var.set(DEFAULT_SETTINGS["proxy_http"])
        self._proxy_https_var.set(DEFAULT_SETTINGS["proxy_https"])

    def _cancel(self) -> None:
        self.saved = False
        self.destroy()

    def _show_error(self, msg: str) -> None:
        import tkinter.messagebox as mb
        mb.showerror("Invalid Input", msg, parent=self)


# Alias untuk exception tkinter (hindari import tkinter di level module)
try:
    import tkinter as _tk
    tk_error = _tk.TclError
except Exception:
    tk_error = Exception
