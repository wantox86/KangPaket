"""
KangPaket — Collection Runner Window (CTkToplevel).
Configuration panel | Progress | Live results list.
"""
from __future__ import annotations

import csv
import json
import os
import time
import tkinter.filedialog as fd
import customtkinter as ctk
from datetime import datetime, timezone

from app.core.http_client import HttpClient
from app.core.profile_manager import ProfileManager
from app.core.runner_engine import RunnerEngine
from app.core.settings_manager import SettingsManager
from app.models.request_model import RequestProfile
from app.models.runner_model import RunnerConfig, RunItemResult, RunnerResult
from app.ui.widgets.runner_result_row import RunnerResultRow
from app.config import METHOD_COLORS, RESULTS_DIR


class RunnerWindow(ctk.CTkToplevel):
    def __init__(
        self,
        parent,
        profile_manager: ProfileManager,
        settings: SettingsManager,
        on_open_profile: callable | None = None,
        preselect_collection: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("Collection Runner — KangPaket")
        self.geometry("900x720")
        self.minsize(760, 560)
        self.grab_set()
        self.focus_set()

        self._pm              = profile_manager
        self._settings        = settings
        self._on_open_profile = on_open_profile
        self._engine          = RunnerEngine(HttpClient(), settings, tk_root=self)
        self._runner_result: RunnerResult | None = None
        self._running         = False
        self._start_time: float = 0.0
        self._elapsed_job: str | None = None

        # Ordered checklist items: list of (profile, BooleanVar)
        self._checklist: list[tuple[RequestProfile, ctk.BooleanVar]] = []

        self._build()

        if preselect_collection:
            self._collection_var.set(preselect_collection)
            self._on_collection_change(preselect_collection)

    # ------------------------------------------------------------------
    # Build layout
    # ------------------------------------------------------------------

    def _build(self) -> None:
        # Config panel — fixed height, packs to the top
        config_frame = ctk.CTkFrame(self, corner_radius=0)
        config_frame.pack(fill="x", side="top")

        # Results area — fills all remaining vertical space
        results_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        results_frame.pack(fill="both", expand=True, side="top")

        self._build_config(config_frame)
        self._build_progress(results_frame)
        self._build_results(results_frame)

    # ---- Config panel ----

    def _build_config(self, parent: ctk.CTkFrame) -> None:
        ctk.CTkLabel(
            parent, text="RUNNER CONFIGURATION",
            font=("Segoe UI", 11, "bold"), text_color="#64748b", anchor="w",
        ).pack(fill="x", padx=12, pady=(8, 4))
        ctk.CTkFrame(parent, height=1, fg_color="#333").pack(fill="x", padx=12, pady=(0, 6))

        # Run Name
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(row, text="Run Name:", width=110, anchor="w", font=("Segoe UI", 12)).pack(side="left")
        self._run_name_var = ctk.StringVar(
            value=f"Run - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        ctk.CTkEntry(row, textvariable=self._run_name_var, font=("Segoe UI", 12), height=28).pack(
            side="left", fill="x", expand=True
        )

        # Collection dropdown
        row2 = ctk.CTkFrame(parent, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(row2, text="Collection:", width=110, anchor="w", font=("Segoe UI", 12)).pack(side="left")

        collections = self._pm.get_collections() or ["Default"]
        self._collection_var = ctk.StringVar(value=collections[0])
        self._col_menu = ctk.CTkOptionMenu(
            row2,
            variable=self._collection_var,
            values=collections,
            width=200, height=28,
            font=("Segoe UI", 12),
            command=self._on_collection_change,
        )
        self._col_menu.pack(side="left")

        ctk.CTkButton(
            row2, text="↺", width=28, height=28,
            font=("Segoe UI", 13),
            fg_color="#374151", hover_color="#4b5563",
            command=self._refresh_collections,
        ).pack(side="left", padx=4)

        # ── Data File (CSV variables) ────────────────────────────────────
        csv_row = ctk.CTkFrame(parent, fg_color="transparent")
        csv_row.pack(fill="x", padx=12, pady=(4, 0))

        ctk.CTkLabel(csv_row, text="Data File:", width=110, anchor="w",
                     font=("Segoe UI", 12)).pack(side="left")

        self._csv_path_var = ctk.StringVar()
        ctk.CTkEntry(
            csv_row, textvariable=self._csv_path_var,
            placeholder_text="No CSV file loaded",
            font=("Segoe UI", 11), height=26, state="readonly",
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))

        ctk.CTkButton(
            csv_row, text="Browse…", width=72, height=26,
            font=("Segoe UI", 11), fg_color="#374151", hover_color="#4b5563",
            command=self._browse_csv,
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            csv_row, text="✕", width=26, height=26,
            font=("Segoe UI", 11), fg_color="#374151", hover_color="#7f1d1d",
            command=self._clear_csv,
        ).pack(side="left")

        # Info label: shows detected variables + row count
        self._csv_info_label = ctk.CTkLabel(
            parent,
            text="Use a CSV file to drive {{variable}} substitution per row.",
            font=("Segoe UI", 10), text_color="#64748b", anchor="w",
        )
        self._csv_info_label.pack(fill="x", padx=12, pady=(1, 4))

        # Internal CSV state
        self._csv_data: list[dict[str, str]] | None = None

        # Checklist header
        chk_hdr = ctk.CTkFrame(parent, fg_color="transparent")
        chk_hdr.pack(fill="x", padx=12, pady=(6, 2))
        ctk.CTkLabel(chk_hdr, text="Requests:", width=110, anchor="w", font=("Segoe UI", 12)).pack(side="left")
        ctk.CTkButton(
            chk_hdr, text="All", width=40, height=22,
            font=("Segoe UI", 10), fg_color="#374151", hover_color="#4b5563",
            command=lambda: self._select_all(True),
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            chk_hdr, text="None", width=48, height=22,
            font=("Segoe UI", 10), fg_color="#374151", hover_color="#4b5563",
            command=lambda: self._select_all(False),
        ).pack(side="left")

        # Scrollable checklist — fixed height so items below are always visible
        self._checklist_scroll = ctk.CTkScrollableFrame(
            parent, corner_radius=0, fg_color="transparent", height=110,
        )
        self._checklist_scroll.pack(fill="x", padx=12, pady=(0, 4))

        self._populate_checklist(self._collection_var.get())

        ctk.CTkFrame(parent, height=1, fg_color="#333").pack(fill="x", padx=12, pady=(2, 0))

        # Options row: Iterations | Delay | Mode | Stop on failure
        opts = ctk.CTkFrame(parent, fg_color="transparent")
        opts.pack(fill="x", padx=12, pady=(4, 2))

        ctk.CTkLabel(opts, text="Iterations:", font=("Segoe UI", 12)).pack(side="left")
        self._iter_var = ctk.StringVar(value="1")
        self._iter_entry = ctk.CTkEntry(opts, textvariable=self._iter_var, width=48, height=26, font=("Courier New", 12))
        self._iter_entry.pack(side="left", padx=(4, 12))

        ctk.CTkLabel(opts, text="Delay (ms):", font=("Segoe UI", 12)).pack(side="left")
        self._delay_var = ctk.StringVar(value="100")
        ctk.CTkEntry(opts, textvariable=self._delay_var, width=56, height=26, font=("Courier New", 12)).pack(
            side="left", padx=(4, 12)
        )

        ctk.CTkLabel(opts, text="Mode:", font=("Segoe UI", 12)).pack(side="left")
        self._mode_var = ctk.StringVar(value="sequential")
        ctk.CTkRadioButton(opts, text="Sequential", variable=self._mode_var, value="sequential").pack(
            side="left", padx=(4, 8)
        )
        ctk.CTkRadioButton(opts, text="Parallel", variable=self._mode_var, value="parallel").pack(
            side="left", padx=(0, 12)
        )

        self._stop_on_fail_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(opts, text="Stop on failure", variable=self._stop_on_fail_var).pack(side="left")

        # Action buttons row
        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(4, 10))

        self._run_btn = ctk.CTkButton(
            btn_row, text="▶  RUN", width=100, height=34,
            font=("Segoe UI", 13, "bold"),
            fg_color="#16a34a", hover_color="#15803d",
            command=self._start_run,
        )
        self._run_btn.pack(side="left", padx=(0, 8))

        self._stop_btn = ctk.CTkButton(
            btn_row, text="■  STOP", width=90, height=34,
            font=("Segoe UI", 12, "bold"),
            fg_color="#dc2626", hover_color="#b91c1c",
            command=self._stop_run,
            state="disabled",
        )
        self._stop_btn.pack(side="left", padx=(0, 8))

        self._export_btn = ctk.CTkButton(
            btn_row, text="Export Results", width=120, height=34,
            font=("Segoe UI", 12),
            fg_color="#374151", hover_color="#4b5563",
            command=self._export_results,
            state="disabled",
        )
        self._export_btn.pack(side="left")

    # ---- Progress panel ----

    def _build_progress(self, parent: ctk.CTkFrame) -> None:
        self._progress_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="#111118")
        self._progress_frame.pack(fill="x")

        ctk.CTkLabel(
            self._progress_frame, text="PROGRESS",
            font=("Segoe UI", 10, "bold"), text_color="#64748b", anchor="w",
        ).pack(fill="x", padx=12, pady=(6, 2))

        self._progress_bar = ctk.CTkProgressBar(self._progress_frame, height=10)
        self._progress_bar.pack(fill="x", padx=12, pady=(0, 4))
        self._progress_bar.set(0)

        summary_row = ctk.CTkFrame(self._progress_frame, fg_color="transparent")
        summary_row.pack(fill="x", padx=12, pady=(0, 4))

        self._prog_label   = ctk.CTkLabel(summary_row, text="0 / 0", font=("Segoe UI", 11), text_color="#94a3b8")
        self._elapsed_label = ctk.CTkLabel(summary_row, text="", font=("Segoe UI", 11), text_color="#64748b")
        self._passed_label = ctk.CTkLabel(summary_row, text="✅ 0", font=("Segoe UI", 11), text_color="#49cc90")
        self._failed_label = ctk.CTkLabel(summary_row, text="❌ 0", font=("Segoe UI", 11), text_color="#f93e3e")
        self._error_label  = ctk.CTkLabel(summary_row, text="⚠ 0",  font=("Segoe UI", 11), text_color="#fca130")
        self._skip_label   = ctk.CTkLabel(summary_row, text="⏭ 0",  font=("Segoe UI", 11), text_color="#64748b")

        for lbl in [self._prog_label, self._passed_label, self._failed_label,
                    self._error_label, self._skip_label, self._elapsed_label]:
            lbl.pack(side="left", padx=8)

    # ---- Results panel ----

    def _build_results(self, parent: ctk.CTkFrame) -> None:
        ctk.CTkLabel(
            parent, text="RESULTS",
            font=("Segoe UI", 10, "bold"), text_color="#64748b", anchor="w",
        ).pack(fill="x", padx=12, pady=(4, 2))

        self._results_scroll = ctk.CTkScrollableFrame(
            parent, corner_radius=0, fg_color="transparent"
        )
        self._results_scroll.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        self._result_rows: list[RunnerResultRow] = []

    # ------------------------------------------------------------------
    # Checklist helpers
    # ------------------------------------------------------------------

    def _on_collection_change(self, value: str) -> None:
        self._populate_checklist(value)

    def _populate_checklist(self, collection: str) -> None:
        for widget in self._checklist_scroll.winfo_children():
            widget.destroy()
        self._checklist.clear()

        grouped = self._pm.get_profiles_by_collection()
        profiles = grouped.get(collection, [])

        if not profiles:
            ctk.CTkLabel(
                self._checklist_scroll,
                text="No requests in this collection.",
                font=("Segoe UI", 11), text_color="#888",
            ).pack(pady=8)
            return

        for profile in profiles:
            var = ctk.BooleanVar(value=True)
            row = ctk.CTkFrame(self._checklist_scroll, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkCheckBox(row, text="", variable=var, width=24,
                            checkbox_width=16, checkbox_height=16).pack(side="left")
            mc = METHOD_COLORS.get(profile.method, "#61affe")
            ctk.CTkLabel(row, text=profile.method[:4], font=("Segoe UI", 9, "bold"),
                         text_color=mc, width=34).pack(side="left")
            ctk.CTkLabel(row, text=profile.name, font=("Segoe UI", 11),
                         anchor="w").pack(side="left", fill="x", expand=True)
            url_short = profile.url[:50] + ("…" if len(profile.url) > 50 else "")
            ctk.CTkLabel(row, text=url_short, font=("Segoe UI", 9),
                         text_color="#64748b", anchor="w").pack(side="left", padx=4)
            self._checklist.append((profile, var))

    def _refresh_collections(self) -> None:
        cols = self._pm.get_collections() or ["Default"]
        self._col_menu.configure(values=cols)
        self._populate_checklist(self._collection_var.get())

    # ------------------------------------------------------------------
    # CSV data file
    # ------------------------------------------------------------------

    def _browse_csv(self) -> None:
        path = fd.askopenfilename(
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Select CSV Data File",
            parent=self,
        )
        if not path:
            return
        try:
            self._load_csv(path)
        except Exception as e:
            import tkinter.messagebox as mb
            mb.showerror("CSV Error", f"Failed to load CSV file:\n{e}", parent=self)

    def _load_csv(self, path: str) -> None:
        import csv as _csv
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = _csv.DictReader(f)
            rows = [dict(row) for row in reader]

        if not rows:
            raise ValueError("CSV file is empty or has no data rows.")

        self._csv_data = rows
        cols = list(rows[0].keys())

        # Build variable preview: show up to 5 column names as {{name}}
        preview_cols = cols[:5]
        vars_preview = "  ".join(f"{{{{{c}}}}}" for c in preview_cols)
        if len(cols) > 5:
            vars_preview += f"  … (+{len(cols) - 5} more)"

        filename = os.path.basename(path)
        self._csv_path_var.set(filename)
        self._csv_info_label.configure(
            text=(
                f"✓  {len(rows)} row(s)  •  "
                f"{len(cols)} variable(s): {vars_preview}  "
                f"[iterations will be set to {len(rows)}]"
            ),
            text_color="#49cc90",
        )
        self._iter_var.set(str(len(rows)))
        self._iter_entry.configure(state="disabled")

    def _clear_csv(self) -> None:
        self._csv_data = None
        self._csv_path_var.set("")
        self._csv_info_label.configure(
            text="Use a CSV file to drive {{variable}} substitution per row.",
            text_color="#64748b",
        )
        self._iter_var.set("1")
        self._iter_entry.configure(state="normal")

    def _select_all(self, value: bool) -> None:
        for _, var in self._checklist:
            var.set(value)

    # ------------------------------------------------------------------
    # Run / Stop
    # ------------------------------------------------------------------

    def _start_run(self) -> None:
        selected = [(p, v) for p, v in self._checklist if v.get()]
        if not selected:
            import tkinter.messagebox as mb
            mb.showwarning("Runner", "Select at least 1 request to run.", parent=self)
            return

        # Parse options
        try:
            iters = max(1, int(self._iter_var.get()))
        except ValueError:
            iters = 1
        try:
            delay = max(0, int(self._delay_var.get()))
        except ValueError:
            delay = 0

        # CSV overrides iteration count
        csv_data = self._csv_data
        if csv_data:
            iters = len(csv_data)

        config = RunnerConfig(
            name=self._run_name_var.get().strip(),
            profile_ids=[p.id for p, _ in selected],
            iteration_count=iters,
            delay_between_ms=delay,
            stop_on_failure=self._stop_on_fail_var.get(),
            run_mode=self._mode_var.get(),
        )

        # Clear previous results
        for widget in self._results_scroll.winfo_children():
            widget.destroy()
        self.update_idletasks()
        self._result_rows.clear()
        self._runner_result = None

        # Update counters
        total = len(selected) * iters
        self._progress_bar.set(0)
        self._prog_label.configure(text=f"0 / {total}")
        self._passed_label.configure(text="✅ 0")
        self._failed_label.configure(text="❌ 0")
        self._error_label.configure(text="⚠ 0")
        self._skip_label.configure(text="⏭ 0")
        self._elapsed_label.configure(text="")

        self._run_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._export_btn.configure(state="disabled")
        self._running = True
        self._start_time = time.monotonic()
        self._tick_elapsed()

        profiles = [p for p, _ in selected]
        self._engine.run(
            config=config,
            profiles=profiles,
            on_item_done=self._on_item_done,
            on_progress=self._on_progress,
            on_finished=self._on_finished,
            csv_data=csv_data,
        )

    def _stop_run(self) -> None:
        self._engine.stop()
        self._stop_btn.configure(state="disabled")

    # ------------------------------------------------------------------
    # Callbacks (called on main thread via root.after)
    # ------------------------------------------------------------------

    def _on_item_done(self, item: RunItemResult) -> None:
        index = len(self._result_rows) + 1
        row = RunnerResultRow(
            self._results_scroll,
            item=item,
            index=index,
            on_open_main=self._on_open_main,
        )
        row.pack(fill="x", pady=2)
        self._result_rows.append(row)
        # Scroll to bottom
        self._results_scroll._parent_canvas.yview_moveto(1.0)

    def _on_progress(self, done: int, total: int) -> None:
        pct = done / total if total > 0 else 0
        self._progress_bar.set(pct)
        self._prog_label.configure(text=f"{done} / {total}")

        passed  = sum(1 for r in self._result_rows if r._item.status == "success")
        failed  = sum(1 for r in self._result_rows if r._item.status == "failed")
        errors  = sum(1 for r in self._result_rows if r._item.status == "error")
        skipped = sum(1 for r in self._result_rows if r._item.status == "skipped")
        self._passed_label.configure(text=f"✅ {passed}")
        self._failed_label.configure(text=f"❌ {failed}")
        self._error_label.configure(text=f"⚠ {errors}")
        self._skip_label.configure(text=f"⏭ {skipped}")

    def _on_finished(self, result: RunnerResult) -> None:
        self._runner_result = result
        self._running = False
        self._run_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self._export_btn.configure(state="normal")
        if self._elapsed_job:
            self.after_cancel(self._elapsed_job)
        elapsed_s = result.total_elapsed_ms / 1000
        self._elapsed_label.configure(text=f"  {elapsed_s:.1f}s total")

    def _tick_elapsed(self) -> None:
        if not self._running:
            return
        elapsed = time.monotonic() - self._start_time
        self._elapsed_label.configure(text=f"  {elapsed:.1f}s")
        self._elapsed_job = self.after(1000, self._tick_elapsed)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _export_results(self) -> None:
        if self._runner_result is None:
            return

        path = fd.asksaveasfilename(
            defaultextension=".json",
            filetypes=[
                ("JSON files", "*.json"),
                ("CSV files", "*.csv"),
            ],
            title="Export Runner Results",
        )
        if not path:
            return

        try:
            if path.endswith(".csv"):
                self._export_csv(path)
            else:
                self._export_json(path)
        except OSError as e:
            import tkinter.messagebox as mb
            mb.showerror("Export Failed", str(e), parent=self)

    def _export_json(self, path: str) -> None:
        r = self._runner_result
        payload = {
            "run_name":        r.config.name,
            "run_mode":        r.config.run_mode,
            "finished_at":     r.finished_at,
            "total":           r.total,
            "passed":          r.passed,
            "failed":          r.failed,
            "errors":          r.errors,
            "skipped":         r.skipped,
            "total_elapsed_ms": r.total_elapsed_ms,
            "items": [
                {
                    "index":          i + 1,
                    "profile_name":   item.profile_name,
                    "profile_id":     item.profile_id,
                    "iteration":      item.iteration,
                    "status":         item.status,
                    "status_code":    item.status_code,
                    "elapsed_ms":     item.elapsed_ms,
                    "size_bytes":     item.size_bytes,
                    "error":          item.error,
                    "assertions":     item.assertion_results,
                    "timestamp":      item.timestamp,
                }
                for i, item in enumerate(r.items)
            ],
        }
        os.makedirs(RESULTS_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def _export_csv(self, path: str) -> None:
        r = self._runner_result
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "#", "Profile Name", "Iteration", "Status",
                "Status Code", "Elapsed (ms)", "Size (bytes)", "Error", "Timestamp"
            ])
            for i, item in enumerate(r.items):
                writer.writerow([
                    i + 1,
                    item.profile_name,
                    item.iteration,
                    item.status,
                    item.status_code or "",
                    f"{item.elapsed_ms:.0f}" if item.elapsed_ms else "",
                    item.size_bytes or "",
                    item.error or "",
                    item.timestamp,
                ])

    # ------------------------------------------------------------------
    # Open in Main Window
    # ------------------------------------------------------------------

    def _on_open_main(self, profile_id: str) -> None:
        if self._on_open_profile:
            profile = self._pm.get_profile(profile_id)
            if profile:
                self._on_open_profile(profile)
