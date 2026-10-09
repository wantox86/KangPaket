"""
KangPaket — Cloud Sync dialogs: Login and Account (modal CTkToplevel, same style as the other dialogs).
"""
from __future__ import annotations

import time
import tkinter.messagebox as mb
import customtkinter as ctk

from app.core.sync_controller import SyncUiController
from app.core.sync_manager import SyncPhase
from app.core.sync_presenter import (
    CONFIRM_CANCEL, LEVEL_COLORS, LEVEL_ERROR, LEVEL_OK, LOGOUT_CONFIRM_YES, LOGOUT_TITLE,
    SWITCH_CONFIRM_YES, account_switch_text, logout_blockers_text, logout_intro_text,
    normalize_server_url, relative_time, status_view, summary_lines,
)


def _center(win, parent, w: int, h: int) -> None:
    win.update_idletasks()
    x = parent.winfo_rootx() + parent.winfo_width() // 2 - w // 2
    y = parent.winfo_rooty() + parent.winfo_height() // 2 - h // 2
    win.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")


class ConfirmDialog(ctk.CTkToplevel):
    """Modal two-button confirmation (Batal / confirm_text). `.confirmed` is set when closed."""

    def __init__(self, parent, title: str, message: str, confirm_text: str,
                 cancel_text: str = CONFIRM_CANCEL) -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.confirmed = False
        ctk.CTkLabel(self, text=message, font=("Segoe UI", 12), wraplength=400,
                     justify="left", anchor="w").pack(fill="x", padx=20, pady=(18, 8))
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=(4, 16))
        ctk.CTkButton(btns, text=confirm_text, width=110, fg_color="#b91c1c", hover_color="#991b1b",
                      command=self._yes).pack(side="right")
        ctk.CTkButton(btns, text=cancel_text, width=80, fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self.destroy).pack(side="right", padx=(0, 8))
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _: self.destroy())
        _center(self, parent, 440, 190 + 16 * message.count("\n"))
        self.grab_set()
        self.focus_set()

    def _yes(self) -> None:
        self.confirmed = True
        self.destroy()


def ask_confirm(parent, title: str, message: str, confirm_text: str) -> bool:
    dlg = ConfirmDialog(parent, title, message, confirm_text)
    parent.wait_window(dlg)
    return dlg.confirmed


