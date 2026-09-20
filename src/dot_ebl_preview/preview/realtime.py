"""Continuous OpenGL viewer with fast interaction and full-resolution settling."""

from __future__ import annotations

from dataclasses import replace
import math
from queue import Empty, Queue
from threading import Event, Lock, Thread
from time import monotonic, sleep

import numpy as np
from PIL import Image

from dot_ebl_preview.core.model import Design
from dot_ebl_preview.gui_logic import SceneSettings, direction_from_position, position_from_direction
from dot_ebl_preview.optics.presets import get_optical_preset
from dot_ebl_preview.optics.tables import premultiplied_XYZ
from dot_ebl_preview.preview.gl_renderer import (
    FRAGMENT_SHADER,
    VERTEX_SHADER,
    release_glfw,
    retain_glfw,
)


DISPLAY_FRAGMENT_SHADER = """#version 330 core
uniform sampler2D u_image;
uniform vec2 u_viewport;
uniform vec2 u_image_size;
out vec4 pixel_color;
void main() {
    float scale = min(u_viewport.x / u_image_size.x, u_viewport.y / u_image_size.y);
    vec2 span = u_image_size * scale;
    vec2 origin = (u_viewport - span) * 0.5;
    vec2 uv = (gl_FragCoord.xy - origin) / span;
    if (uv.x < 0.0 || uv.y < 0.0 || uv.x >= 1.0 || uv.y >= 1.0) {
        pixel_color = vec4(0.07, 0.09, 0.13, 1.0);
    } else {
        pixel_color = texture(u_image, uv);
    }
}
"""


class FramePayload(tuple):
    """2-tuple (serial, image) with an extra quality attribute."""

    def __new__(cls, serial: int, image: Image.Image, quality: int = 0):
        obj = super().__new__(cls, (serial, image))
        obj._quality = quality
        return obj

    @property
    def quality(self) -> int:
        return self._quality


class EventQueue(Queue):
    """Event queue with a 1-slot mailbox for live frames to prevent stale frame accumulation."""

    def put(self, item: tuple[str, object], block: bool = True, timeout: float | None = None) -> None:
        with self.not_full:
            if self.maxsize > 0:
                if not block:
                    if self._qsize() >= self.maxsize:
                        raise Full
                elif timeout is None:
                    while self._qsize() >= self.maxsize:
                        self.not_full.wait()
                elif timeout < 0:
                    raise ValueError("'timeout' must be a non-negative number")
                else:
                    endtime = monotonic() + timeout
                    while self._qsize() >= self.maxsize:
                        remaining = endtime - monotonic()
                        if remaining <= 0.0:
                            raise Full
                        self.not_full.wait(remaining)

            if item[0] == "frame":
                for idx, existing in enumerate(self.queue):
                    if existing[0] == "frame":
                        self.queue[idx] = item
                        return

            self._put(item)
            self.unfinished_tasks += 1
            self.not_empty.notify()


