"""
KangPaket — Request panel with full tabs: Params, Headers, Body, Auth, Settings.
"""
from __future__ import annotations

import json
import threading
import customtkinter as ctk

from app.config import (
    HTTP_METHODS, METHOD_COLORS, FONT_MONO, RAW_CONTENT_TYPES,
)
from app.core.http_client import HttpClient
from app.core.settings_manager import SettingsManager
from app.models.request_model import RequestProfile
from app.models.response_model import ResponseResult
from app.ui.widgets.key_value_editor import KeyValueEditor


class RequestPanel(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        settings: SettingsManager,
        on_response=None,
        on_status=None,
        on_save=None,
        on_delete=None,
        **kwargs,
    ):
        super().__init__(parent, corner_radius=0, **kwargs)
        self._settings     = settings
        self._on_response  = on_response   # callback(ResponseResult)
        self._on_status    = on_status     # callback(str)
        self._on_save      = on_save       # callback(RequestProfile) → opens ProfileDialog
        self._on_delete    = on_delete     # callback(profile_id: str)
        self._http_client  = HttpClient()
        self._sending      = False
        self._current_profile_id: str | None = None  # ID profil yang sedang dibuka
        self._is_dirty     = False          # unsaved changes flag

        self._build_url_bar()
        self._build_tabs()

    # ------------------------------------------------------------------
    # URL bar
    # ------------------------------------------------------------------

    def _build_url_bar(self) -> None:
        bar = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        bar.pack(fill="x", padx=8, pady=(8, 4))

        # Method dropdown
        self._method_var = ctk.StringVar(value="GET")
        self._method_menu = ctk.CTkOptionMenu(
            bar,
            variable=self._method_var,
            values=HTTP_METHODS,
            width=110,
            height=36,
            font=("Segoe UI", 12, "bold"),
            command=self._on_method_change,
        )
        self._method_menu.pack(side="left", padx=(0, 6))
        self._apply_method_color()

        # URL entry
        self._url_var = ctk.StringVar()
        self._url_entry = ctk.CTkEntry(
            bar,
            textvariable=self._url_var,
            placeholder_text="https://api.example.com/endpoint",
            font=(FONT_MONO, 13),
            height=36,
        )
        self._url_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._url_entry.bind("<Return>", lambda _: self._send_request())
        self._url_var.trace_add("write", lambda *_: self._mark_dirty())

        # SEND button
        self._send_btn = ctk.CTkButton(
            bar,
            text="SEND",
            width=80,
            height=36,
            font=("Segoe UI", 13, "bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=self._send_request,
        )
        self._send_btn.pack(side="left", padx=(0, 6))

        # Save button
        self._save_btn = ctk.CTkButton(
            bar,
            text="Save",
            width=60,
            height=36,
            font=("Segoe UI", 12),
            fg_color="#374151",
            hover_color="#4b5563",
            command=self._save_profile,
        )
        self._save_btn.pack(side="left", padx=(0, 6))

        # Delete button (only active when a saved profile is loaded)
        self._delete_btn = ctk.CTkButton(
            bar,
            text="Delete",
            width=60,
            height=36,
            font=("Segoe UI", 12),
            fg_color="#374151",
            hover_color="#7f1d1d",
            text_color="#f87171",
            state="disabled",
            command=self._delete_profile,
        )
        self._delete_btn.pack(side="left")

    # ------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------

    def _build_tabs(self) -> None:
        self._tabview = ctk.CTkTabview(self, anchor="nw")
        self._tabview.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        for tab_name in ["Params", "Headers", "Body", "Auth", "Settings"]:
            self._tabview.add(tab_name)

        self._build_params_tab()
        self._build_headers_tab()
        self._build_body_tab()
        self._build_auth_tab()
        self._build_settings_tab()

    # ---- Params ----

    def _build_params_tab(self) -> None:
        tab = self._tabview.tab("Params")
        self._params_editor = KeyValueEditor(
            tab,
            columns=["Key", "Value"],
            allow_toggle=True,
            on_change=self._on_params_change,
        )
        self._params_editor.pack(fill="both", expand=True)

    def _on_params_change(self) -> None:
        """Live-update URL preview label (optional visual feedback)."""
        pass

    # ---- Headers ----

    def _build_headers_tab(self) -> None:
        tab = self._tabview.tab("Headers")

        # Preset quick-add
        preset_frame = ctk.CTkFrame(tab, corner_radius=0, fg_color="transparent")
        preset_frame.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(
            preset_frame, text="Quick add:", font=("Segoe UI", 11), text_color="#888"
        ).pack(side="left", padx=(0, 6))

        presets = [
            ("Content-Type: JSON", "Content-Type", "application/json"),
            ("Content-Type: XML",  "Content-Type", "application/xml"),
            ("Accept: JSON",       "Accept",        "application/json"),
            ("Accept: Any",        "Accept",        "*/*"),
        ]
        for label, key, value in presets:
            ctk.CTkButton(
                preset_frame,
                text=label,
                width=130,
                height=24,
                font=("Segoe UI", 10),
                fg_color="#2a2a2a",
                hover_color="#3a3a3a",
                command=lambda k=key, v=value: self._add_preset_header(k, v),
            ).pack(side="left", padx=2)

        self._headers_editor = KeyValueEditor(
            tab,
            columns=["Header", "Value"],
            allow_toggle=True,
        )
        self._headers_editor.pack(fill="both", expand=True)

    def _add_preset_header(self, key: str, value: str) -> None:
        data = self._headers_editor.get_data()
        data[key] = value
        self._headers_editor.set_data(data)

    # ---- Body ----

    def _build_body_tab(self) -> None:
        tab = self._tabview.tab("Body")

        # Body type radio row
        type_frame = ctk.CTkFrame(tab, corner_radius=0, fg_color="transparent")
        type_frame.pack(fill="x", pady=(4, 6))

        self._body_type_var = ctk.StringVar(value="none")
        for btype in ["none", "raw", "form-data", "x-www-form-urlencoded"]:
            ctk.CTkRadioButton(
                type_frame,
                text=btype,
                variable=self._body_type_var,
                value=btype,
                command=self._on_body_type_change,
            ).pack(side="left", padx=(0, 12))

        # Container that switches content
        self._body_content_frame = ctk.CTkFrame(
            tab, corner_radius=0, fg_color="transparent"
        )
        self._body_content_frame.pack(fill="both", expand=True)

        self._build_body_raw_panel()
        self._build_body_form_panel()

        self._show_body_panel("none")

    def _build_body_raw_panel(self) -> None:
        self._raw_frame = ctk.CTkFrame(
            self._body_content_frame, corner_radius=0, fg_color="transparent"
        )

        # Content-Type dropdown + Format JSON button
        ctrl_row = ctk.CTkFrame(self._raw_frame, corner_radius=0, fg_color="transparent")
        ctrl_row.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(
            ctrl_row, text="Content-Type:", font=("Segoe UI", 11)
        ).pack(side="left", padx=(0, 6))

        self._raw_ct_var = ctk.StringVar(value="application/json")
        ctk.CTkOptionMenu(
            ctrl_row,
            variable=self._raw_ct_var,
            values=RAW_CONTENT_TYPES,
            width=220,
            height=26,
            font=("Segoe UI", 11),
        ).pack(side="left", padx=(0, 12))

        ctk.CTkButton(
            ctrl_row,
            text="Format JSON",
            width=100,
            height=26,
            font=("Segoe UI", 11),
            fg_color="#374151",
            hover_color="#4b5563",
            command=self._format_json,
        ).pack(side="left")

        # Raw body textarea
        self._body_raw_text = ctk.CTkTextbox(
            self._raw_frame,
            font=(FONT_MONO, 12),
            wrap="none",
        )
        self._body_raw_text.pack(fill="both", expand=True)

    def _build_body_form_panel(self) -> None:
        self._form_frame = ctk.CTkFrame(
            self._body_content_frame, corner_radius=0, fg_color="transparent"
        )
        self._body_form_editor = KeyValueEditor(
            self._form_frame,
            columns=["Field", "Value"],
            allow_toggle=True,
        )
        self._body_form_editor.pack(fill="both", expand=True)

    def _on_body_type_change(self) -> None:
        self._show_body_panel(self._body_type_var.get())

    def _show_body_panel(self, body_type: str) -> None:
        self._raw_frame.pack_forget()
        self._form_frame.pack_forget()

        if body_type == "raw":
            self._raw_frame.pack(fill="both", expand=True)
        elif body_type in ("form-data", "x-www-form-urlencoded"):
            self._form_frame.pack(fill="both", expand=True)

    def _format_json(self) -> None:
        raw = self._body_raw_text.get("1.0", "end-1c")
        try:
            parsed = json.loads(raw)
            pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
            self._body_raw_text.delete("1.0", "end")
            self._body_raw_text.insert("1.0", pretty)
        except json.JSONDecodeError as e:
            if self._on_status:
                self._on_status(f"Invalid JSON: {e}")

    # ---- Auth ----

    def _build_auth_tab(self) -> None:
        tab = self._tabview.tab("Auth")

        type_frame = ctk.CTkFrame(tab, corner_radius=0, fg_color="transparent")
        type_frame.pack(fill="x", pady=(4, 8))

        ctk.CTkLabel(
            type_frame, text="Auth Type:", font=("Segoe UI", 12)
        ).pack(side="left", padx=(0, 8))

        self._auth_type_var = ctk.StringVar(value="none")
        ctk.CTkOptionMenu(
            type_frame,
            variable=self._auth_type_var,
            values=["none", "bearer", "basic", "api-key"],
            width=150,
            height=30,
            font=("Segoe UI", 12),
            command=self._on_auth_type_change,
        ).pack(side="left")

        # Auth form container
        self._auth_form_frame = ctk.CTkFrame(tab, corner_radius=0, fg_color="transparent")
        self._auth_form_frame.pack(fill="both", expand=True)

        self._build_auth_bearer()
        self._build_auth_basic()
        self._build_auth_apikey()

        self._show_auth_panel("none")

    def _build_auth_bearer(self) -> None:
        self._auth_bearer_frame = ctk.CTkFrame(
            self._auth_form_frame, corner_radius=0, fg_color="transparent"
        )
        ctk.CTkLabel(
            self._auth_bearer_frame, text="Token:", font=("Segoe UI", 12), anchor="w"
        ).pack(fill="x", pady=(0, 4))
        self._bearer_token_var = ctk.StringVar()
        ctk.CTkEntry(
            self._auth_bearer_frame,
            textvariable=self._bearer_token_var,
            placeholder_text="Bearer token…",
            font=(FONT_MONO, 12),
            height=32,
        ).pack(fill="x")

    def _build_auth_basic(self) -> None:
        self._auth_basic_frame = ctk.CTkFrame(
            self._auth_form_frame, corner_radius=0, fg_color="transparent"
        )
        for label, attr in [("Username:", "_basic_user_var"), ("Password:", "_basic_pass_var")]:
            ctk.CTkLabel(
                self._auth_basic_frame, text=label, font=("Segoe UI", 12), anchor="w"
            ).pack(fill="x", pady=(4, 2))
            var = ctk.StringVar()
            setattr(self, attr, var)
            show = "*" if "pass" in attr else ""
            ctk.CTkEntry(
                self._auth_basic_frame,
                textvariable=var,
                font=(FONT_MONO, 12),
                height=32,
                show=show,
            ).pack(fill="x")

    def _build_auth_apikey(self) -> None:
        self._auth_apikey_frame = ctk.CTkFrame(
            self._auth_form_frame, corner_radius=0, fg_color="transparent"
        )
        # Key name
        ctk.CTkLabel(
            self._auth_apikey_frame, text="Key Name:", font=("Segoe UI", 12), anchor="w"
        ).pack(fill="x", pady=(0, 2))
        self._apikey_name_var = ctk.StringVar(value="X-API-Key")
        ctk.CTkEntry(
            self._auth_apikey_frame,
            textvariable=self._apikey_name_var,
            font=(FONT_MONO, 12),
            height=32,
        ).pack(fill="x")

        # Key value
        ctk.CTkLabel(
            self._auth_apikey_frame, text="Key Value:", font=("Segoe UI", 12), anchor="w"
        ).pack(fill="x", pady=(8, 2))
        self._apikey_value_var = ctk.StringVar()
        ctk.CTkEntry(
            self._auth_apikey_frame,
            textvariable=self._apikey_value_var,
            font=(FONT_MONO, 12),
            height=32,
        ).pack(fill="x")

        # Location
        ctk.CTkLabel(
            self._auth_apikey_frame, text="Add to:", font=("Segoe UI", 12), anchor="w"
        ).pack(fill="x", pady=(8, 2))
        self._apikey_in_var = ctk.StringVar(value="header")
        loc_frame = ctk.CTkFrame(
            self._auth_apikey_frame, corner_radius=0, fg_color="transparent"
        )
        loc_frame.pack(fill="x")
        for loc in ["header", "query param"]:
            ctk.CTkRadioButton(
                loc_frame,
                text=loc,
                variable=self._apikey_in_var,
                value=loc,
            ).pack(side="left", padx=(0, 12))

    def _on_auth_type_change(self, value: str) -> None:
        self._show_auth_panel(value)

    def _show_auth_panel(self, auth_type: str) -> None:
        for frame in (
            self._auth_bearer_frame,
            self._auth_basic_frame,
            self._auth_apikey_frame,
        ):
            frame.pack_forget()

        if auth_type == "bearer":
            self._auth_bearer_frame.pack(fill="x", pady=4)
        elif auth_type == "basic":
            self._auth_basic_frame.pack(fill="x", pady=4)
        elif auth_type == "api-key":
            self._auth_apikey_frame.pack(fill="x", pady=4)

    # ---- Settings (per-request override) ----

    def _build_settings_tab(self) -> None:
        tab = self._tabview.tab("Settings")
        pad = {"padx": 8, "pady": 4}

        # Timeout override
        row1 = ctk.CTkFrame(tab, corner_radius=0, fg_color="transparent")
        row1.pack(fill="x", **pad)
        ctk.CTkLabel(row1, text="Timeout (seconds):", font=("Segoe UI", 12), width=160, anchor="w").pack(side="left")
        self._timeout_var = ctk.StringVar()
        ctk.CTkEntry(
            row1,
            textvariable=self._timeout_var,
            placeholder_text=f"Default: {self._settings.get('default_timeout', 30)}",
            width=120,
            height=30,
            font=(FONT_MONO, 12),
        ).pack(side="left")
        ctk.CTkLabel(
            row1, text="(leave empty = use global)", font=("Segoe UI", 10), text_color="#888"
        ).pack(side="left", padx=8)

        # Follow redirects
        row2 = ctk.CTkFrame(tab, corner_radius=0, fg_color="transparent")
        row2.pack(fill="x", **pad)
        ctk.CTkLabel(row2, text="Follow Redirects:", font=("Segoe UI", 12), width=160, anchor="w").pack(side="left")
        self._follow_redirects_var = ctk.BooleanVar(value=self._settings.get("follow_redirects", True))
        ctk.CTkCheckBox(row2, text="", variable=self._follow_redirects_var, width=28).pack(side="left")

        # Verify SSL
        row3 = ctk.CTkFrame(tab, corner_radius=0, fg_color="transparent")
        row3.pack(fill="x", **pad)
        ctk.CTkLabel(row3, text="Verify SSL:", font=("Segoe UI", 12), width=160, anchor="w").pack(side="left")
        self._verify_ssl_var = ctk.BooleanVar(value=self._settings.get("verify_ssl", True))
        ctk.CTkCheckBox(row3, text="", variable=self._verify_ssl_var, width=28).pack(side="left")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_profile(self, profile: RequestProfile, is_saved: bool = False) -> None:
        self._current_profile_id = profile.id
        # Enable delete only for profiles that exist on disk
        self._delete_btn.configure(state="normal" if is_saved else "disabled")
        self._method_var.set(profile.method)
        self._apply_method_color()
        self._url_var.set(profile.url)

        # Params
        self._params_editor.set_data(profile.params)

        # Headers
        self._headers_editor.set_data(profile.headers)

        # Body
        self._body_type_var.set(profile.body_type)
        self._show_body_panel(profile.body_type)
        self._body_raw_text.delete("1.0", "end")
        self._body_raw_text.insert("1.0", profile.body_content)
        self._body_form_editor.set_data(profile.body_form)

        # Auth
        self._auth_type_var.set(profile.auth_type)
        self._show_auth_panel(profile.auth_type)
        if profile.auth_type == "bearer":
            self._bearer_token_var.set(profile.auth_data.get("token", ""))
        elif profile.auth_type == "basic":
            self._basic_user_var.set(profile.auth_data.get("username", ""))
            self._basic_pass_var.set(profile.auth_data.get("password", ""))
        elif profile.auth_type == "api-key":
            self._apikey_name_var.set(profile.auth_data.get("key", "X-API-Key"))
            self._apikey_value_var.set(profile.auth_data.get("value", ""))
            self._apikey_in_var.set(profile.auth_data.get("in", "header"))

        # Settings
        self._timeout_var.set(str(profile.timeout) if profile.timeout is not None else "")
        self._follow_redirects_var.set(profile.follow_redirects)
        self._verify_ssl_var.set(profile.verify_ssl)

        self._clear_dirty()

    def get_current_profile(self) -> RequestProfile:
        """Build a RequestProfile from current UI state."""
        # Timeout
        timeout_str = self._timeout_var.get().strip()
        try:
            timeout = float(timeout_str) if timeout_str else None
        except ValueError:
            timeout = None

        # Auth
        auth_type = self._auth_type_var.get()
        auth_data = self._collect_auth_data(auth_type)

        # Body
        body_type = self._body_type_var.get()
        body_content = ""
        body_form: dict[str, str] = {}

        if body_type == "raw":
            body_content = self._body_raw_text.get("1.0", "end-1c")
            # Inject Content-Type header if not already set
            ct = self._raw_ct_var.get()
            headers = self._headers_editor.get_data()
            if "Content-Type" not in headers and ct:
                headers["Content-Type"] = ct
                self._headers_editor.set_data(headers)
        elif body_type in ("form-data", "x-www-form-urlencoded"):
            body_form = self._body_form_editor.get_data()

        # Params with api-key in query support
        params = self._params_editor.get_data()
        if auth_type == "api-key" and self._apikey_in_var.get() == "query param":
            key_name  = self._apikey_name_var.get() or "api_key"
            key_value = self._apikey_value_var.get()
            params[key_name] = key_value

        return RequestProfile(
            name="Untitled",
            url=self._url_var.get().strip(),
            method=self._method_var.get(),
            headers=self._headers_editor.get_data(),
            params=params,
            body_type=body_type,
            body_content=body_content,
            body_form=body_form,
            auth_type=auth_type,
            auth_data=auth_data,
            timeout=timeout,
            follow_redirects=self._follow_redirects_var.get(),
            verify_ssl=self._verify_ssl_var.get(),
        )

    def _collect_auth_data(self, auth_type: str) -> dict[str, str]:
        if auth_type == "bearer":
            return {"token": self._bearer_token_var.get()}
        elif auth_type == "basic":
            return {
                "username": self._basic_user_var.get(),
                "password": self._basic_pass_var.get(),
            }
        elif auth_type == "api-key":
            return {
                "key":   self._apikey_name_var.get(),
                "value": self._apikey_value_var.get(),
                "in":    self._apikey_in_var.get().replace(" ", "_"),  # "query_param"
            }
        return {}

    # ------------------------------------------------------------------
    # Send logic
    # ------------------------------------------------------------------

    def _send_request(self) -> None:
        url = self._url_var.get().strip()
        if not url:
            self._show_url_error()
            return
        if self._sending:
            return

        self._sending = True
        self._send_btn.configure(state="disabled", text="Sending…")
        if self._on_status:
            self._on_status("Sending request…")

        profile = self.get_current_profile()
        timeout         = self._settings.get("default_timeout", 30.0)
        proxy_enabled   = self._settings.get("proxy_enabled", False)
        proxy_http      = self._settings.get("proxy_http", "")
        proxy_https     = self._settings.get("proxy_https", "")

        threading.Thread(
            target=self._do_send,
            args=(profile, timeout, proxy_enabled, proxy_http, proxy_https),
            daemon=True,
        ).start()

    def _do_send(
        self,
        profile: RequestProfile,
        timeout: float,
        proxy_enabled: bool = False,
        proxy_http: str = "",
        proxy_https: str = "",
    ) -> None:
        result = self._http_client.send(
            profile,
            default_timeout=timeout,
            proxy_enabled=proxy_enabled,
            proxy_http=proxy_http,
            proxy_https=proxy_https,
        )
        self.after(0, self._on_send_done, result)

    def _on_send_done(self, result: ResponseResult) -> None:
        self._sending = False
        self._send_btn.configure(state="normal", text="SEND")
        if self._on_response:
            self._on_response(result)
        if self._on_status:
            if result.is_error:
                self._on_status(f"Error: {result.error}")
            else:
                self._on_status(
                    f"{result.status_code} {result.status_text}  •  "
                    f"{result.elapsed_human}  •  {result.size_human}"
                )

    def apply_settings(self) -> None:
        """Re-apply font size from settings to editable text widgets."""
        size = self._settings.get("font_size", 13)
        font_mono = ("Courier New", size)
        font_ui   = ("Segoe UI", size)
        try:
            self._url_entry.configure(font=(font_mono[0], size + 1))
            self._body_raw_text.configure(font=font_mono)
        except Exception:
            pass

    def _save_profile(self) -> None:
        if self._on_save:
            self._on_save(self.get_current_profile())

    def _delete_profile(self) -> None:
        if not self._current_profile_id or not self._on_delete:
            return
        import tkinter.messagebox as mb
        # Get current profile name for confirmation message
        profile = self.get_current_profile()
        name = profile.name if profile.name and profile.name != "Untitled" else "this profile"
        if mb.askyesno(
            "Delete Profile",
            f"Delete '{name}'?\nThis action cannot be undone.",
            icon="warning",
        ):
            self._on_delete(self._current_profile_id)

    def _mark_dirty(self) -> None:
        if not self._is_dirty:
            self._is_dirty = True
            self._save_btn.configure(text="Save •")

    def _clear_dirty(self) -> None:
        self._is_dirty = False
        self._save_btn.configure(text="Save")

    def clear_profile(self) -> None:
        """Reset panel to empty state (called after profile deletion)."""
        self._current_profile_id = None
        self._delete_btn.configure(state="disabled")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _on_method_change(self, _value: str) -> None:
        self._apply_method_color()

    def _apply_method_color(self) -> None:
        method = self._method_var.get()
        color  = METHOD_COLORS.get(method, "#61affe")
        self._method_menu.configure(fg_color=color, button_color=color)

    def _show_url_error(self) -> None:
        self._url_entry.configure(border_color="#f93e3e")
        self.after(2000, lambda: self._url_entry.configure(border_color="#555555"))
        if self._on_status:
            self._on_status("URL cannot be empty.")