class LoginDialog(ctk.CTkToplevel):
    """Username / password (+ collapsible Server URL). Login runs in a background thread."""

    def __init__(
        self,
        parent,
        controller: SyncUiController,
        default_url: str,
        current_url: str,
        username: str = "",
        notice: str = "",
        on_success=None,
        has_unsaved_edit=None,
    ) -> None:
        super().__init__(parent)
        self.title("Login Cloud Sync — KangPaket")
        self.resizable(False, False)
        self.grab_set()
        self.focus_set()

        self._ctl = controller
        self._default_url = default_url
        self._on_success = on_success
        self._has_unsaved_edit = has_unsaved_edit or (lambda: False)
        self._busy = False
        self._advanced_open = False

        self._user_var = ctk.StringVar(value=username)
        self._pass_var = ctk.StringVar()
        self._url_var = ctk.StringVar(value=current_url or default_url)

        self._build(notice)
        _center(self, parent, 420, 360)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Return>", lambda _: self._submit())
        self.bind("<Escape>", lambda _: self._cancel())
        (self._pass_entry if username else self._user_entry).focus_set()

    def _build(self, notice: str) -> None:
        pad = {"padx": 20, "pady": (4, 0)}
        ctk.CTkLabel(self, text="Login Cloud Sync", font=("Segoe UI", 15, "bold")).pack(
            anchor="w", padx=20, pady=(16, 0))
        ctk.CTkLabel(
            self, text="Sinkronkan profile dan environment antar perangkat.",
            font=("Segoe UI", 11), text_color="#94a3b8", anchor="w",
        ).pack(fill="x", padx=20, pady=(0, 6))
        if notice:
            ctk.CTkLabel(
                self, text=notice, font=("Segoe UI", 11), text_color=LEVEL_COLORS["warn"],
                wraplength=380, justify="left", anchor="w",
            ).pack(fill="x", padx=20, pady=(0, 4))

        ctk.CTkLabel(self, text="Username:", font=("Segoe UI", 12), anchor="w").pack(fill="x", **pad)
        self._user_entry = ctk.CTkEntry(self, textvariable=self._user_var, height=30)
        self._user_entry.pack(fill="x", padx=20, pady=(2, 4))

        ctk.CTkLabel(self, text="Password:", font=("Segoe UI", 12), anchor="w").pack(fill="x", **pad)
        self._pass_entry = ctk.CTkEntry(self, textvariable=self._pass_var, show="•", height=30)
        self._pass_entry.pack(fill="x", padx=20, pady=(2, 4))

        self._adv_btn = ctk.CTkButton(
            self, text="▸ Lanjutan", width=90, height=22, fg_color="transparent",
            text_color=("gray30", "gray70"), hover_color=("gray85", "gray25"),
            font=("Segoe UI", 11), anchor="w", command=self._toggle_advanced,
        )
        self._adv_btn.pack(anchor="w", padx=16, pady=(2, 0))
        self._adv_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(self._adv_frame, text="Server URL:", font=("Segoe UI", 12), anchor="w").pack(fill="x")
        row = ctk.CTkFrame(self._adv_frame, fg_color="transparent")
        row.pack(fill="x", pady=(2, 0))
        ctk.CTkEntry(row, textvariable=self._url_var, height=28).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="Reset", width=54, height=28, command=self._reset_url).pack(
            side="left", padx=(6, 0))

        self._msg = ctk.CTkLabel(
            self, text="", font=("Segoe UI", 11), text_color=LEVEL_COLORS[LEVEL_ERROR],
            wraplength=380, justify="left", anchor="w",
        )
        self._msg.pack(fill="x", padx=20, pady=(6, 0))

        self._progress = ctk.CTkProgressBar(self, mode="indeterminate", height=6)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(side="bottom", fill="x", padx=20, pady=14)
        self._login_btn = ctk.CTkButton(btns, text="Login", width=90, command=self._submit)
        self._login_btn.pack(side="right")
        ctk.CTkButton(
            btns, text="Batal", width=80, fg_color="transparent", border_width=1,
            text_color=("gray10", "gray90"), command=self._cancel,
        ).pack(side="right", padx=(0, 8))

    # ------------------------------------------------------------------
    def _toggle_advanced(self) -> None:
        self._advanced_open = not self._advanced_open
        if self._advanced_open:
            self._adv_frame.pack(fill="x", padx=20, pady=(2, 0), after=self._adv_btn)
            self._adv_btn.configure(text="▾ Lanjutan")
        else:
            self._adv_frame.pack_forget()
            self._adv_btn.configure(text="▸ Lanjutan")

    def _reset_url(self) -> None:
        self._url_var.set(self._default_url)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._login_btn.configure(state="disabled" if busy else "normal",
                                  text="Memproses…" if busy else "Login")
        if busy:
            self._progress.pack(fill="x", padx=20, pady=(6, 0))
            self._progress.start()
        else:
            self._progress.stop()
            self._progress.pack_forget()

    def _show_error(self, text: str) -> None:
        self._msg.configure(text=text)

    def _submit(self) -> None:
        if self._busy:
            return
        username = self._user_var.get().strip()
        password = self._pass_var.get()
        if not username or not password:
            self._show_error("Username dan password wajib diisi.")
            return
        try:
            url = normalize_server_url(self._url_var.get())
        except ValueError as e:
            if not self._advanced_open:
                self._toggle_advanced()
            self._show_error(str(e))
            return
        self._show_error("")
        self._set_busy(True)
        started = self._ctl.login_async(
            username, password, url, self._login_done, on_switch_required=self._switch_required)
        if not started:
            self._set_busy(False)
            self._show_error("Login sedang berjalan, tunggu sebentar.")

    def _switch_required(self, old_account: str, new_account: str) -> None:
        """Login is valid but the device holds another account's data: nothing stored yet."""
        try:
            if not self.winfo_exists():
                self._ctl.cancel_switch_async(lambda ok, msg: None)
                return
        except Exception:
            self._ctl.cancel_switch_async(lambda ok, msg: None)
            return
        if ask_confirm(self, "Ganti akun Cloud Sync",
                       account_switch_text(old_account, new_account, self._has_unsaved_edit()),
                       SWITCH_CONFIRM_YES):
            self._show_error("")
            self._ctl.confirm_switch_async(self._login_done)
        else:
            self._ctl.cancel_switch_async(self._login_done)

    def _login_done(self, ok: bool, message: str) -> None:
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        self._pass_var.set("")
        if ok:
            self.grab_release()
            self.destroy()
            if self._on_success:
                self._on_success()
            return
        self._set_busy(False)
        self._show_error(message)
        self._pass_entry.focus_set()

    def _cancel(self) -> None:
        if self._busy:
            return   # let the in-flight login finish; the result is handled above
        self._pass_var.set("")
        self.destroy()


