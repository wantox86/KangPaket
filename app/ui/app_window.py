"""
KangPaket — Main application window (Sprint 4: full profile integration).
"""
from __future__ import annotations

import tkinter as tk
import tkinter.filedialog as fd
import tkinter.messagebox as mb
import customtkinter as ctk

from app.config import APP_TITLE, ASSETS_DIR
from app.core.profile_manager import ProfileManager
from app.core.settings_manager import SettingsManager
from app.models.request_model import RequestProfile
from app.models.response_model import ResponseResult
from app.ui.sidebar import Sidebar
from app.ui.request_panel import RequestPanel
from app.ui.response_panel import ResponsePanel
from app.ui.widgets.status_bar import StatusBar


class AppWindow:
    def __init__(self, settings: SettingsManager) -> None:
        self._settings = settings
        self._pm       = ProfileManager()

        theme = settings.get("theme", "dark")
        ctk.set_appearance_mode(theme)
        ctk.set_default_color_theme("blue")

        self._root = ctk.CTk()
        self._root.title(APP_TITLE)
        self._root.geometry("1280x780")
        self._root.minsize(900, 600)
        self._set_window_icon()

        self._build_layout()
        self._build_menu()
        self._bind_shortcuts()

    # ------------------------------------------------------------------
    # Window icon
    # ------------------------------------------------------------------

    def _set_window_icon(self) -> None:
        import os, sys
        ico_path = os.path.join(ASSETS_DIR, "KangPaket-ico.ico")
        png_path = os.path.join(ASSETS_DIR, "KangPaket-ico.png")
        try:
            if sys.platform == "win32" and os.path.exists(ico_path):
                self._root.iconbitmap(ico_path)
            elif os.path.exists(png_path):
                from PIL import Image, ImageTk
                img = Image.open(png_path)
                photo = ImageTk.PhotoImage(img)
                self._root.iconphoto(True, photo)
                # Keep reference so it's not garbage-collected
                self._icon_photo = photo
        except Exception as e:
            print(f"[AppWindow] Could not set window icon: {e}")

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        # Status bar (bottom)
        self._status_bar = StatusBar(self._root)
        self._status_bar.pack(side="bottom", fill="x")

        # Main 3-panel container
        main = ctk.CTkFrame(self._root, corner_radius=0, fg_color="transparent")
        main.pack(fill="both", expand=True)

        # Left: Sidebar
        self._sidebar = Sidebar(
            main,
            profile_manager=self._pm,
            on_select=self._on_profile_select,
            on_new_request=self._new_request,
            on_open_dialog=self._open_save_dialog,
            on_run_collection=self._open_runner,
            on_delete=self._on_profile_deleted,
            on_delete_collection=self._on_collection_deleted,
        )
        self._sidebar.pack(side="left", fill="y")

        # Vertical divider
        ctk.CTkFrame(main, width=1, corner_radius=0, fg_color="#333").pack(
            side="left", fill="y"
        )

        # Right area
        right = ctk.CTkFrame(main, corner_radius=0, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)

        # Vertical PanedWindow: request (top) + response (bottom)
        self._paned = tk.PanedWindow(
            right, orient=tk.VERTICAL,
            sashrelief=tk.FLAT, sashwidth=4,
            bg="#1a1a2e",
        )
        self._paned.pack(fill="both", expand=True)

        self._request_panel = RequestPanel(
            self._paned,
            settings=self._settings,
            on_response=self._on_response,
            on_status=self._status_bar.set_text,
            on_save=self._open_save_dialog,
            on_delete=self._on_delete_profile,
        )
        self._paned.add(self._request_panel, minsize=220)

        self._response_panel = ResponsePanel(self._paned, settings=self._settings)
        self._paned.add(self._response_panel, minsize=160)

        self._root.after(100, lambda: self._paned.sash_place(0, 0, 340))

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = tk.Menu(self._root)

        # --- File ---
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(
            label="New Request", command=self._new_request, accelerator="Ctrl+N"
        )
        file_menu.add_command(
            label="Save Profile", command=self._save_current, accelerator="Ctrl+S"
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Export Profiles…", command=self._export_profiles, accelerator="Ctrl+E"
        )
        file_menu.add_command(label="Import Profiles…", command=self._import_profiles)
        file_menu.add_separator()
        file_menu.add_command(label="Import from Postman…", command=self._import_postman)
        file_menu.add_separator()
        file_menu.add_command(label="Settings", command=self._open_settings, accelerator="Ctrl+,")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        # --- Tools ---
        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Collection Runner", command=self._open_runner)
        tools_menu.add_separator()
        tools_menu.add_command(
            label="Clear Response", command=self._clear_response, accelerator="Ctrl+L"
        )
        tools_menu.add_command(label="Copy Response Body", command=self._response_panel._copy_body)
        tools_menu.add_command(label="Copy as cURL", command=self._copy_as_curl)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        # --- Help ---
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About KangPaket", command=self._about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self._root.configure(menu=menubar)

    def _bind_shortcuts(self) -> None:
        self._root.bind("<Control-n>",      lambda _: self._new_request())
        self._root.bind("<Control-s>",      lambda _: self._save_current())
        self._root.bind("<Control-Return>", lambda _: self._request_panel._send_request())
        self._root.bind("<Control-comma>",  lambda _: self._open_settings())
        self._root.bind("<Control-e>",      lambda _: self._export_profiles())
        self._root.bind("<Control-l>",      lambda _: self._response_panel.clear())

    # ------------------------------------------------------------------
    # Profile actions
    # ------------------------------------------------------------------

    def _on_profile_select(self, profile: RequestProfile) -> None:
        self._request_panel.load_profile(profile, is_saved=True)
        self._response_panel.clear()
        self._status_bar.set_text(f"Loaded: {profile.name}")

    def _on_delete_profile(self, profile_id: str) -> None:
        """Delete profil dari disk (dipanggil dari tombol Delete di request panel)."""
        try:
            self._pm.delete_profile(profile_id)
        except RuntimeError as e:
            mb.showerror("Delete Failed", str(e))
            return
        self._new_request()
        self._sidebar.refresh(keep_selection=False)
        self._status_bar.set_text("Profile deleted.")

    def _on_profile_deleted(self, profile_id: str) -> None:
        """Dipanggil dari sidebar saat profil dihapus via context menu."""
        if self._request_panel._current_profile_id == profile_id:
            self._new_request()
            self._status_bar.set_text("Profile deleted.")

    def _on_collection_deleted(self, deleted_ids: list[str]) -> None:
        """Dipanggil dari sidebar saat collection dihapus."""
        if self._request_panel._current_profile_id in deleted_ids:
            self._new_request()
        self._status_bar.set_text(f"Collection deleted ({len(deleted_ids)} request(s) removed).")

    def _new_request(self) -> None:
        empty = RequestProfile(
            name="Untitled",
            url="",
            collection=self._settings.get("default_collection", "Default"),
        )
        self._request_panel.load_profile(empty)
        self._response_panel.clear()
        self._sidebar.select_profile("")
        self._status_bar.ready()

    def _save_current(self) -> None:
        self._open_save_dialog(self._request_panel.get_current_profile())

    def _open_save_dialog(self, profile: RequestProfile) -> None:
        from app.ui.profile_dialog import ProfileDialog

        # If editing an existing saved profile, pre-fill its name/collection
        existing_id = self._request_panel._current_profile_id
        saved = self._pm.get_profile(existing_id) if existing_id else None

        dialog = ProfileDialog(
            self._root,
            title="Save Profile",
            initial_name=saved.name if saved else profile.name,
            initial_collection=saved.collection if saved else (
                profile.collection or self._settings.get("default_collection", "Default")
            ),
            collections=self._pm.get_collections(),
        )
        self._root.wait_window(dialog)

        if not dialog.confirmed:
            return

        profile.name       = dialog.name
        profile.collection = dialog.collection

        # Reuse existing ID if updating same profile
        if saved:
            profile.id = saved.id

        self._pm.save_profile(profile)
        self._request_panel._current_profile_id = profile.id
        self._request_panel._clear_dirty()
        self._request_panel._delete_btn.configure(state="normal")
        self._sidebar.refresh(keep_selection=True)
        self._sidebar.select_profile(profile.id)
        self._status_bar.set_text(f"Saved: {profile.name}")

    # ------------------------------------------------------------------
    # Export / Import
    # ------------------------------------------------------------------

    def _export_profiles(self) -> None:
        profiles = self._pm.load_all_profiles()
        if not profiles:
            mb.showinfo("Export", "No profiles to export.")
            return
        path = fd.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            title="Export Profiles",
        )
        if not path:
            return
        try:
            self._pm.export_profiles(profiles, path)
            self._status_bar.set_text(f"Export complete: {len(profiles)} profile(s) → {path}")
        except RuntimeError as e:
            mb.showerror("Export Failed", str(e))

    def _import_profiles(self) -> None:
        path = fd.askopenfilename(
            filetypes=[("JSON files", "*.json")],
            title="Import Profiles",
        )
        if not path:
            return
        try:
            imported = self._pm.import_profiles(path)
            self._sidebar.refresh()
            self._status_bar.set_text(f"Import complete: {len(imported)} profile(s) imported.")
            mb.showinfo("Import Complete", f"{len(imported)} profile(s) successfully imported.")
        except RuntimeError as e:
            mb.showerror("Import Failed", str(e))

    def _import_postman(self) -> None:
        from app.core.postman_importer import (
            parse_postman_file, get_file_size_mb, PostmanImportError
        )
        from app.ui.postman_import_dialog import PostmanImportDialog

        path = fd.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Select Postman Collection",
        )
        if not path:
            return

        # Warn for large files
        size_mb = get_file_size_mb(path)
        if size_mb > 10:
            if not mb.askyesno(
                "Large File",
                f"File is {size_mb:.1f} MB. Processing may take a moment.\n\nContinue?",
            ):
                return

        try:
            result = parse_postman_file(path)
        except PostmanImportError as e:
            mb.showerror("Import Failed", str(e))
            return
        except Exception as e:
            mb.showerror("Import Failed", f"Unexpected error:\n{e}")
            return

        dialog = PostmanImportDialog(
            self._root,
            file_path=path,
            result=result,
            profile_manager=self._pm,
            on_import_done=self._on_postman_import_done,
        )
        self._root.wait_window(dialog)

    def _on_postman_import_done(self, count: int, collection: str) -> None:
        self._sidebar.refresh()
        if count == 0:
            self._status_bar.set_text("0 requests imported — all items could not be converted.")
        else:
            self._status_bar.set_text(f"✅ {count} request(s) imported to '{collection}'")

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------

    def _on_response(self, result: ResponseResult) -> None:
        self._response_panel.show_response(result)

        profile = self._request_panel.get_current_profile()
        if result.is_error:
            self._status_bar.set_error(f"Error: {result.error}")
            self._show_error_dialog(result)
        else:
            self._status_bar.set_request_info(
                method=profile.method,
                url=profile.url,
                status=result.status_code,
                elapsed=result.elapsed_human,
                size=result.size_human,
            )

    def _show_error_dialog(self, result: ResponseResult) -> None:
        """Show a detailed error dialog for failed requests."""
        if result.status_code == 0:
            # Network/connection error — show detailed dialog
            _ErrorDialog(self._root, error=result.error or "Unknown error")

    def _clear_response(self) -> None:
        self._response_panel.clear()

    def _copy_as_curl(self) -> None:
        profile = self._request_panel.get_current_profile()
        curl = self._build_curl(profile)
        self._root.clipboard_clear()
        self._root.clipboard_append(curl)
        self._status_bar.set_text("cURL command copied to clipboard.")

    @staticmethod
    def _build_curl(profile: RequestProfile) -> str:
        parts = [f"curl -X {profile.method}"]
        for k, v in profile.headers.items():
            parts.append(f"  -H '{k}: {v}'")
        if profile.auth_type == "bearer":
            token = profile.auth_data.get("token", "")
            parts.append(f"  -H 'Authorization: Bearer {token}'")
        elif profile.auth_type == "basic":
            u = profile.auth_data.get("username", "")
            p = profile.auth_data.get("password", "")
            parts.append(f"  -u '{u}:{p}'")
        if profile.body_type == "raw" and profile.body_content:
            body = profile.body_content.replace("'", "\\'")
            parts.append(f"  -d '{body}'")
        url = profile.url
        if profile.params:
            import urllib.parse
            qs = urllib.parse.urlencode(profile.params)
            url += ("&" if "?" in url else "?") + qs
        parts.append(f"  '{url}'")
        return " \\\n".join(parts)

    # ------------------------------------------------------------------
    # Dialogs
    # ------------------------------------------------------------------

    def _open_settings(self) -> None:
        from app.ui.settings_dialog import SettingsDialog
        dialog = SettingsDialog(
            self._root,
            settings=self._settings,
            on_apply=self._on_settings_applied,
        )
        self._root.wait_window(dialog)

    def _on_settings_applied(self) -> None:
        """Dipanggil setelah settings disimpan — apply perubahan ke seluruh UI."""
        # Theme
        theme = self._settings.get("theme", "dark")
        ctk.set_appearance_mode(theme)

        # Font size ke request & response panel
        self._request_panel.apply_settings()
        self._response_panel.apply_settings()

        self._status_bar.set_text("Settings saved.")

    def _open_runner(self, preselect_collection: str | None = None) -> None:
        from app.ui.runner_window import RunnerWindow
        win = RunnerWindow(
            self._root,
            profile_manager=self._pm,
            settings=self._settings,
            on_open_profile=self._on_profile_select,
            preselect_collection=preselect_collection,
        )
        self._root.wait_window(win)

    def _about(self) -> None:
        _AboutDialog(self._root)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self) -> None:
        self._root.mainloop()


