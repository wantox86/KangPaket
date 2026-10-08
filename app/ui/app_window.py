"""
KangPaket — Main application window (Sprint 4: full profile integration).
"""
from __future__ import annotations

import time
import tkinter as tk
import tkinter.filedialog as fd
import tkinter.messagebox as mb
import customtkinter as ctk

from app.config import APP_TITLE, ASSETS_DIR
from app.core.environment_manager import EnvironmentManager
from app.core.profile_manager import ProfileManager
from app.models.environment_model import Environment
from app.core.settings_manager import SettingsManager
from app.core.sync_client import SyncClient, resolve_server_url
from app.core.sync_controller import SyncUiController
from app.core.sync_manager import SyncManager, SyncPhase, SyncResult, SyncStatus
from app.core.sync_presenter import (
    ACTION_CLOSE, ACTION_RELOAD, ACTION_WARN_CHANGED, ACTION_WARN_DELETED,
    LEVEL_COLORS, decide_open_profile_action, status_view,
)
from app.core.sync_state import SyncState
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
        self._environments = EnvironmentManager()

        theme = settings.get("theme", "dark")
        ctk.set_appearance_mode(theme)
        ctk.set_default_color_theme("blue")

        self._root = ctk.CTk()
        self._root.title(APP_TITLE)
        self._root.geometry("1280x780")
        self._root.minsize(900, 600)
        self._set_window_icon()

        self._env_dialog = None
        self._sync_dialog = None
        self._closing = False
        self._sync_status_at = time.monotonic()
        self._init_sync()

        self._build_layout()
        self._build_menu()
        self._bind_shortcuts()
        self._start_sync()
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

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

        # Environment selector (top bar)
        topbar = ctk.CTkFrame(self._root, height=32, corner_radius=0)
        topbar.pack(side="top", fill="x")
        self._env_menu = ctk.CTkOptionMenu(
            topbar, values=["No Environment"], width=200, height=24,
            font=("Segoe UI", 12), command=self._on_env_selected,
        )
        self._env_menu.pack(side="right", padx=8, pady=4)
        ctk.CTkLabel(topbar, text="Environment:", font=("Segoe UI", 12)).pack(
            side="right", pady=4
        )
        self._environments.on_change(self._refresh_env_menu)
        self._refresh_env_menu()

        # Cloud Sync account entry (left side of the top bar)
        self._sync_btn = ctk.CTkButton(
            topbar, text="☁  Belum login", height=24, width=160, anchor="w",
            font=("Segoe UI", 12), fg_color="transparent", hover_color=("gray85", "gray25"),
            text_color=LEVEL_COLORS["muted"], command=self._open_account,
        )
        self._sync_btn.pack(side="left", padx=8, pady=4)
        self._render_sync_status()
        self._root.after(15000, self._tick_sync_label)

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
            environments=self._environments,
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
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        # --- Tools ---
        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Collection Runner", command=self._open_runner)
        tools_menu.add_command(label="Environments…", command=self._open_environments)
        tools_menu.add_command(label="Akun Cloud Sync…", command=self._open_account)
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
        self._request_panel.loaded_updated_at = profile.updated_at
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
            parse_postman_file, get_file_size_mb, is_postman_environment_file,
            PostmanImportError,
        )
        from app.ui.postman_import_dialog import PostmanImportDialog

        path = fd.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Select Postman Collection or Environment",
        )
        if not path:
            return

        if is_postman_environment_file(path):
            self._import_postman_environment(path)
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
            on_import_done=lambda count, col: self._on_postman_import_done(count, col, result),
        )
        self._root.wait_window(dialog)

    def _on_postman_import_done(self, count: int, collection: str, result=None) -> None:
        self._sidebar.refresh()
        if count == 0:
            self._status_bar.set_text("0 requests imported — all items could not be converted.")
            return
        msg = f"✅ {count} request(s) imported to '{collection}'"
        if result is not None and result.variables:
            env = self._add_environment(result.collection_name, result.variables)
            msg += f"; environment '{env.name}' created and activated"
        self._status_bar.set_text(msg)

    def _import_postman_environment(self, path: str) -> None:
        from app.core.postman_importer import parse_postman_environment, PostmanImportError
        try:
            env = parse_postman_environment(path)
        except PostmanImportError as e:
            mb.showerror("Import Failed", str(e))
            return
        env = self._add_environment(env.name, env.vars)
        self._status_bar.set_text(
            f"✅ Environment '{env.name}' imported ({len(env.vars)} variable(s)) and activated"
        )

    def _add_environment(self, name: str, variables) -> Environment:
        env = self._environments.add(
            Environment(self._environments.unique_name(name), list(variables))
        )
        self._environments.set_active(env.id)
        return env

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
            environments=self._environments,
            on_open_profile=self._on_profile_select,
            preselect_collection=preselect_collection,
        )
        self._root.wait_window(win)

    def _open_environments(self) -> None:
        from app.ui.environment_dialog import EnvironmentDialog
        dlg = EnvironmentDialog(self._root, self._environments)
        self._env_dialog = dlg
        dlg.bind("<Destroy>", lambda e, d=dlg: self._env_dialog_closed(d, e), add="+")

    def _env_dialog_closed(self, dlg, event) -> None:
        if event.widget is dlg and self._env_dialog is dlg:
            self._env_dialog = None

    def _refresh_env_menu(self) -> None:
        names = ["No Environment"] + [e.name for e in self._environments.envs]
        active = self._environments.active
        self._env_menu.configure(values=names)
        self._env_menu.set(active.name if active else "No Environment")

    def _on_env_selected(self, name: str) -> None:
        env = next((e for e in self._environments.envs if e.name == name), None)
        self._environments.set_active(env.id if env else None)
        self._status_bar.set_text(f"Environment: {name}")

    def _about(self) -> None:
        _AboutDialog(self._root)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self) -> None:
        self._root.mainloop()

    # ------------------------------------------------------------------
    # Cloud Sync
    # ------------------------------------------------------------------

    def _init_sync(self) -> None:
        """Create state/client/manager once. Callbacks come from the runner thread -> marshalled."""
        self._sync_state = SyncState()
        self._sync_client = SyncClient(
            self._sync_state, resolve_server_url(self._settings, self._sync_state)
        )
        self._sync = SyncManager(
            self._pm, self._environments, self._sync_state, self._sync_client,
            on_status=lambda st: self._ui(self._on_sync_status, st),
            on_data_changed=lambda res: self._ui(self._on_sync_data_changed, res),
        )
        self._sync_ctl = SyncUiController(self._sync, dispatch=self._ui)

    def _start_sync(self) -> None:
        self._sync.attach()
        self._sync.start()

    def _ui(self, fn, *args) -> None:
        """Run fn(*args) on the UI thread; safe to call from any thread, even while closing."""
        if self._closing:
            return

        def run() -> None:
            if self._closing:
                return
            try:
                fn(*args)
            except tk.TclError:
                pass   # widget destroyed meanwhile
            except Exception as e:
                print(f"[AppWindow] UI callback failed: {e}")

        try:
            self._root.after(0, run)
        except (tk.TclError, RuntimeError):
            pass   # window gone / mainloop not running

    def _default_sync_url(self) -> str:
        return resolve_server_url(self._settings, None)

    def _render_sync_status(self) -> None:
        view = status_view(
            self._sync.status, int(time.time() * 1000), time.monotonic() - self._sync_status_at
        )
        self._sync_btn.configure(text=f"☁  {view.text}", text_color=LEVEL_COLORS[view.level])

    def _tick_sync_label(self) -> None:
        if self._closing:
            return
        try:
            self._render_sync_status()
            if self._sync_dialog is not None:
                self._sync_dialog.update_status()
            self._root.after(15000, self._tick_sync_label)
        except tk.TclError:
            pass

    def _on_sync_status(self, status: SyncStatus) -> None:
        self._sync_status_at = time.monotonic()
        self._render_sync_status()
        dlg = self._sync_dialog
        if dlg is not None:
            dlg.note_status_received()
            dlg.update_status()

    def _on_sync_data_changed(self, result: SyncResult) -> None:
        """Server data was merged into local storage: refresh everything that shows it."""
        self._sidebar.refresh()
        self._refresh_env_menu()
        if self._env_dialog is not None:
            try:
                self._env_dialog.reload_from_manager()
            except tk.TclError:
                pass
        self._status_bar.set_text(
            f"Cloud Sync: {result.applied_local} diperbarui, {result.deleted_local} dihapus dari server."
        )
        self._reconcile_open_profile()   # may override the status text with a warning

    def _reconcile_open_profile(self) -> None:
        """Safe, simple policy for the profile open in the request panel after a pull."""
        rp = self._request_panel
        pid = rp._current_profile_id
        if not pid:
            return
        disk = self._pm.get_profile(pid)
        action = decide_open_profile_action(
            rp.loaded_updated_at, disk.updated_at if disk else None, disk is not None, rp.is_dirty
        )
        if action == ACTION_RELOAD and disk is not None:
            rp.load_profile(disk, is_saved=True)
            self._status_bar.set_text(f"Cloud Sync: '{disk.name}' diperbarui dari server.")
        elif action == ACTION_CLOSE:
            self._new_request()
            self._status_bar.set_text("Cloud Sync: request yang dibuka dihapus dari server.")
        elif action == ACTION_WARN_CHANGED:
            rp.loaded_updated_at = disk.updated_at if disk else rp.loaded_updated_at
            self._status_bar.set_error(
                "Cloud Sync: profile yang sedang diedit berubah di server. Edit Anda tidak ditimpa; "
                "menyimpan akan menggantikan versi server."
            )
        elif action == ACTION_WARN_DELETED:
            rp.loaded_updated_at = None
            self._status_bar.set_error(
                "Cloud Sync: profile yang sedang diedit dihapus di server. Edit Anda masih ada; "
                "simpan untuk membuatnya lagi."
            )

    def _open_account(self) -> None:
        from app.ui.sync_dialogs import AccountDialog
        if self._sync_dialog is not None:
            try:
                if self._sync_dialog.winfo_exists():
                    self._sync_dialog.focus_set()
                    return
            except tk.TclError:
                pass
            self._sync_dialog = None
        if self._sync.logged_in or self._sync.status.phase == SyncPhase.AUTH_REQUIRED:
            dlg = AccountDialog(
                self._root, self._sync_ctl,
                on_relogin=self._open_login_relogin,
                on_logged_out=self._on_logged_out,
            )
            self._sync_dialog = dlg
            dlg.bind("<Destroy>", lambda e, d=dlg: self._sync_dialog_closed(d, e), add="+")
        else:
            self._open_login()

    def _sync_dialog_closed(self, dlg, event) -> None:
        if event.widget is dlg and self._sync_dialog is dlg:
            self._sync_dialog = None

    def _open_login(self, username: str = "", notice: str = "") -> None:
        from app.ui.sync_dialogs import LoginDialog
        LoginDialog(
            self._root, self._sync_ctl,
            default_url=self._default_sync_url(),
            current_url=self._sync_state.server_url or self._sync_client.base_url,
            username=username, notice=notice,
            on_success=lambda: self._status_bar.set_text(
                "Login berhasil. Menyinkronkan data pertama kali…"),
        )

    def _open_login_relogin(self) -> None:
        self._open_login(
            username=self._sync_state.username,
            notice="Sesi berakhir. Masukkan password untuk login ulang.",
        )

    def _on_logged_out(self) -> None:
        self._render_sync_status()
        self._status_bar.set_text("Logout Cloud Sync. Data lokal tetap ada.")

    def _on_close(self) -> None:
        """Stop the sync runner (briefly) and close; never hangs on an in-flight request."""
        if self._closing:
            return
        self._closing = True
        try:
            self._sync.stop(timeout=1.5)
        except Exception as e:
            print(f"[AppWindow] sync stop failed: {e}")
        try:
            self._root.destroy()
        except tk.TclError:
            pass


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