class AccountDialog(ctk.CTkToplevel):
    """Account panel shown when logged in (or when the session expired)."""

    def __init__(self, parent, controller: SyncUiController, on_relogin, on_logged_out,
                 has_unsaved_edit=None) -> None:
        super().__init__(parent)
        self.title("Akun Cloud Sync — KangPaket")
        self.resizable(False, False)
        self.grab_set()
        self.focus_set()

        self._ctl = controller
        self._on_relogin = on_relogin
        self._on_logged_out = on_logged_out
        self._has_unsaved_edit = has_unsaved_edit or (lambda: False)
        self._manual_busy = False
        self._last_manual_error = ""
        self._received_at = time.monotonic()

        self._build()
        self.update_status()
        _center(self, parent, 460, 470)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _: self.destroy())

    def _row(self, label: str) -> ctk.CTkLabel:
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=2)
        ctk.CTkLabel(row, text=label, font=("Segoe UI", 11), width=100, anchor="w",
                     text_color="#64748b").pack(side="left")
        value = ctk.CTkLabel(row, text="", font=("Segoe UI", 12), anchor="w",
                             wraplength=320, justify="left")
        value.pack(side="left", fill="x", expand=True)
        return value

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Akun Cloud Sync", font=("Segoe UI", 15, "bold")).pack(
            anchor="w", padx=20, pady=(16, 8))
        self._user_lbl = self._row("Username")
        self._url_lbl = self._row("Server")
        self._status_lbl = self._row("Status")
        self._last_lbl = self._row("Sync terakhir")

        self._banner = ctk.CTkLabel(
            self, text="Sesi berakhir. Login ulang untuk melanjutkan sinkronisasi.",
            font=("Segoe UI", 11), text_color=LEVEL_COLORS["warn"], wraplength=420,
            justify="left", anchor="w",
        )

        ctk.CTkLabel(self, text="Ringkasan sync terakhir", font=("Segoe UI", 12, "bold"),
                     anchor="w").pack(fill="x", padx=20, pady=(12, 2))
        self._summary = ctk.CTkTextbox(self, height=130, font=("Segoe UI", 11), wrap="word")
        self._summary.pack(fill="x", padx=20)
        self._summary.configure(state="disabled")

        self._action_msg = ctk.CTkLabel(
            self, text="", font=("Segoe UI", 11), anchor="w", wraplength=420, justify="left")
        self._action_msg.pack(fill="x", padx=20, pady=(6, 0))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(side="bottom", fill="x", padx=20, pady=14)
        self._sync_btn = ctk.CTkButton(btns, text="Sync Now", width=90, command=self._sync_now)
        self._sync_btn.pack(side="left")
        self._relogin_btn = ctk.CTkButton(btns, text="Login Ulang", width=100, command=self._relogin)
        ctk.CTkButton(btns, text="Tutup", width=70, fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self.destroy).pack(side="right")
        ctk.CTkButton(btns, text="Logout", width=80, fg_color="#b91c1c", hover_color="#991b1b",
                      command=self._logout).pack(side="right", padx=(0, 8))

    # ------------------------------------------------------------------
    def note_status_received(self) -> None:
        self._received_at = time.monotonic()

    def update_status(self) -> None:
        """Refresh the labels from the manager's current status (UI thread only)."""
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        mgr = self._ctl.manager
        st = mgr.status
        now_ms = int(time.time() * 1000)
        view = status_view(st, now_ms, time.monotonic() - self._received_at)
        self._user_lbl.configure(text=mgr.state.username or "-")
        self._url_lbl.configure(text=mgr.state.server_url or mgr.client.base_url)
        self._status_lbl.configure(text=view.text, text_color=LEVEL_COLORS[view.level])
        last = st.last_sync_at
        self._last_lbl.configure(text=relative_time(last, now_ms) if last else "belum pernah")

        if st.phase == SyncPhase.AUTH_REQUIRED:
            self._banner.pack(fill="x", padx=20, pady=(8, 0), after=self._last_lbl.master)
            self._relogin_btn.pack(side="left", padx=(8, 0))
            self._sync_btn.configure(state="disabled")
        else:
            self._banner.pack_forget()
            self._relogin_btn.pack_forget()
            self._sync_btn.configure(state="disabled" if self._manual_busy or st.phase == SyncPhase.SYNCING else "normal")

        lines = summary_lines(mgr.last_result)
        self._summary.configure(state="normal")
        self._summary.delete("1.0", "end")
        self._summary.insert("1.0", "\n".join(lines))
        self._summary.configure(state="disabled")

    def _sync_now(self) -> None:
        if self._manual_busy:
            return
        self._manual_busy = True
        self._action_msg.configure(text="Menyinkronkan…", text_color=LEVEL_COLORS["busy"])
        self._sync_btn.configure(state="disabled")
        started = self._ctl.sync_now_async(self._sync_done)
        if not started:
            self._manual_busy = False
            self._action_msg.configure(text="Sinkronisasi sedang berjalan.", text_color=LEVEL_COLORS["warn"])

    def _sync_done(self, result, message: str) -> None:
        self._manual_busy = False
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        if message:
            self._action_msg.configure(text=message, text_color=LEVEL_COLORS[LEVEL_ERROR])
        else:
            self._action_msg.configure(text="Sinkronisasi selesai.", text_color=LEVEL_COLORS[LEVEL_OK])
        self.update_status()

    def _relogin(self) -> None:
        self.destroy()
        self._on_relogin()

    def _logout(self) -> None:
        user = self._ctl.manager.state.username or ""
        if not ask_confirm(self, LOGOUT_TITLE, logout_intro_text(user), "Logout"):
            return
        self._start_logout(force=False)

    def _start_logout(self, force: bool) -> None:
        self._sync_btn.configure(state="disabled")
        self._action_msg.configure(
            text="Logout…" if force else "Menyinkronkan perubahan terakhir…",
            text_color=LEVEL_COLORS["busy"])
        started = self._ctl.logout_async(
            self._logout_done, unsaved_edit=self._has_unsaved_edit(), force=force)
        if not started:
            self._action_msg.configure(text="Logout sedang berjalan.", text_color=LEVEL_COLORS["warn"])

    def _logout_done(self, outcome) -> None:
        try:
            if not self.winfo_exists():
                if outcome.done:
                    self._on_logged_out()
                return
        except Exception:
            return
        if outcome.done:
            self.destroy()
            self._on_logged_out()
            return
        if outcome.blockers.needs_confirm:
            if ask_confirm(self, LOGOUT_TITLE, logout_blockers_text(outcome.blockers), LOGOUT_CONFIRM_YES):
                self._start_logout(force=True)
                return
            self._action_msg.configure(
                text="Logout dibatalkan. Data lokal tidak diubah.", text_color=LEVEL_COLORS["warn"])
        else:
            self._action_msg.configure(text=outcome.error or "Logout gagal.",
                                       text_color=LEVEL_COLORS[LEVEL_ERROR])
        self.update_status()