class RealtimeViewer:
    """A visible GPU viewer. Tk sends the latest scene; GLFW owns its own thread."""

    def __init__(self, design: Design, scene: SceneSettings, visible: bool = True,
                 pane_size: tuple[int, int] | None = None) -> None:
        self.design = design
        self.visible = visible
        self.pane_size = pane_size
        self.events: Queue[tuple[str, object]] = EventQueue()
        self._captures: Queue[int] = Queue()
        self._lock = Lock()
        self._scene = scene.validated()
        self._serial = 0
        self._changed_at = monotonic()
        self._stop = Event()
        self._wake = Event()
        self._thread = Thread(target=self._run, name="dot-ebl-live-opengl", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)

    @property
    def is_alive(self) -> bool:
        return self._thread.is_alive()

    @property
    def serial(self) -> int:
        with self._lock:
            return self._serial

    def update_scene(self, scene: SceneSettings) -> None:
        scene.validated()
        with self._lock:
            if scene != self._scene:
                self._scene = scene
                self._serial += 1
                self._changed_at = monotonic()
                self._wake.set()

    def update_pane_size(self, size: tuple[int, int]) -> None:
        with self._lock:
            self.pane_size = size

    def capture(self, token: int) -> None:
        self._captures.put(token)
        self._wake.set()

    def _snapshot(self) -> tuple[SceneSettings, int, float]:
        with self._lock:
            return self._scene, self._serial, self._changed_at

    def orbit(self, which: str, delta_az: float = 0.0, delta_el: float = 0.0,
              distance_factor: float = 1.0) -> None:
        """Update the scene from a mouse gesture in either the Tk pane or GLFW window."""
        if which not in ("camera", "light"):
            raise ValueError(f"Unknown orbit target: {which}")
        scene, _serial, _changed = self._snapshot()
        point = scene.camera_pos if which == "camera" else scene.light_pos
        az, el, distance = direction_from_position(point)
        updated = position_from_direction(az + delta_az, max(-90.0, min(90.0, el + delta_el)),
                                          max(1.0, min(500.0, distance * distance_factor)))
        scene = replace(scene, **({"camera_pos": updated} if which == "camera" else {"light_pos": updated}))
        self.update_scene(scene)
        self.events.put(("scene", scene))

    def _run(self) -> None:
        try:
            self._run_gl()
        except BaseException as error:
            self.events.put(("error", str(error)))
        finally:
            self.events.put(("closed", None))

    def _run_gl(self) -> None:
        import glfw
        from OpenGL import GL
        from OpenGL.GL import shaders

        retain_glfw()
        window = None
        programs: list[int] = []
        textures: list[int] = []
        framebuffers: list[int] = []
        vao = 0
        try:
            glfw.window_hint(glfw.VISIBLE, glfw.TRUE if self.visible else glfw.FALSE)
            glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
            glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
            glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
            window = glfw.create_window(920, 760, "Dot EBL Live OpenGL", None, None)
            if not window:
                raise RuntimeError("OpenGL 3.3 context is unavailable for the live viewer.")
            glfw.make_context_current(window)
            glfw.swap_interval(1 if self.visible else 0)
            if self.visible:
                glfw.focus_window(window)
            self.events.put(("opened", None))

            spectral_program = shaders.compileProgram(
                shaders.compileShader(VERTEX_SHADER, GL.GL_VERTEX_SHADER),
                shaders.compileShader(FRAGMENT_SHADER, GL.GL_FRAGMENT_SHADER),
            )
            programs.append(spectral_program)

            display_program = 0
            display_uniforms: dict[str, int] = {}
            if self.visible:
                display_program = shaders.compileProgram(
                    shaders.compileShader(VERTEX_SHADER, GL.GL_VERTEX_SHADER),
                    shaders.compileShader(DISPLAY_FRAGMENT_SHADER, GL.GL_FRAGMENT_SHADER),
                )
                programs.append(display_program)
                display_uniforms = {
                    name: GL.glGetUniformLocation(display_program, name)
                    for name in ("u_image", "u_viewport", "u_image_size")
                }
                GL.glUseProgram(display_program)
                GL.glUniform1i(display_uniforms["u_image"], 2)

            vao = int(GL.glGenVertexArrays(1))
            GL.glBindVertexArray(vao)

            h, w = self.design.shape
            limit = min(int(GL.glGetIntegerv(GL.GL_MAX_TEXTURE_SIZE)),
                        int(GL.glGetIntegerv(GL.GL_MAX_RENDERBUFFER_SIZE)))
            if w > limit or h > limit:
                raise RuntimeError(f"Design {w}×{h} exceeds this GPU's render target limit of {limit} pixels per axis.")
            ratio = min(1.0, 384.0 / max(w, h))
            fast_size = (max(1, round(w * ratio)), max(1, round(h * ratio)))

            settled_bound = max(384.0, float(max(self.pane_size)) if self.pane_size is not None else 384.0)
            settled_ratio = min(1.0, settled_bound / max(w, h))
            settled_size = (max(1, round(w * settled_ratio)), max(1, round(h * settled_ratio)))
            full_size = (w, h)

            packed = np.empty((h, w, 4), dtype=np.float32)
            packed[:, :, 0] = self.design.period_nm
            packed[:, :, 1] = self.design.angle_deg
            packed[:, :, 2] = self.design.active
            packed[:, :, 3] = self.design.fallback_intensity if self.design.fallback_intensity is not None else 0.0
            packed = np.ascontiguousarray(packed)
            spectrum = np.ascontiguousarray(premultiplied_XYZ(), dtype=np.float32)
            light_xyz = spectrum.sum(axis=0, dtype=np.float64)
            white_xy = light_xyz[:2] / light_xyz.sum()

            data_texture, spectrum_texture, fast_texture = [int(value) for value in GL.glGenTextures(3)]
            textures.extend((data_texture, spectrum_texture, fast_texture))
            GL.glActiveTexture(GL.GL_TEXTURE0)
            GL.glBindTexture(GL.GL_TEXTURE_2D, data_texture)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
            GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA32F, w, h, 0, GL.GL_RGBA, GL.GL_FLOAT, packed)
            GL.glActiveTexture(GL.GL_TEXTURE1)
            GL.glBindTexture(GL.GL_TEXTURE_1D, spectrum_texture)
            GL.glTexParameteri(GL.GL_TEXTURE_1D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
            GL.glTexParameteri(GL.GL_TEXTURE_1D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
            GL.glTexImage1D(GL.GL_TEXTURE_1D, 0, GL.GL_RGB32F, 77, 0, GL.GL_RGB, GL.GL_FLOAT, spectrum)

            GL.glActiveTexture(GL.GL_TEXTURE2)
            GL.glBindTexture(GL.GL_TEXTURE_2D, fast_texture)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
            GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, fast_size[0], fast_size[1], 0,
                            GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, None)
            fast_fbo = int(GL.glGenFramebuffers(1))
            framebuffers.append(fast_fbo)
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fast_fbo)
            GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0,
                                      GL.GL_TEXTURE_2D, fast_texture, 0)
            if GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER) != GL.GL_FRAMEBUFFER_COMPLETE:
                raise RuntimeError("OpenGL could not create a fast preview render target.")

            if settled_size != fast_size:
                settled_texture = int(GL.glGenTextures(1))
                textures.append(settled_texture)
                GL.glBindTexture(GL.GL_TEXTURE_2D, settled_texture)
                GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
                GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
                GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, settled_size[0], settled_size[1], 0,
                                GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, None)
                settled_fbo = int(GL.glGenFramebuffers(1))
                framebuffers.append(settled_fbo)
                GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, settled_fbo)
                GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0,
                                          GL.GL_TEXTURE_2D, settled_texture, 0)
                if GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER) != GL.GL_FRAMEBUFFER_COMPLETE:
                    raise RuntimeError("OpenGL could not create a settled preview render target.")
            else:
                settled_texture = fast_texture
                settled_fbo = fast_fbo

            full_texture = 0
            full_fbo = 0

            def ensure_full_target() -> tuple[int, int]:
                nonlocal full_texture, full_fbo
                if full_texture == 0:
                    full_texture = int(GL.glGenTextures(1))
                    textures.append(full_texture)
                    GL.glActiveTexture(GL.GL_TEXTURE2)
                    GL.glBindTexture(GL.GL_TEXTURE_2D, full_texture)
                    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
                    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
                    GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, full_size[0], full_size[1], 0,
                                    GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, None)
                    full_fbo = int(GL.glGenFramebuffers(1))
                    framebuffers.append(full_fbo)
                    GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, full_fbo)
                    GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0,
                                              GL.GL_TEXTURE_2D, full_texture, 0)
                    if GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER) != GL.GL_FRAMEBUFFER_COMPLETE:
                        raise RuntimeError("OpenGL could not create a full preview render target.")
                return full_fbo, full_texture

            uniforms = {
                name: GL.glGetUniformLocation(spectral_program, name)
                for name in (
                    "u_design", "u_spectrum", "u_size", "u_target_size", "u_pitch_mm",
                    "u_orientation_deg", "u_light_pos", "u_camera_pos", "u_aperture_mm",
                    "u_light_y", "u_white_xy",
                )
            }

            GL.glDisable(GL.GL_FRAMEBUFFER_SRGB)
            GL.glUseProgram(spectral_program)
            GL.glUniform1i(uniforms["u_design"], 0)
            GL.glUniform1i(uniforms["u_spectrum"], 1)
            GL.glUniform2i(uniforms["u_size"], w, h)
            GL.glUniform1f(uniforms["u_pitch_mm"], self.design.pitch_nm * 1.0e-6)
            GL.glUniform1f(uniforms["u_aperture_mm"],
                           get_optical_preset("corrected").aperture_radius_factor)
            GL.glUniform1f(uniforms["u_light_y"], float(light_xyz[1]))
            GL.glUniform2f(uniforms["u_white_xy"], *white_xy)

            def render_spectral(fbo: int, size: tuple[int, int], scene: SceneSettings) -> None:
                GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)
                GL.glViewport(0, 0, size[0], size[1])
                GL.glUseProgram(spectral_program)
                GL.glActiveTexture(GL.GL_TEXTURE0)
                GL.glBindTexture(GL.GL_TEXTURE_2D, data_texture)
                GL.glActiveTexture(GL.GL_TEXTURE1)
                GL.glBindTexture(GL.GL_TEXTURE_1D, spectrum_texture)
                GL.glUniform2i(uniforms["u_target_size"], *size)
                GL.glUniform1f(uniforms["u_orientation_deg"], scene.orientation_deg)
                GL.glUniform3f(uniforms["u_light_pos"], *scene.light_pos)
                GL.glUniform3f(uniforms["u_camera_pos"], *scene.camera_pos)
                GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)

            def read_frame(fbo: int, size: tuple[int, int]) -> Image.Image:
                GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)
                raw = GL.glReadPixels(0, 0, size[0], size[1], GL.GL_RGBA, GL.GL_UNSIGNED_BYTE)
                rgba = np.frombuffer(raw, dtype=np.uint8).reshape(size[1], size[0], 4)
                return Image.fromarray(np.ascontiguousarray(rgba[::-1, :, :3]), mode="RGB")

            mouse = {"button": None, "last": None}

            def button_callback(_window, button: int, action: int, _mods: int) -> None:
                if action == glfw.PRESS and button in (glfw.MOUSE_BUTTON_LEFT, glfw.MOUSE_BUTTON_RIGHT):
                    mouse["button"] = button
                    mouse["last"] = glfw.get_cursor_pos(window)
                elif action == glfw.RELEASE and button == mouse["button"]:
                    mouse["button"] = None
                    mouse["last"] = None

            def cursor_callback(_window, x: float, y: float) -> None:
                if mouse["button"] is None or mouse["last"] is None:
                    return
                old_x, old_y = mouse["last"]
                mouse["last"] = (x, y)
                which = "camera" if mouse["button"] == glfw.MOUSE_BUTTON_LEFT else "light"
                self.orbit(which, delta_az=(x - old_x) * 0.35, delta_el=(old_y - y) * 0.35)

            def scroll_callback(_window, _xoffset: float, yoffset: float) -> None:
                shifted = (glfw.get_key(window, glfw.KEY_LEFT_SHIFT) == glfw.PRESS or
                           glfw.get_key(window, glfw.KEY_RIGHT_SHIFT) == glfw.PRESS)
                self.orbit("light" if shifted else "camera", distance_factor=math.pow(0.9, yoffset))

            if self.visible:
                glfw.set_mouse_button_callback(window, button_callback)
                glfw.set_cursor_pos_callback(window, cursor_callback)
                glfw.set_scroll_callback(window, scroll_callback)

            rendered_fast = -1
            rendered_full = -1
            pending_fast = -1
            current_texture = fast_texture
            current_size = fast_size
            last_frame_event = 0.0
            while not self._stop.is_set() and (not self.visible or not glfw.window_should_close(window)):
                frame_started = monotonic()
                if self.visible:
                    glfw.poll_events()
                scene, serial, changed_at = self._snapshot()
                if serial != rendered_fast:
                    render_spectral(fast_fbo, fast_size, scene)
                    rendered_fast = serial
                    rendered_full = -1
                    pending_fast = serial
                    current_texture, current_size = fast_texture, fast_size

                # Deliver latest completed fast frame without discarding if newer input was requested.
                if pending_fast == serial and frame_started - last_frame_event >= 1.0 / 75.0:
                    self.events.put(("frame", FramePayload(serial, read_frame(fast_fbo, fast_size), quality=0)))
                    last_frame_event = monotonic()
                    pending_fast = -1

                now = monotonic()
                if rendered_full != serial and now - changed_at >= 0.3:
                    # Recheck snapshot before launching expensive settled work
                    curr_scene, curr_serial, _ = self._snapshot()
                    if curr_serial == serial:
                        if w <= settled_size[0] and h <= settled_size[1]:
                            render_spectral(settled_fbo, settled_size, curr_scene)
                            settled_img = read_frame(settled_fbo, settled_size)
                        else:
                            f_fbo, f_tex = ensure_full_target()
                            render_spectral(f_fbo, full_size, curr_scene)
                            # Downsample color image on GPU before readback
                            GL.glBindFramebuffer(GL.GL_READ_FRAMEBUFFER, f_fbo)
                            GL.glBindFramebuffer(GL.GL_DRAW_FRAMEBUFFER, settled_fbo)
                            GL.glBlitFramebuffer(0, 0, w, h, 0, 0, settled_size[0], settled_size[1],
                                                 GL.GL_COLOR_BUFFER_BIT, GL.GL_LINEAR)
                            settled_img = read_frame(settled_fbo, settled_size)
                        rendered_full = serial
                        current_texture, current_size = settled_texture, settled_size
                        self.events.put(("frame", FramePayload(serial, settled_img, quality=1)))
                        last_frame_event = monotonic()
                        pending_fast = -1

                try:
                    token = self._captures.get_nowait()
                except Empty:
                    pass
                else:
                    f_fbo, f_tex = ensure_full_target()
                    if rendered_full != serial:
                        render_spectral(f_fbo, full_size, scene)
                        rendered_full = serial
                        current_texture, current_size = full_texture, full_size
                    pending_fast = -1
                    self.events.put(("capture", (token, read_frame(f_fbo, full_size))))

                if self.visible:
                    viewport = glfw.get_framebuffer_size(window)
                    if viewport[0] > 0 and viewport[1] > 0:
                        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
                        GL.glViewport(0, 0, *viewport)
                        GL.glUseProgram(display_program)
                        GL.glActiveTexture(GL.GL_TEXTURE2)
                        GL.glBindTexture(GL.GL_TEXTURE_2D, current_texture)
                        GL.glUniform2f(display_uniforms["u_viewport"], *viewport)
                        GL.glUniform2f(display_uniforms["u_image_size"], *current_size)
                        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
                        glfw.swap_buffers(window)
                    remaining = 1.0 / 60.0 - (monotonic() - frame_started)
                    if remaining > 0:
                        sleep(remaining)
                else:
                    self._wake.clear()
                    if pending_fast == serial:
                        wait_time = max(0.0, (last_frame_event + 1.0 / 75.0) - monotonic())
                    elif rendered_full != serial:
                        wait_time = max(0.0, (changed_at + 0.3) - monotonic())
                    else:
                        wait_time = None
                    self._wake.wait(timeout=wait_time)
        finally:
            if window is not None:
                glfw.make_context_current(window)
                if vao:
                    GL.glDeleteVertexArrays(1, [vao])
                if framebuffers:
                    GL.glDeleteFramebuffers(len(framebuffers), framebuffers)
                if textures:
                    GL.glDeleteTextures(textures)
                for program in programs:
                    GL.glDeleteProgram(program)
                glfw.destroy_window(window)
            release_glfw()

