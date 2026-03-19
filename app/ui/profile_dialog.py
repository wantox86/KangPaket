"""
KangPaket — Profile save/rename dialog.
Modal CTkToplevel: input nama profil + pilih/ketik collection.
"""
from __future__ import annotations

import customtkinter as ctk


class ProfileDialog(ctk.CTkToplevel):
    """
    Modal dialog untuk save atau rename profil.

    Setelah ditutup, cek result:
        dialog.confirmed  -> bool
        dialog.name       -> str
        dialog.collection -> str
    """

    def __init__(
        self,
        parent,
        title: str = "Save Profile",
        initial_name: str = "",
        initial_collection: str = "Default",
        collections: list[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.grab_set()            # modal
        self.focus_set()

        self.confirmed  = False
        self.name       = initial_name
        self.collection = initial_collection

        self._collections = collections or ["Default"]

        self._build(initial_name, initial_collection)

        # Center relative to parent
        self.update_idletasks()
        px = parent.winfo_rootx() + parent.winfo_width() // 2 - 220
        py = parent.winfo_rooty() + parent.winfo_height() // 2 - 130
        self.geometry(f"440x260+{px}+{py}")

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Return>", lambda _: self._confirm())
        self.bind("<Escape>", lambda _: self._cancel())

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self, initial_name: str, initial_collection: str) -> None:
        pad = {"padx": 20, "pady": 6}

        ctk.CTkLabel(
            self, text="Request Name:", font=("Segoe UI", 12), anchor="w"
        ).pack(fill="x", **pad)

        self._name_var = ctk.StringVar(value=initial_name)
        self._name_entry = ctk.CTkEntry(
            self,
            textvariable=self._name_var,
            placeholder_text="e.g. Login API",
            font=("Segoe UI", 13),
            height=34,
        )
        self._name_entry.pack(fill="x", padx=20, pady=(0, 6))
        self._name_entry.focus()
        # select all text if pre-filled
        if initial_name:
            self._name_entry.select_range(0, "end")

        ctk.CTkLabel(
            self, text="Collection:", font=("Segoe UI", 12), anchor="w"
        ).pack(fill="x", **pad)

        self._collection_var = ctk.StringVar(value=initial_collection)

        # ComboBox-like: OptionMenu + manual entry below
        col_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        col_frame.pack(fill="x", padx=20, pady=(0, 6))

        # Dropdown existing collections
        all_cols = sorted(set(self._collections + [initial_collection]))
        self._col_menu = ctk.CTkOptionMenu(
            col_frame,
            variable=self._collection_var,
            values=all_cols,
            width=200,
            height=32,
            font=("Segoe UI", 12),
            command=self._on_collection_select,
        )
        self._col_menu.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            col_frame, text="or type new:", font=("Segoe UI", 11), text_color="#888"
        ).pack(side="left", padx=(0, 6))

        self._new_col_var = ctk.StringVar()
        ctk.CTkEntry(
            col_frame,
            textvariable=self._new_col_var,
            placeholder_text="New collection name",
            font=("Segoe UI", 12),
            height=32,
        ).pack(side="left", fill="x", expand=True)

        # Validation message
        self._msg_label = ctk.CTkLabel(
            self, text="", font=("Segoe UI", 11), text_color="#f93e3e"
        )
        self._msg_label.pack(fill="x", padx=20)

        # Buttons
        btn_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(8, 16))

        ctk.CTkButton(
            btn_frame, text="Cancel", width=100, height=34,
            fg_color="#374151", hover_color="#4b5563",
            command=self._cancel,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            btn_frame, text="Save", width=100, height=34,
            fg_color="#2563eb", hover_color="#1d4ed8",
            command=self._confirm,
        ).pack(side="right")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_collection_select(self, value: str) -> None:
        self._collection_var.set(value)

    def _confirm(self) -> None:
        name = self._name_var.get().strip()
        if not name:
            self._msg_label.configure(text="Name cannot be empty.")
            self._name_entry.focus()
            return

        # Prefer manually typed collection over dropdown
        new_col = self._new_col_var.get().strip()
        collection = new_col if new_col else self._collection_var.get().strip()
        if not collection:
            collection = "Default"

        self.confirmed  = True
        self.name       = name
        self.collection = collection
        self.destroy()

    def _cancel(self) -> None:
        self.confirmed = False
        self.destroy()