# ---------------------------------------------------------------------------
# Helper dialogs (module-level, not part of AppWindow)
# ---------------------------------------------------------------------------

class _ErrorDialog(ctk.CTkToplevel):
    """Detailed error dialog for network/connection failures."""

    def __init__(self, parent, error: str) -> None:
        super().__init__(parent)
        self.title("Request Failed")
        self.resizable(False, False)
        self.grab_set()
        self.focus_set()

        # Icon + title
        ctk.CTkLabel(
            self, text="⚠  Request could not be sent",
            font=("Segoe UI", 13, "bold"), text_color="#f93e3e",
        ).pack(padx=20, pady=(16, 4))

        ctk.CTkLabel(
            self, text="Detail error:",
            font=("Segoe UI", 11), text_color="#888", anchor="w",
        ).pack(fill="x", padx=20, pady=(4, 2))

        # Error text box
        box = ctk.CTkTextbox(self, font=("Courier New", 11), height=120, wrap="word")
        box.pack(fill="x", padx=20, pady=(0, 8))
        box.insert("1.0", error)
        box.configure(state="disabled")

        # Tips based on error type
        tip = self._get_tip(error)
        if tip:
            ctk.CTkLabel(
                self, text=f"💡 {tip}",
                font=("Segoe UI", 11), text_color="#fca130",
                wraplength=360, justify="left", anchor="w",
            ).pack(fill="x", padx=20, pady=(0, 8))

        ctk.CTkButton(
            self, text="Close", width=80, height=30,
            command=self.destroy,
        ).pack(pady=(0, 16))

        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width() // 2 - 200
        ph = parent.winfo_rooty() + parent.winfo_height() // 2 - 150
        self.geometry(f"400x300+{pw}+{ph}")

    @staticmethod
    def _get_tip(error: str) -> str:
        e = error.lower()
        if "timeout" in e or "timed out" in e:
            return "Try increasing the Default Timeout in Settings, or check your internet connection."
        if "ssl" in e or "certificate" in e:
            return "Try disabling Verify SSL in the request Settings tab."
        if "connection" in e or "refused" in e:
            return "Make sure the server is running and the URL is correct. Check firewall/proxy if needed."
        if "invalid url" in e:
            return "Check the URL format — must start with http:// or https://"
        return ""


