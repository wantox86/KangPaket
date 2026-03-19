"""
KangPaket — Response panel (Sprint 3 full implementation).
Tabs: Body | Headers | Cookies | Info
Features: JSON syntax highlight, auto Content-Type detection, Pretty/Raw toggle,
          Copy, Save to File, truncation warning.
"""
from __future__ import annotations

import json
import tkinter as tk
import tkinter.filedialog as fd
import customtkinter as ctk

from app.config import FONT_MONO, status_color
from app.core.settings_manager import SettingsManager
from app.models.response_model import ResponseResult
from app.ui.widgets.json_viewer import JsonViewer


class ResponsePanel(ctk.CTkFrame):
    def __init__(self, parent, settings: SettingsManager | None = None, **kwargs):
        super().__init__(parent, corner_radius=0, **kwargs)
        self._settings = settings
        self._result: ResponseResult | None = None

        self._build_status_bar()
        self._build_tabs()

    # ------------------------------------------------------------------
    # Build — status bar
    # ------------------------------------------------------------------

    def _build_status_bar(self) -> None:
        bar = ctk.CTkFrame(self, corner_radius=0, height=38)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        self._status_label = ctk.CTkLabel(
            bar, text="—", font=("Segoe UI", 13, "bold"), anchor="w"
        )
        self._status_label.pack(side="left", padx=12, pady=6)

        self._time_label = ctk.CTkLabel(
            bar, text="", font=("Segoe UI", 12), text_color="#888888"
        )
        self._time_label.pack(side="left", padx=(8, 0))

        self._size_label = ctk.CTkLabel(
            bar, text="", font=("Segoe UI", 12), text_color="#888888"
        )
        self._size_label.pack(side="left", padx=(12, 0))

        # Right-side buttons (pack right-to-left)
        self._save_btn = ctk.CTkButton(
            bar, text="Save", width=56, height=26,
            font=("Segoe UI", 11),
            fg_color="#374151", hover_color="#4b5563",
            command=self._save_to_file, state="disabled",
        )
        self._save_btn.pack(side="right", padx=(4, 8), pady=6)

        self._copy_btn = ctk.CTkButton(
            bar, text="Copy", width=56, height=26,
            font=("Segoe UI", 11),
            fg_color="#374151", hover_color="#4b5563",
            command=self._copy_body, state="disabled",
        )
        self._copy_btn.pack(side="right", padx=4, pady=6)

    # ------------------------------------------------------------------
    # Build — tabs
    # ------------------------------------------------------------------

    def _build_tabs(self) -> None:
        self._tabview = ctk.CTkTabview(self, anchor="nw")
        self._tabview.pack(fill="both", expand=True)

        for name in ["Body", "Headers", "Cookies", "Info"]:
            self._tabview.add(name)

        self._build_body_tab()
        self._build_headers_tab()
        self._build_cookies_tab()
        self._build_info_tab()

    # ---- Body tab ----

    def _build_body_tab(self) -> None:
        tab = self._tabview.tab("Body")

        # Toolbar row
        toolbar = ctk.CTkFrame(tab, corner_radius=0, fg_color="transparent")
        toolbar.pack(fill="x", pady=(4, 2))

        self._display_mode = ctk.StringVar(value="pretty")
        ctk.CTkRadioButton(
            toolbar, text="Pretty", variable=self._display_mode,
            value="pretty", command=self._refresh_body,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkRadioButton(
            toolbar, text="Raw", variable=self._display_mode,
            value="raw", command=self._refresh_body,
        ).pack(side="left")

        # Truncation warning banner (hidden by default)
        self._trunc_banner = ctk.CTkLabel(
            tab,
            text="⚠ Response truncated — size exceeds maximum limit. Use Save for the full file.",
            font=("Segoe UI", 11),
            text_color="#fca130",
            fg_color="#2a1a00",
            corner_radius=4,
            anchor="w",
        )

        # Body area: JSON viewer (pretty) OR plain textbox (raw/non-JSON)
        self._body_container = ctk.CTkFrame(tab, corner_radius=0, fg_color="transparent")
        self._body_container.pack(fill="both", expand=True, pady=(2, 0))

        self._json_viewer = JsonViewer(self._body_container)
        self._plain_text  = ctk.CTkTextbox(
            self._body_container,
            font=(FONT_MONO, 12),
            wrap="none",
            state="disabled",
        )
        # Start with plain text visible
        self._plain_text.pack(fill="both", expand=True)
        self._active_body_widget = "plain"

    # ---- Headers tab ----

    def _build_headers_tab(self) -> None:
        tab = self._tabview.tab("Headers")

        # Copy All button
        top = ctk.CTkFrame(tab, corner_radius=0, fg_color="transparent")
        top.pack(fill="x", pady=(4, 2))
        ctk.CTkButton(
            top, text="Copy All Headers", width=130, height=26,
            font=("Segoe UI", 11),
            fg_color="#374151", hover_color="#4b5563",
            command=self._copy_all_headers,
        ).pack(side="left")

        # Table frame (scrollable)
        self._headers_frame = ctk.CTkScrollableFrame(
            tab, corner_radius=0, fg_color="transparent"
        )
        self._headers_frame.pack(fill="both", expand=True, pady=(2, 0))

        # Column headers
        hdr = ctk.CTkFrame(self._headers_frame, corner_radius=0, fg_color="#2a2a3a")
        hdr.pack(fill="x", pady=(0, 2))
        ctk.CTkLabel(
            hdr, text="Header", font=("Segoe UI", 11, "bold"),
            width=220, anchor="w",
        ).pack(side="left", padx=8, pady=4)
        ctk.CTkLabel(
            hdr, text="Value", font=("Segoe UI", 11, "bold"), anchor="w"
        ).pack(side="left", fill="x", expand=True, padx=8, pady=4)

        self._header_rows_frame = ctk.CTkFrame(
            self._headers_frame, corner_radius=0, fg_color="transparent"
        )
        self._header_rows_frame.pack(fill="x")

    # ---- Cookies tab ----

    def _build_cookies_tab(self) -> None:
        tab = self._tabview.tab("Cookies")

        self._cookies_frame = ctk.CTkScrollableFrame(
            tab, corner_radius=0, fg_color="transparent"
        )
        self._cookies_frame.pack(fill="both", expand=True, pady=(4, 0))

        # Column headers
        hdr = ctk.CTkFrame(self._cookies_frame, corner_radius=0, fg_color="#2a2a3a")
        hdr.pack(fill="x", pady=(0, 2))
        for col, w in [("Name", 140), ("Value", 200), ("Domain", 140), ("Path", 80), ("Expires", 160)]:
            ctk.CTkLabel(
                hdr, text=col, font=("Segoe UI", 11, "bold"), width=w, anchor="w"
            ).pack(side="left", padx=6, pady=4)

        self._cookie_rows_frame = ctk.CTkFrame(
            self._cookies_frame, corner_radius=0, fg_color="transparent"
        )
        self._cookie_rows_frame.pack(fill="x")

        self._no_cookies_label = ctk.CTkLabel(
            self._cookies_frame,
            text="No cookies.",
            font=("Segoe UI", 12),
            text_color="#888888",
        )

    # ---- Info tab ----

    def _build_info_tab(self) -> None:
        tab = self._tabview.tab("Info")
        self._info_text = ctk.CTkTextbox(
            tab, font=(FONT_MONO, 12), wrap="none", state="disabled"
        )
        self._info_text.pack(fill="both", expand=True, pady=(4, 0))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_response(self, result: ResponseResult) -> None:
        self._result = result
        self._update_status_bar(result)
        self._refresh_body()
        self._populate_headers(result)
        self._populate_cookies(result)
        self._populate_info(result)
        self._copy_btn.configure(state="normal")
        self._save_btn.configure(state="normal")

    def show_loading(self) -> None:
        self._status_label.configure(text="Sending…", text_color="#888888")
        self._time_label.configure(text="")
        self._size_label.configure(text="")
        self._copy_btn.configure(state="disabled")
        self._save_btn.configure(state="disabled")
        self._set_plain_body("Sending request…")

    def clear(self) -> None:
        self._result = None
        self._status_label.configure(text="—", text_color="#ffffff")
        self._time_label.configure(text="")
        self._size_label.configure(text="")
        self._copy_btn.configure(state="disabled")
        self._save_btn.configure(state="disabled")
        self._trunc_banner.pack_forget()
        self._switch_body_widget("plain")
        self._set_plain_body("")
        self._clear_header_rows()
        self._clear_cookie_rows()
        self._set_info_text("")

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _update_status_bar(self, result: ResponseResult) -> None:
        if result.is_error:
            self._status_label.configure(text="ERROR", text_color="#f93e3e")
            self._time_label.configure(text="")
            self._size_label.configure(text="")
        else:
            color = status_color(result.status_code)
            self._status_label.configure(
                text=f"{result.status_code} {result.status_text}",
                text_color=color,
            )
            self._time_label.configure(text=result.elapsed_human)
            self._size_label.configure(text=result.size_human)

    # ------------------------------------------------------------------
    # Body tab
    # ------------------------------------------------------------------

    def _refresh_body(self) -> None:
        if self._result is None:
            return

        result = self._result

        if result.is_error:
            self._trunc_banner.pack_forget()
            self._switch_body_widget("plain")
            self._set_plain_body(f"ERROR:\n\n{result.error}")
            return

        # Truncation check
        max_mb   = self._settings.get("max_response_size_mb", 10) if self._settings else 10
        max_bytes = max_mb * 1024 * 1024
        body      = result.body
        truncated = False
        if result.size_bytes > max_bytes:
            # Truncate by char count (approx)
            body      = body[: max_bytes] + "\n\n… [TRUNCATED]"
            truncated = True

        if truncated:
            self._trunc_banner.pack(fill="x", pady=(2, 0), before=self._body_container)
        else:
            self._trunc_banner.pack_forget()

        mode = self._display_mode.get()

        if mode == "pretty":
            ct = result.headers.get("content-type", "")
            if "application/json" in ct or self._looks_like_json(body):
                self._switch_body_widget("json")
                self._json_viewer.set_json(body)
                return
            # Non-JSON pretty: just display raw (images handled below)
            if ct.startswith("image/"):
                self._switch_body_widget("plain")
                self._set_plain_body("[Image response — use Save to File]")
                return

        # Raw mode or non-JSON content type
        self._switch_body_widget("plain")
        self._set_plain_body(body)

    def _switch_body_widget(self, mode: str) -> None:
        """Toggle between json_viewer and plain_text in body_container."""
        if mode == "json" and self._active_body_widget != "json":
            self._plain_text.pack_forget()
            self._json_viewer.pack(fill="both", expand=True)
            self._active_body_widget = "json"
        elif mode == "plain" and self._active_body_widget != "plain":
            self._json_viewer.pack_forget()
            self._plain_text.pack(fill="both", expand=True)
            self._active_body_widget = "plain"

    def _set_plain_body(self, text: str) -> None:
        self._plain_text.configure(state="normal")
        self._plain_text.delete("1.0", "end")
        self._plain_text.insert("1.0", text)
        self._plain_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Headers tab
    # ------------------------------------------------------------------

    def _populate_headers(self, result: ResponseResult) -> None:
        self._clear_header_rows()
        if result.is_error:
            return
        for name, value in result.headers.items():
            row = ctk.CTkFrame(
                self._header_rows_frame, corner_radius=0, fg_color="transparent"
            )
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(
                row, text=name, font=(FONT_MONO, 11),
                width=220, anchor="w", text_color="#7dd3fc",
            ).pack(side="left", padx=8, pady=2)
            ctk.CTkLabel(
                row, text=value, font=(FONT_MONO, 11), anchor="w",
            ).pack(side="left", fill="x", expand=True, padx=8, pady=2)

    def _clear_header_rows(self) -> None:
        for widget in self._header_rows_frame.winfo_children():
            widget.destroy()

    def _copy_all_headers(self) -> None:
        if self._result is None or self._result.is_error:
            return
        lines = [f"{k}: {v}" for k, v in self._result.headers.items()]
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))

    # ------------------------------------------------------------------
    # Cookies tab
    # ------------------------------------------------------------------

    def _populate_cookies(self, result: ResponseResult) -> None:
        self._clear_cookie_rows()
        cookies = self._parse_cookies(result)

        if not cookies:
            self._no_cookies_label.pack(pady=16)
            return

        self._no_cookies_label.pack_forget()
        for ck in cookies:
            row = ctk.CTkFrame(
                self._cookie_rows_frame, corner_radius=0, fg_color="transparent"
            )
            row.pack(fill="x", pady=1)
            for text, w in [
                (ck.get("name", ""), 140),
                (ck.get("value", ""), 200),
                (ck.get("domain", ""), 140),
                (ck.get("path", "/"), 80),
                (ck.get("expires", ""), 160),
            ]:
                ctk.CTkLabel(
                    row, text=text, font=(FONT_MONO, 11),
                    width=w, anchor="w", wraplength=w - 8,
                ).pack(side="left", padx=6, pady=2)

    def _clear_cookie_rows(self) -> None:
        self._no_cookies_label.pack_forget()
        for widget in self._cookie_rows_frame.winfo_children():
            widget.destroy()

    @staticmethod
    def _parse_cookies(result: ResponseResult) -> list[dict]:
        """Parse Set-Cookie headers into list of dicts."""
        if result.is_error:
            return []
        cookies = []
        for header_name, header_val in result.headers.items():
            if header_name.lower() != "set-cookie":
                continue
            parts = [p.strip() for p in header_val.split(";")]
            if not parts:
                continue
            name_val = parts[0].split("=", 1)
            ck: dict = {
                "name":    name_val[0].strip() if name_val else "",
                "value":   name_val[1].strip() if len(name_val) > 1 else "",
                "domain":  "",
                "path":    "/",
                "expires": "",
            }
            for attr in parts[1:]:
                attr_lower = attr.lower()
                if attr_lower.startswith("domain="):
                    ck["domain"] = attr.split("=", 1)[1]
                elif attr_lower.startswith("path="):
                    ck["path"] = attr.split("=", 1)[1]
                elif attr_lower.startswith("expires="):
                    ck["expires"] = attr.split("=", 1)[1]
            cookies.append(ck)
        return cookies

    # ------------------------------------------------------------------
    # Info tab
    # ------------------------------------------------------------------

    def _populate_info(self, result: ResponseResult) -> None:
        lines = [
            f"Timestamp  : {result.timestamp}",
            f"Status     : {result.status_code} {result.status_text}",
            f"Elapsed    : {result.elapsed_human}",
            f"Size       : {result.size_human} ({result.size_bytes} bytes)",
        ]
        if result.is_error:
            lines += ["", "─" * 40, "Error:", result.error or ""]
        self._set_info_text("\n".join(lines))

    def _set_info_text(self, text: str) -> None:
        self._info_text.configure(state="normal")
        self._info_text.delete("1.0", "end")
        self._info_text.insert("1.0", text)
        self._info_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Copy / Save
    # ------------------------------------------------------------------

    def _copy_body(self) -> None:
        if self._result is None:
            return
        self.clipboard_clear()
        self.clipboard_append(self._result.body)

    def _save_to_file(self) -> None:
        if self._result is None:
            return
        ct = self._result.headers.get("content-type", "")
        if "json" in ct:
            default_ext = ".json"
            filetypes   = [("JSON files", "*.json"), ("All files", "*.*")]
        elif "html" in ct:
            default_ext = ".html"
            filetypes   = [("HTML files", "*.html"), ("All files", "*.*")]
        elif "xml" in ct:
            default_ext = ".xml"
            filetypes   = [("XML files", "*.xml"), ("All files", "*.*")]
        else:
            default_ext = ".txt"
            filetypes   = [("Text files", "*.txt"), ("All files", "*.*")]

        path = fd.asksaveasfilename(
            defaultextension=default_ext,
            filetypes=filetypes,
            title="Save Response Body",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._result.body)
        except OSError as e:
            import tkinter.messagebox as mb
            mb.showerror("Save Failed", f"Cannot save file:\n{e}")

    def apply_settings(self) -> None:
        """Re-apply font size from settings to text widgets."""
        if self._settings is None:
            return
        size      = self._settings.get("font_size", 13)
        font_mono = ("Courier New", size)
        try:
            self._plain_text.configure(font=font_mono)
            self._info_text.configure(font=font_mono)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _looks_like_json(text: str) -> bool:
        return text.strip().startswith(("{", "["))
