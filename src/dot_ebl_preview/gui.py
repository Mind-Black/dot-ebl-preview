"""Tkinter desktop GUI for inspecting designs, previewing diffraction and saving GDS."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Empty, Queue
from time import perf_counter
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

import numpy as np
from PIL import Image, ImageTk

from dot_ebl_preview.core.model import Design
from dot_ebl_preview.gui_logic import (
    INPUT_FORMATS, SceneSettings, apply_parameter_edit, direction_from_position,
    encode_gui_design_image, export_gui_bundle, load_gui_design, parameter_counts,
    parameter_map, position_from_direction, render_scene, render_scene_gpu, save_gds,
    save_gui_design_image,
)
from dot_ebl_preview.io.images import load_image_rgb
from dot_ebl_preview.preview.realtime import RealtimeViewer


class DesignWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Dot EBL Preview")
        self.root.geometry("1500x920")
        self.root.minsize(1050, 700)
        self.design: Design | None = None
        self.preview_image: Image.Image | None = None
        self.panel_images: dict[str, Image.Image | None] = {
            "source": None, "periods": None, "angles": None, "preview": None,
        }
        self.panel_canvases: dict[str, tk.Canvas] = {}
        self.panel_photos: dict[str, ImageTk.PhotoImage] = {}
        self.panel_captions: dict[str, tk.StringVar] = {}
        self._preview_drag: tuple[int, float, float] | None = None
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dot-ebl-gui")
        self.results: Queue[tuple[Callable, object, BaseException | None, bool]] = Queue()
        self.action_buttons: list[ttk.Button] = []
        self.busy = False
        self.preview_running = False
        self.preview_pending: tuple[Design, SceneSettings, str, int] | None = None
        self.scene_revision = 0
        self.closed = False
        self.panel_canvas_image_items: dict[str, int] = {}
        self.panel_canvas_text_items: dict[str, int] = {}
        self._last_displayed_viewer: object | None = None
        self._last_displayed_serial: int = -1
        self._last_displayed_quality: int = -1
        self._last_poll_time: float = perf_counter()
        self.viewer: RealtimeViewer | None = None
        self._from_viewer = False
        self._capture_token = 0
        self._capture_actions: dict[int, tuple[str, str | None]] = {}
        self.source_raw: np.ndarray | None = None
        self.original_source_raw: np.ndarray | None = None
        self.original_design: Design | None = None
        self._inline_entry: ttk.Entry | None = None
        self._table_selected_vars: dict[str, tk.StringVar] = {}
        self._table_entry_vars: dict[str, tk.StringVar] = {}
        self._table_data: dict[str, list[tuple[float, int]]] = {"gratings": [], "angles": []}
        self.point_sliders: dict[str, list[ttk.Scale]] = {}

        self.path_var = tk.StringVar()
        self.format_var = tk.StringVar(value=INPUT_FORMATS[0])
        self.pitch_var = tk.StringVar(value="20")
        self.orientation_var = tk.StringVar(value="0")
        self.renderer_var = tk.StringVar(value="OpenGL (fast)")
        self.live_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Choose a design image or a saved .npz design.")
        self.source_vars = self._point_vars(
            ("0", "20.6487533", "29.4891314"), ("90", "55", "36"),
            extra={"size": "0.0"},
        )
        self.observer_vars = self._point_vars(
            ("0", "0", "66"), ("0", "90", "66"),
            extra={"aperture": "5.0"},
        )

        self._build_window()
        for variable in (self.orientation_var, self.renderer_var, *self.source_vars.values(),
                         *self.observer_vars.values()):
            variable.trace_add("write", self._scene_changed)
        self.root.after(16, self._poll_results)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    @staticmethod
    def _point_vars(xyz: tuple[str, str, str], direction: tuple[str, str, str],
                    extra: dict[str, str] | None = None) -> dict[str, tk.StringVar]:
        vars_dict = {
            "mode": tk.StringVar(value="XYZ"),
            **{key: tk.StringVar(value=value) for key, value in zip(("x", "y", "z"), xyz)},
            **{key: tk.StringVar(value=value) for key, value in zip(("az", "el", "distance"), direction)},
        }
        if extra:
            for key, value in extra.items():
                vars_dict[key] = tk.StringVar(value=value)
        return vars_dict

    def _button(self, parent: tk.Widget, label: str, command: Callable, **kwargs) -> ttk.Button:
        button = ttk.Button(parent, text=label, command=command, **kwargs)
        self.action_buttons.append(button)
        return button

    def _build_window(self) -> None:
        outer = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 4))

        controls = ttk.Frame(outer, width=420)
        outer.add(controls, weight=0)
        control_canvas = tk.Canvas(controls, highlightthickness=0, width=400)
        scrollbar = ttk.Scrollbar(controls, orient=tk.VERTICAL, command=control_canvas.yview)
        control_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        control_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        form = ttk.Frame(control_canvas, padding=5)
        form_id = control_canvas.create_window((0, 0), window=form, anchor="nw")
        form.bind("<Configure>", lambda _event: control_canvas.configure(scrollregion=control_canvas.bbox("all")))
        control_canvas.bind("<Configure>", lambda event: control_canvas.itemconfigure(form_id, width=event.width))

        source = ttk.LabelFrame(form, text="1  Design image", padding=8)
        source.pack(fill=tk.X, pady=(0, 8))
        path_row = ttk.Frame(source)
        path_row.pack(fill=tk.X)
        ttk.Entry(path_row, textvariable=self.path_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._button(path_row, "Browse...", self._browse).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Label(source, text="Image interpretation").pack(anchor=tk.W, pady=(7, 1))
        ttk.Combobox(source, textvariable=self.format_var, values=INPUT_FORMATS, state="readonly").pack(fill=tk.X)
        pitch_row = ttk.Frame(source)
        pitch_row.pack(fill=tk.X, pady=(7, 0))
        ttk.Label(pitch_row, text="Holopixel pitch (µm)").pack(side=tk.LEFT)
        ttk.Entry(pitch_row, textvariable=self.pitch_var, width=10).pack(side=tk.RIGHT)
        self._button(source, "Load design", self._load).pack(fill=tk.X, pady=(8, 0))

        data = ttk.LabelFrame(form, text="2  Found parameters", padding=8)
        data.pack(fill=tk.X, pady=(0, 8))
        self.summary_var = tk.StringVar(value="No parameters loaded")
        ttk.Label(data, textvariable=self.summary_var, wraplength=365).pack(anchor=tk.W)
        self.parameter_tabs = ttk.Notebook(data)
        self.parameter_tabs.pack(fill=tk.X, pady=(7, 0))
        self.period_table = self._parameter_table("Gratings (µm)", "gratings")
        self.angle_table = self._parameter_table("Angles (°)", "angles")
        scene = ttk.LabelFrame(form, text="3  Diffraction scene", padding=8)
        scene.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(scene, text="Design orientation (° CCW)").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(scene, textvariable=self.orientation_var, width=12).grid(row=0, column=1, sticky=tk.E)
        self.orientation_slider = self._linked_slider(scene, 1, self.orientation_var, -180.0, 180.0)
        scene.columnconfigure(0, weight=1)
        self._point_editor(scene, "Illumination", self.source_vars, 2,
                           extra_caption="Source radius (mm)", extra_key="size", extra_range=(0.0, 30.0))
        self._point_editor(scene, "Observation", self.observer_vars, 3,
                           extra_caption="Aperture radius (mm)", extra_key="aperture", extra_range=(0.1, 30.0))
        ttk.Label(scene, text="Drag sliders or edit values. In the OpenGL pane: left drag moves the observer; right drag moves the light; wheel changes distance (Shift+wheel for light).",
                  wraplength=355).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))
        ttk.Label(scene, text="Renderer").grid(row=5, column=0, sticky=tk.W, pady=(7, 0))
        ttk.Combobox(scene, textvariable=self.renderer_var, values=("OpenGL (fast)", "CPU reference"),
                     state="readonly", width=17).grid(row=5, column=1, sticky=tk.E, pady=(7, 0))
        ttk.Checkbutton(scene, text="Live OpenGL rendering", variable=self.live_var,
                        command=self._live_toggled).grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=(7, 0))
        self._button(scene, "Refresh preview", self._preview).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(9, 0))

        output = ttk.LabelFrame(form, text="4  Output", padding=8)
        output.pack(fill=tk.X, pady=(0, 8))
        self._button(output, "Save design image PNG...", self._save_design_image).pack(fill=tk.X)
        self._button(output, "Save GDS...", self._save_gds).pack(fill=tk.X, pady=(5, 0))
        self._button(output, "Export fabrication bundle...", self._export_bundle).pack(fill=tk.X, pady=(5, 0))
        self._button(output, "Save preview PNG...", self._save_preview).pack(fill=tk.X, pady=(5, 0))

        right = ttk.Frame(outer)
        outer.add(right, weight=1)
        for column in range(2):
            right.columnconfigure(column, weight=1, uniform="screens")
        for row in range(2):
            right.rowconfigure(row, weight=1, uniform="screens")
        for key, title, row, column in (
            ("source", "1  Original RGB design", 0, 0),
            ("periods", "2  Extracted grating periodicity", 0, 1),
            ("angles", "3  Extracted rotation angle", 1, 0),
            ("preview", "4  Real-time OpenGL diffraction", 1, 1),
        ):
            panel = ttk.LabelFrame(right, text=title, padding=5)
            panel.grid(row=row, column=column, sticky="nsew", padx=4, pady=4)
            canvas = tk.Canvas(panel, bg="#121821", highlightthickness=0, width=350, height=300)
            canvas.pack(fill=tk.BOTH, expand=True)
            caption = tk.StringVar(value="Load a design to begin." if key != "preview" else "Waiting for a design.")
            ttk.Label(panel, textvariable=caption, anchor=tk.CENTER, wraplength=360).pack(fill=tk.X, pady=(3, 0))
            self.panel_canvases[key] = canvas
            self.panel_captions[key] = caption
            canvas.bind("<Configure>", lambda _event, panel_key=key: self._draw_panel(panel_key))
        preview_canvas = self.panel_canvases["preview"]
        preview_canvas.bind("<ButtonPress-1>", lambda event: self._preview_drag_start(event, 1))
        preview_canvas.bind("<ButtonPress-3>", lambda event: self._preview_drag_start(event, 3))
        preview_canvas.bind("<B1-Motion>", lambda event: self._preview_drag_move(event, 1))
        preview_canvas.bind("<B3-Motion>", lambda event: self._preview_drag_move(event, 3))
        preview_canvas.bind("<ButtonRelease-1>", self._preview_drag_end)
        preview_canvas.bind("<ButtonRelease-3>", self._preview_drag_end)
        preview_canvas.bind("<MouseWheel>", self._preview_wheel)

        status = ttk.Frame(self.root, padding=(10, 0, 10, 8))
        status.pack(fill=tk.X)
        self.progress = ttk.Progressbar(status, mode="indeterminate", length=120)
        self.progress.pack(side=tk.RIGHT)
        ttk.Label(status, textvariable=self.status_var, wraplength=900).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _parameter_table(self, title: str, kind: str) -> ttk.Treeview:
        holder = ttk.Frame(self.parameter_tabs, padding=2)
        self.parameter_tabs.add(holder, text=title)

        hint = ttk.Label(holder, text="Double-click a value to edit inline, or edit below:",
                         font=("Segoe UI", 8), foreground="#5c6b73")
        hint.pack(anchor=tk.W, pady=(0, 2))

        table_frame = ttk.Frame(holder)
        table_frame.pack(fill=tk.BOTH, expand=True)

        table = ttk.Treeview(table_frame, columns=("value", "count"), show="headings", height=5)
        table.heading("value", text=title)
        table.heading("count", text="Cells")
        table.column("value", width=150, stretch=True)
        table.column("count", width=90, stretch=False, anchor=tk.E)
        scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=table.yview)
        table.configure(yscrollcommand=scroll.set)
        table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        edit_row = ttk.Frame(holder)
        edit_row.pack(fill=tk.X, pady=(4, 0))

        selected_var = tk.StringVar(value="—")
        new_val_var = tk.StringVar()
        self._table_selected_vars[kind] = selected_var
        self._table_entry_vars[kind] = new_val_var

        ttk.Label(edit_row, text="Selected:").pack(side=tk.LEFT)
        ttk.Label(edit_row, textvariable=selected_var, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(2, 6))
        ttk.Label(edit_row, text="New:").pack(side=tk.LEFT)
        new_entry = ttk.Entry(edit_row, textvariable=new_val_var, width=8)
        new_entry.pack(side=tk.LEFT, padx=(2, 4))

        apply_btn = self._button(
            edit_row, "Apply",
            lambda k=kind, t=table: self._apply_table_edit_from_bar(k, t),
            width=5,
        )
        apply_btn.pack(side=tk.LEFT, padx=2)
        new_entry.bind("<Return>", lambda _e, k=kind, t=table: self._apply_table_edit_from_bar(k, t))

        revert_btn = self._button(
            edit_row, "Revert all",
            self._revert_to_original,
            width=9,
        )
        revert_btn.pack(side=tk.RIGHT)

        table.bind("<<TreeviewSelect>>", lambda _e, k=kind, t=table: self._table_row_selected(k, t))
        table.bind("<Double-1>", lambda event, k=kind, t=table: self._table_double_clicked(event, k, t))
        table.bind("<Return>", lambda _e, k=kind, t=table: self._table_enter_pressed(k, t))

        return table

    def _linked_slider(self, parent: tk.Widget, row: int, variable: tk.StringVar,
                       low: float, high: float, column: int = 0, columnspan: int = 2) -> ttk.Scale:
        state = {"updating": False}

        def moved(value: str) -> None:
            if not state["updating"]:
                variable.set(f"{float(value):.2f}")

        slider = ttk.Scale(parent, from_=low, to=high, orient=tk.HORIZONTAL, command=moved)
        slider.grid(row=row, column=column, columnspan=columnspan, sticky="ew", pady=(2, 0))

        def sync(*_args) -> None:
            try:
                value = float(variable.get())
            except ValueError:
                return
            if low <= value <= high and abs(slider.get() - value) > 0.005:
                state["updating"] = True
                try:
                    slider.set(value)
                finally:
                    state["updating"] = False

        variable.trace_add("write", sync)
        sync()
        return slider

    def _point_editor(self, parent: ttk.LabelFrame, title: str,
                      variables: dict[str, tk.StringVar], row: int,
                      extra_caption: str = "", extra_key: str = "",
                      extra_range: tuple[float, float] = (0.0, 30.0)) -> None:
        group = ttk.LabelFrame(parent, text=title, padding=5)
        group.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(group, text="Specify by").grid(row=0, column=0, sticky=tk.W)
        ttk.Combobox(group, textvariable=variables["mode"], values=("XYZ", "Direction"),
                     state="readonly", width=12).grid(row=0, column=1, columnspan=2, sticky=tk.W)
        entries: dict[str, ttk.Entry] = {}
        for column, (label, key) in enumerate((("X", "x"), ("Y", "y"), ("Z", "z"))):
            ttk.Label(group, text=f"{label} mm").grid(row=1, column=column)
            entry = ttk.Entry(group, textvariable=variables[key], width=9)
            entry.grid(row=2, column=column, padx=2, sticky="ew")
            entries[key] = entry
        for column, (label, key) in enumerate((("Azimuth °", "az"), ("Elevation °", "el"), ("Distance mm", "distance"))):
            ttk.Label(group, text=label).grid(row=3, column=column, pady=(4, 0))
            entry = ttk.Entry(group, textvariable=variables[key], width=9)
            entry.grid(row=4, column=column, padx=2, sticky="ew")
            entries[key] = entry
            group.columnconfigure(column, weight=1)

        slider_controls = []
        for index in range(3):
            label = ttk.Label(group, width=12)
            label.grid(row=5 + index, column=0, sticky=tk.W)
            state = {"variable": variables["x"], "updating": False, "low": -100.0, "high": 100.0}

            def moved(value: str, binding=state) -> None:
                if not binding["updating"]:
                    binding["variable"].set(f"{float(value):.2f}")

            slider = ttk.Scale(group, orient=tk.HORIZONTAL, command=moved)
            slider.grid(row=5 + index, column=1, columnspan=2, sticky="ew", pady=2)
            slider_controls.append((label, slider, state))
        self.point_sliders[title] = [slider for _label, slider, _state in slider_controls]

        def sync(binding: dict, slider: ttk.Scale) -> None:
            try:
                value = float(binding["variable"].get())
            except ValueError:
                return
            if binding["low"] <= value <= binding["high"] and abs(slider.get() - value) > 0.005:
                binding["updating"] = True
                try:
                    slider.set(value)
                finally:
                    binding["updating"] = False

        current_mode = {"value": variables["mode"].get()}

        def configure_mode(*_args) -> None:
            mode = variables["mode"].get()
            if mode != current_mode["value"]:
                try:
                    if mode == "Direction":
                        converted = direction_from_position(tuple(float(variables[key].get()) for key in ("x", "y", "z")))
                        keys = ("az", "el", "distance")
                    else:
                        converted = position_from_direction(
                            float(variables["az"].get()), float(variables["el"].get()),
                            float(variables["distance"].get()))
                        keys = ("x", "y", "z")
                    for key, value in zip(keys, converted):
                        variables[key].set(f"{value:.4f}")
                except ValueError:
                    pass
                current_mode["value"] = mode
            if mode == "XYZ":
                specs = (("X mm", "x", -100.0, 100.0), ("Y mm", "y", -100.0, 100.0),
                         ("Z mm", "z", 1.0, 200.0))
            else:
                specs = (("Azimuth °", "az", -180.0, 180.0), ("Elevation °", "el", -90.0, 90.0),
                         ("Distance mm", "distance", 1.0, 200.0))
            active_keys = {key for _caption, key, _low, _high in specs}
            for key, entry in entries.items():
                entry.configure(state="normal" if key in active_keys else "disabled")
            for (label, slider, binding), (caption, key, low, high) in zip(slider_controls, specs):
                label.configure(text=caption)
                binding["variable"] = variables[key]
                binding["low"] = low
                binding["high"] = high
                binding["updating"] = True
                try:
                    slider.configure(from_=low, to=high)
                finally:
                    binding["updating"] = False
                sync(binding, slider)

        for key in ("x", "y", "z", "az", "el", "distance"):
            variable = variables[key]
            for _label, slider, binding in slider_controls:
                variable.trace_add("write", lambda *_args, v=variable, s=slider, b=binding:
                                   sync(b, s) if b["variable"] is v else None)
        variables["mode"].trace_add("write", configure_mode)
        configure_mode()

        if extra_key and extra_key in variables:
            ttk.Label(group, text=extra_caption).grid(row=8, column=0, columnspan=2, sticky=tk.W, pady=(6, 0))
            extra_entry = ttk.Entry(group, textvariable=variables[extra_key], width=9)
            extra_entry.grid(row=8, column=2, padx=2, sticky="ew", pady=(6, 0))
            self._linked_slider(group, 9, variables[extra_key], extra_range[0], extra_range[1], column=0, columnspan=3)

    def _browse(self) -> None:
        filename = filedialog.askopenfilename(
            title="Select design image or saved design",
            filetypes=[("Design files", "*.png *.bmp *.tif *.tiff *.npz"), ("All files", "*.*")],
        )
        if filename:
            self.path_var.set(filename)
            self._load()

    def _submit(self, work: Callable, completed: Callable, status: str) -> None:
        if self.busy:
            return
        self.busy = True
        self.status_var.set(status)
        for button in self.action_buttons:
            button.configure(state=tk.DISABLED)
        self.progress.start(12)

        def run() -> None:
            try:
                result = work()
                self.results.put((completed, result, None, True))
            except BaseException as error:
                self.results.put((completed, None, error, True))

        self.worker.submit(run)

    def _poll_results(self) -> None:
        try:
            while True:
                completed, result, error, blocking = self.results.get_nowait()
                if blocking:
                    self.busy = False
                    for button in self.action_buttons:
                        button.configure(state=tk.NORMAL)
                else:
                    self.preview_running = False
                if error is None:
                    completed(result)
                else:
                    self.status_var.set(f"Error: {error}")
                    if blocking:
                        messagebox.showerror("Dot EBL Preview", str(error), parent=self.root)
                    else:
                        self.live_var.set(False)
                        self._cancel_preview_request()
                self._start_pending_preview()
                if not self.busy and not self.preview_running:
                    self.progress.stop()
        except Empty:
            pass
        self._poll_viewer_events()
        if not self.closed:
            if not hasattr(self, "_last_poll_time"):
                self._last_poll_time = perf_counter()
            elapsed = perf_counter() - self._last_poll_time
            delay_ms = max(1, min(16, int((0.016 - elapsed) * 1000))) if elapsed < 0.016 else 1
            self._last_poll_time = perf_counter()
            self.root.after(delay_ms, self._poll_results)

    def _poll_viewer_events(self) -> None:
        viewer = self.viewer
        if viewer is None:
            return
        latest_frame: tuple[int, Image.Image, int] | None = None
        latest_scene: SceneSettings | None = None
        if getattr(self, "_last_displayed_viewer", None) is not viewer:
            self._last_displayed_viewer = viewer
            self._last_displayed_serial = -1
            self._last_displayed_quality = -1
        try:
            while True:
                kind, payload = viewer.events.get_nowait()
                if kind == "opened":
                    self.status_var.set("Live OpenGL rendering ready. Drag in the diffraction pane or use the scene controls.")
                elif kind == "frame":
                    serial = payload[0]
                    image = payload[1]
                    quality = getattr(payload, "quality", 0) if hasattr(payload, "quality") else (payload[2] if len(payload) > 2 else 0)
                    if serial > self._last_displayed_serial or (serial == self._last_displayed_serial and quality > self._last_displayed_quality):
                        latest_frame = (serial, image, quality)
                elif kind == "scene":
                    latest_scene = payload
                elif kind == "capture":
                    token, image = payload
                    action, path = self._capture_actions.pop(token, ("refresh", None))
                    self.preview_image = image
                    if action == "save" and path is not None:
                        image.save(path, format="PNG")
                        self.status_var.set(f"Saved full-resolution preview: {path}")
                    else:
                        self._last_displayed_serial = viewer.serial
                        self._last_displayed_quality = 1
                        self._set_panel("preview", image, "OpenGL • full resolution")
                        self.status_var.set("Captured current full-resolution OpenGL preview.")
                elif kind == "error":
                    self.status_var.set(f"Live OpenGL error: {payload}")
                    self.live_var.set(False)
                elif kind == "closed":
                    if self.viewer is viewer:
                        self.viewer = None
                        self._last_displayed_viewer = None
                        self._last_displayed_serial = -1
                        self._last_displayed_quality = -1
                        self.live_var.set(False)
        except Empty:
            pass
        if latest_scene is not None:
            self._apply_viewer_scene(latest_scene)
        if latest_frame is not None:
            serial, image, quality = latest_frame
            self._last_displayed_serial = serial
            self._last_displayed_quality = quality
            self.preview_image = image
            self._set_panel("preview", image, "OpenGL • fast while moving, full resolution when still")

    def _apply_viewer_scene(self, scene: SceneSettings) -> None:
        self._from_viewer = True
        try:
            for variables, position in ((self.source_vars, scene.light_pos),
                                        (self.observer_vars, scene.camera_pos)):
                for key, value in zip(("x", "y", "z"), position):
                    variables[key].set(f"{value:.4f}")
                for key, value in zip(("az", "el", "distance"), direction_from_position(position)):
                    variables[key].set(f"{value:.4f}")
            self.orientation_var.set(f"{scene.orientation_deg:.4f}")
            if "size" in self.source_vars:
                self.source_vars["size"].set(f"{scene.source_size_mm:.2f}")
            if "aperture" in self.observer_vars:
                self.observer_vars["aperture"].set(f"{scene.aperture_mm:.2f}")
        finally:
            self._from_viewer = False

    def _load(self) -> None:
        if self.busy:
            return
        path = self.path_var.get().strip()
        image_format = self.format_var.get()
        try:
            pitch = float(self.pitch_var.get())
        except ValueError:
            messagebox.showerror("Invalid pitch", "Enter a numeric holopixel pitch in µm.", parent=self.root)
            return

        def work():
            design = load_gui_design(path, image_format, pitch)
            source_raw = None
            source_image = None
            if Path(path).suffix.lower() != ".npz":
                source_raw = load_image_rgb(path)
                if source_raw.dtype == np.uint16:
                    vis = np.zeros((*design.shape, 3), dtype=np.uint8)
                    vis[:, :, 0] = np.clip(source_raw[:, :, 0] >> 4, 0, 255).astype(np.uint8)
                    vis[:, :, 1] = np.clip(source_raw[:, :, 1] >> 8, 0, 255).astype(np.uint8)
                    vis[:, :, 2] = np.where(design.active, 255, 0).astype(np.uint8)
                    source_image = Image.fromarray(vis, mode="RGB")
                else:
                    source_image = Image.fromarray(source_raw, mode="RGB")
            else:
                source_raw, source_image = encode_gui_design_image(design, image_format)
            return (design, source_raw, source_image, parameter_counts(design, "gratings"),
                    parameter_counts(design, "angles"), parameter_map(design, "gratings"),
                    parameter_map(design, "angles"), Path(path).name)

        self._stop_viewer()
        self._cancel_preview_request()
        self.design = None
        self.original_design = None
        self.source_raw = None
        self.original_source_raw = None
        self.source_image = None
        self.preview_image = None
        for key in self.panel_images:
            self._set_panel(key, None, "Loading design..." if key != "preview" else "Waiting for OpenGL render...")
        self._submit(work, self._loaded, "Loading design and finding parameters...")

    def _loaded(self, result: object) -> None:
        design, source_raw, source_image, periods, angles, period_image, angle_image, filename = result
        self.design = design
        self.original_design = design.copy()
        self.source_raw = source_raw.copy() if source_raw is not None else None
        self.original_source_raw = source_raw.copy() if source_raw is not None else None
        self.source_image = source_image
        self.preview_image = None
        self._table_data["gratings"] = periods
        self._table_data["angles"] = angles
        for table, entries in ((self.period_table, periods), (self.angle_table, angles)):
            table.delete(*table.get_children())
            for value, count in entries:
                table.insert("", tk.END, values=(f"{value:g}", f"{count:,}"))
        for k in ("gratings", "angles"):
            self._table_selected_vars[k].set("—")
            self._table_entry_vars[k].set("")
        self.summary_var.set(
            f"{design.width} × {design.height} cells  •  {design.active_count:,} active  •  "
            f"{len(periods)} periods  •  {len(angles)} angles  •  pitch {design.pitch_nm / 1000:g} µm"
        )
        self._set_panel(
            "source", source_image,
            f"{filename} • {design.width} × {design.height} pixels" if source_image is not None
            else "Saved design has no original RGB source image.",
        )
        for key, image, values, unit in (
            ("periods", period_image, periods, "µm"),
            ("angles", angle_image, angles, "°"),
        ):
            span = f"{values[0][0]:g} to {values[-1][0]:g} {unit}" if values else "no active cells"
            self._set_panel(key, image, f"{span} • dark = inactive")
        self._set_panel("preview", None, "Preparing OpenGL diffraction render...")
        self.status_var.set(f"Loaded {filename}.")
        self._scene_changed()

    @staticmethod
    def _point(variables: dict[str, tk.StringVar]) -> tuple[float, float, float]:
        if variables["mode"].get() == "XYZ":
            return tuple(float(variables[key].get()) for key in ("x", "y", "z"))
        return position_from_direction(
            float(variables["az"].get()), float(variables["el"].get()),
            float(variables["distance"].get()),
        )

    def _scene_settings(self, report_error: bool) -> SceneSettings | None:
        try:
            aperture = float(self.observer_vars["aperture"].get()) if "aperture" in self.observer_vars else 5.0
            source_size = float(self.source_vars["size"].get()) if "size" in self.source_vars else 0.0
            return SceneSettings(
                light_pos=self._point(self.source_vars),
                camera_pos=self._point(self.observer_vars),
                orientation_deg=float(self.orientation_var.get()),
                aperture_mm=aperture,
                source_size_mm=source_size,
            ).validated()
        except ValueError as error:
            if report_error:
                messagebox.showerror("Invalid scene", str(error), parent=self.root)
            return

    def _cancel_preview_request(self) -> None:
        self.scene_revision += 1
        self.preview_pending = None

    def _live_toggled(self) -> None:
        self._scene_changed()

    def _scene_changed(self, *_args) -> None:
        if self._from_viewer:
            return
        self._cancel_preview_request()
        if self.design is not None and self.live_var.get() and self.renderer_var.get() == "OpenGL (fast)":
            settings = self._scene_settings(report_error=False)
            if settings is None:
                self.status_var.set("Enter valid scene values to update the live viewer.")
                return
            if self.viewer is None:
                canvas = self.panel_canvases.get("preview")
                pane_size = None
                if canvas is not None:
                    cw = max(1, canvas.winfo_width() - 16)
                    ch = max(1, canvas.winfo_height() - 16)
                    if cw > 50 and ch > 50:
                        pane_size = (cw, ch)
                self.viewer = RealtimeViewer(self.design, settings, visible=False)
                if pane_size is not None and hasattr(self.viewer, "update_pane_size"):
                    self.viewer.update_pane_size(pane_size)
                self.viewer.start()
                self.status_var.set("Starting live OpenGL rendering...")
            else:
                self.viewer.update_scene(settings)
        else:
            self._stop_viewer()
            if self.design is not None and self.renderer_var.get() == "CPU reference":
                self._set_panel("preview", None, "CPU reference selected • click Refresh preview")

    def _preview_drag_start(self, event: tk.Event, button: int) -> None:
        self._preview_drag = (button, event.x, event.y)

    def _preview_drag_move(self, event: tk.Event, button: int) -> None:
        previous = self._preview_drag
        self._preview_drag = (button, event.x, event.y)
        if previous is None or previous[0] != button or self.viewer is None:
            return
        self.viewer.orbit(
            "camera" if button == 1 else "light",
            delta_az=(event.x - previous[1]) * 0.35,
            delta_el=(previous[2] - event.y) * 0.35,
        )

    def _preview_drag_end(self, _event: tk.Event) -> None:
        self._preview_drag = None

    def _preview_wheel(self, event: tk.Event) -> None:
        if self.viewer is None or event.delta == 0:
            return
        which = "light" if event.state & 0x0001 else "camera"
        self.viewer.orbit(which, distance_factor=0.9 ** (event.delta / 120.0))

    def _stop_viewer(self) -> None:
        viewer = self.viewer
        self.viewer = None
        self._last_displayed_viewer = None
        self._last_displayed_serial = -1
        self._last_displayed_quality = -1
        self._capture_actions.clear()
        if viewer is not None and hasattr(viewer, "close"):
            viewer.close()

    def _preview(self) -> None:
        if self.design is None:
            self._need_design()
            return
        settings = self._scene_settings(report_error=True)
        if settings is None:
            return
        if self.viewer is not None and self.renderer_var.get() == "OpenGL (fast)":
            self._capture_token += 1
            self._capture_actions[self._capture_token] = ("refresh", None)
            self.viewer.capture(self._capture_token)
            self.status_var.set("Capturing current full-resolution OpenGL frame...")
            return
        self._cancel_preview_request()
        self._queue_preview(settings)

    def _queue_preview(self, settings: SceneSettings) -> None:
        if self.design is None:
            return
        self.preview_pending = (self.design, settings, self.renderer_var.get(), self.scene_revision)
        self._start_pending_preview()

    def _start_pending_preview(self) -> None:
        if self.busy or self.preview_running or self.preview_pending is None or self.closed:
            return
        design, settings, backend, revision = self.preview_pending
        self.preview_pending = None
        self.preview_running = True
        self.progress.start(12)
        self.status_var.set(f"Updating {backend} preview...")
        render = render_scene_gpu if backend == "OpenGL (fast)" else render_scene

        def work() -> None:
            try:
                start = perf_counter()
                image = render(design, settings)
                self.results.put((self._previewed, (image, backend, perf_counter() - start,
                                                  revision, design), None, False))
            except BaseException as error:
                self.results.put((self._previewed, None, error, False))

        self.worker.submit(work)

    def _previewed(self, result: object) -> None:
        image, backend, elapsed, revision, design = result
        if revision != self.scene_revision or design is not self.design or backend != self.renderer_var.get():
            return
        self.preview_image = image
        self._set_panel("preview", image, f"{backend} • qualitative spectral diffraction")
        self.status_var.set(f"{backend} preview updated in {elapsed:.2f} s.")

    def _save_gds(self) -> None:
        if self.design is None:
            self._need_design()
            return
        initial = Path(self.path_var.get()).stem or "HOLOGRAM"
        filename = filedialog.asksaveasfilename(
            title="Save Raith GDSII layout", defaultextension=".gds",
            filetypes=[("GDSII layout", "*.gds")], initialfile=f"{initial}.gds",
        )
        if filename:
            design = self.design
            self._submit(lambda: save_gds(design, filename), self._gds_saved, "Generating GDSII layout...")

    def _gds_saved(self, path: object) -> None:
        self.status_var.set(f"Saved GDSII layout: {path}")
        messagebox.showinfo("GDS saved", f"Saved layout to:\n{path}", parent=self.root)

    def _save_preview(self) -> None:
        if self.viewer is not None:
            filename = filedialog.asksaveasfilename(
                title="Save diffraction preview", defaultextension=".png",
                filetypes=[("PNG image", "*.png")], initialfile="diffraction_preview.png",
            )
            if filename:
                self._capture_token += 1
                self._capture_actions[self._capture_token] = ("save", filename)
                self.viewer.capture(self._capture_token)
                self.status_var.set("Capturing full-resolution preview for PNG...")
            return
        if self.preview_image is None:
            messagebox.showinfo("No preview", "Run the diffraction preview first.", parent=self.root)
            return
        filename = filedialog.asksaveasfilename(
            title="Save diffraction preview", defaultextension=".png",
            filetypes=[("PNG image", "*.png")], initialfile="diffraction_preview.png",
        )
        if filename:
            self.preview_image.save(filename, format="PNG")
            self.status_var.set(f"Saved diffraction preview: {filename}")

    def _save_design_image(self) -> None:
        if self.design is None:
            self._need_design()
            return
        initial = f"{Path(self.path_var.get()).stem or 'design'}_modified.png"
        filename = filedialog.asksaveasfilename(
            title="Save design image", defaultextension=".png",
            filetypes=[("PNG image", "*.png"), ("All files", "*.*")], initialfile=initial,
        )
        if filename:
            if self.source_raw is None:
                self.source_raw, self.source_image = encode_gui_design_image(
                    self.design, self.format_var.get(), self.original_source_raw,
                )
            raw = self.source_raw
            self._submit(lambda: save_gui_design_image(filename, raw), self._design_image_saved, "Saving design image...")

    def _design_image_saved(self, path: object) -> None:
        self.status_var.set(f"Saved design image: {path}")
        messagebox.showinfo("Design image saved", f"Saved design image to:\n{path}", parent=self.root)

    def _export_bundle(self) -> None:
        if self.design is None:
            self._need_design()
            return
        initial = Path(self.path_var.get()).stem or "HOLOGRAM"
        output_dir = filedialog.askdirectory(
            title="Select destination directory for fabrication bundle",
            initialdir=str(Path(self.path_var.get()).parent or "."),
        )
        if output_dir:
            design = self.design
            self._submit(
                lambda: export_gui_bundle(design, output_dir, layout_name=initial),
                self._bundle_exported,
                "Exporting fabrication bundle (GDS, texts, NPZ, manifest, previews)...",
            )

    def _bundle_exported(self, path: object) -> None:
        self.status_var.set(f"Exported fabrication bundle: {path}")
        messagebox.showinfo("Fabrication bundle exported", f"Saved complete fabrication bundle to:\n{path}", parent=self.root)

    def _table_row_selected(self, kind: str, table: ttk.Treeview) -> None:
        selected = table.selection()
        if not selected:
            self._table_selected_vars[kind].set("—")
            self._table_entry_vars[kind].set("")
            return
        item_id = selected[0]
        vals = table.item(item_id, "values")
        if vals:
            current_val = vals[0]
            unit = " µm" if kind == "gratings" else "°"
            self._table_selected_vars[kind].set(f"{current_val}{unit}")
            self._table_entry_vars[kind].set(current_val)

    def _table_double_clicked(self, event: tk.Event, kind: str, table: ttk.Treeview) -> None:
        region = table.identify("region", event.x, event.y)
        if region not in ("tree", "cell"):
            return
        column = table.identify_column(event.x)
        if column not in ("#1", "#0"):
            return
        item = table.identify_row(event.y)
        if not item:
            return
        self._start_inline_editing(kind, table, item)

    def _table_enter_pressed(self, kind: str, table: ttk.Treeview) -> None:
        selected = table.selection()
        if selected:
            self._start_inline_editing(kind, table, selected[0])

    def _start_inline_editing(self, kind: str, table: ttk.Treeview, item: str) -> None:
        if self._inline_entry is not None:
            try:
                self._inline_entry.destroy()
            except Exception:
                pass
            self._inline_entry = None

        bbox = table.bbox(item, "#1")
        if not bbox:
            return
        x, y, w, h = bbox
        vals = table.item(item, "values")
        if not vals:
            return
        old_val_str = str(vals[0])

        entry_var = tk.StringVar(value=old_val_str)
        entry = ttk.Entry(table, textvariable=entry_var)
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_set()
        entry.selection_range(0, tk.END)
        self._inline_entry = entry

        committed = [False]

        def commit(*_args) -> None:
            if committed[0]:
                return
            committed[0] = True
            new_text = entry_var.get().strip()
            try:
                entry.destroy()
            except Exception:
                pass
            self._inline_entry = None
            if new_text and new_text != old_val_str:
                self._update_parameter_value(kind, old_val_str, new_text)

        def cancel(*_args) -> None:
            if committed[0]:
                return
            committed[0] = True
            try:
                entry.destroy()
            except Exception:
                pass
            self._inline_entry = None

        entry.bind("<Return>", commit)
        entry.bind("<Escape>", cancel)
        entry.bind("<FocusOut>", commit)

    def _apply_table_edit_from_bar(self, kind: str, table: ttk.Treeview) -> None:
        selected = table.selection()
        if not selected:
            messagebox.showinfo("No selection", f"Select a row in the {kind} table first.", parent=self.root)
            return
        item_id = selected[0]
        vals = table.item(item_id, "values")
        if not vals:
            return
        old_val_str = str(vals[0])
        new_val_str = self._table_entry_vars[kind].get().strip()
        if not new_val_str:
            return
        self._update_parameter_value(kind, old_val_str, new_val_str)

    def _update_parameter_value(self, kind: str, old_val_str: str, new_val_str: str) -> None:
        if self.design is None:
            self._need_design()
            return
        try:
            old_val = float(old_val_str)
            new_val = float(new_val_str)
        except ValueError:
            messagebox.showerror("Invalid number", f"'{new_val_str}' is not a valid number.", parent=self.root)
            return

        try:
            self.design, count = apply_parameter_edit(self.design, kind, old_val, new_val)
        except ValueError as err:
            messagebox.showerror("Invalid parameter", str(err), parent=self.root)
            return

        if count == 0:
            return

        self._refresh_after_parameter_change(kind, old_val, new_val, count)

    def _refresh_after_parameter_change(self, kind: str, old_val: float, new_val: float, count: int) -> None:
        if self.design is None:
            return

        periods = parameter_counts(self.design, "gratings")
        angles = parameter_counts(self.design, "angles")
        self._table_data["gratings"] = periods
        self._table_data["angles"] = angles

        for table, entries in ((self.period_table, periods), (self.angle_table, angles)):
            table.delete(*table.get_children())
            for val, cnt in entries:
                table.insert("", tk.END, values=(f"{val:g}", f"{cnt:,}"))

        for k in ("gratings", "angles"):
            self._table_selected_vars[k].set("—")
            self._table_entry_vars[k].set("")

        self.summary_var.set(
            f"{self.design.width} × {self.design.height} cells  •  {self.design.active_count:,} active  •  "
            f"{len(periods)} periods  •  {len(angles)} angles  •  pitch {self.design.pitch_nm / 1000:g} µm"
        )

        self.source_raw, self.source_image = encode_gui_design_image(
            self.design, self.format_var.get(), self.original_source_raw,
        )
        self._set_panel(
            "source", self.source_image,
            f"Modified design image ({self.format_var.get()}) • {self.design.width} × {self.design.height} pixels",
        )

        period_image = parameter_map(self.design, "gratings")
        span_p = f"{periods[0][0]:g} to {periods[-1][0]:g} µm" if periods else "no active cells"
        self._set_panel("periods", period_image, f"{span_p} • dark = inactive")

        angle_image = parameter_map(self.design, "angles")
        span_a = f"{angles[0][0]:g} to {angles[-1][0]:g} °" if angles else "no active cells"
        self._set_panel("angles", angle_image, f"{span_a} • dark = inactive")

        self._stop_viewer()
        if self.live_var.get() and self.renderer_var.get() == "OpenGL (fast)":
            self._scene_changed()
        elif self.renderer_var.get() == "CPU reference":
            settings = self._scene_settings(report_error=False)
            if settings:
                self._cancel_preview_request()
                self._queue_preview(settings)
        else:
            self._scene_changed()

        unit = "µm" if kind == "gratings" else "°"
        self.status_var.set(
            f"Updated {kind}: {old_val:g} {unit} → {new_val:g} {unit} ({count:,} cells). All 4 graphs updated."
        )

    def _revert_to_original(self) -> None:
        if self.original_design is None:
            return
        self.design = self.original_design.copy()
        if self.original_source_raw is not None:
            self.source_raw = self.original_source_raw.copy()
            if self.source_raw.dtype == np.uint16:
                vis = np.zeros((*self.design.shape, 3), dtype=np.uint8)
                vis[:, :, 0] = np.clip(self.source_raw[:, :, 0] >> 4, 0, 255).astype(np.uint8)
                vis[:, :, 1] = np.clip(self.source_raw[:, :, 1] >> 8, 0, 255).astype(np.uint8)
                vis[:, :, 2] = np.where(self.design.active, 255, 0).astype(np.uint8)
                self.source_image = Image.fromarray(vis, mode="RGB")
            else:
                self.source_image = Image.fromarray(self.source_raw, mode="RGB")
        else:
            self.source_raw, self.source_image = encode_gui_design_image(
                self.design, self.format_var.get(),
            )

        periods = parameter_counts(self.design, "gratings")
        angles = parameter_counts(self.design, "angles")
        self._table_data["gratings"] = periods
        self._table_data["angles"] = angles

        for table, entries in ((self.period_table, periods), (self.angle_table, angles)):
            table.delete(*table.get_children())
            for val, cnt in entries:
                table.insert("", tk.END, values=(f"{val:g}", f"{cnt:,}"))

        for k in ("gratings", "angles"):
            self._table_selected_vars[k].set("—")
            self._table_entry_vars[k].set("")

        self.summary_var.set(
            f"{self.design.width} × {self.design.height} cells  •  {self.design.active_count:,} active  •  "
            f"{len(periods)} periods  •  {len(angles)} angles  •  pitch {self.design.pitch_nm / 1000:g} µm"
        )

        filename = Path(self.path_var.get()).name if self.path_var.get() else "Design"
        self._set_panel("source", self.source_image, f"{filename} • {self.design.width} × {self.design.height} pixels")

        period_image = parameter_map(self.design, "gratings")
        span_p = f"{periods[0][0]:g} to {periods[-1][0]:g} µm" if periods else "no active cells"
        self._set_panel("periods", period_image, f"{span_p} • dark = inactive")

        angle_image = parameter_map(self.design, "angles")
        span_a = f"{angles[0][0]:g} to {angles[-1][0]:g} °" if angles else "no active cells"
        self._set_panel("angles", angle_image, f"{span_a} • dark = inactive")

        self._stop_viewer()
        self._scene_changed()
        self.status_var.set("Reverted all parameters to originally imported design. All 4 graphs updated.")

    def _need_design(self) -> None:
        messagebox.showinfo("No design", "Load a design image first.", parent=self.root)

    def _set_panel(self, key: str, image: Image.Image | None, caption: str) -> None:
        self.panel_images[key] = image
        if self.panel_captions[key].get() != caption:
            self.panel_captions[key].set(caption)
        self._draw_panel(key)

    def _draw_panel(self, key: str) -> None:
        canvas = self.panel_canvases[key]
        if not hasattr(self, "panel_canvas_image_items"):
            self.panel_canvas_image_items = {}
        if not hasattr(self, "panel_canvas_text_items"):
            self.panel_canvas_text_items = {}

        image = self.panel_images[key]
        if image is None:
            self.panel_photos.pop(key, None)
            img_item = self.panel_canvas_image_items.pop(key, None)
            if img_item is not None:
                canvas.delete(img_item)
            text_item = self.panel_canvas_text_items.get(key)
            cx, cy = canvas.winfo_width() // 2, canvas.winfo_height() // 2
            text = self.panel_captions[key].get()
            width = max(100, canvas.winfo_width() - 32)
            if text_item is not None:
                canvas.coords(text_item, cx, cy)
                canvas.itemconfig(text_item, text=text, width=width)
            else:
                self.panel_canvas_text_items[key] = canvas.create_text(
                    cx, cy, text=text, fill="#aab7c5",
                    font=("Segoe UI", 11), width=width, justify=tk.CENTER)
            return

        text_item = self.panel_canvas_text_items.pop(key, None)
        if text_item is not None:
            canvas.delete(text_item)

        width = max(1, canvas.winfo_width() - 16)
        height = max(1, canvas.winfo_height() - 16)
        scale = min(width / image.width, height / image.height)
        display_size = (max(1, int(image.width * scale)),
                        max(1, int(image.height * scale)))
        if image.size == display_size:
            resized = image
        else:
            sampling = Image.Resampling.BILINEAR if key == "preview" else Image.Resampling.NEAREST
            resized = image.resize(display_size, sampling)
        photo = ImageTk.PhotoImage(resized, master=self.root)
        self.panel_photos[key] = photo

        cx, cy = canvas.winfo_width() // 2, canvas.winfo_height() // 2
        img_item = self.panel_canvas_image_items.get(key)
        if img_item is not None:
            canvas.coords(img_item, cx, cy)
            canvas.itemconfig(img_item, image=photo)
        else:
            self.panel_canvas_image_items[key] = canvas.create_image(cx, cy, image=photo, anchor=tk.CENTER)

    def _close(self) -> None:
        self.closed = True
        if getattr(self, "_inline_entry", None) is not None:
            try:
                self._inline_entry.destroy()
            except Exception:
                pass
            self._inline_entry = None
        self._cancel_preview_request()
        self._stop_viewer()
        self.worker.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    DesignWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