class _AboutDialog(ctk.CTkToplevel):
    """About dialog."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.title("About KangPaket")
        self.resizable(False, False)
        self.grab_set()
        self.focus_set()

        from app.config import APP_VERSION
        import sys

        ctk.CTkLabel(
            self, text="KangPaket",
            font=("Segoe UI", 22, "bold"),
        ).pack(pady=(20, 2))

        ctk.CTkLabel(
            self, text=f"v{APP_VERSION}",
            font=("Segoe UI", 12), text_color="#94a3b8",
        ).pack()

        ctk.CTkFrame(self, height=1, fg_color="#333").pack(fill="x", padx=24, pady=16)

        info = [
            ("Python",        sys.version.split()[0]),
            ("Platform",      sys.platform),
            ("GUI",           "CustomTkinter"),
            ("HTTP",          "httpx"),
        ]
        for label, value in info:
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", padx=24, pady=2)
            ctk.CTkLabel(row, text=label, font=("Segoe UI", 11), width=80, anchor="w",
                         text_color="#64748b").pack(side="left")
            ctk.CTkLabel(row, text=value, font=("Courier New", 11), anchor="w").pack(side="left")

        ctk.CTkFrame(self, height=1, fg_color="#333").pack(fill="x", padx=24, pady=16)

        ctk.CTkLabel(
            self,
            text="Built for internal use.\nA lightweight, offline Postman alternative.",
            font=("Segoe UI", 11), text_color="#64748b", justify="center",
        ).pack(pady=(0, 4))

        ctk.CTkButton(
            self, text="Close", width=80, height=30,
            command=self.destroy,
        ).pack(pady=(8, 20))

        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width() // 2 - 175
        ph = parent.winfo_rooty() + parent.winfo_height() // 2 - 180
        self.geometry(f"350x360+{pw}+{ph}")
