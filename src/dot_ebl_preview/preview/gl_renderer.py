"""Offscreen OpenGL 3.3 diffraction preview, adapted from the original GLSL model.

The fragment shader evaluates one physical design cell per output pixel. This avoids
the original four-vertex-per-cell mesh and transfers only canonical period, angle,
activity, and optional fallback data to the GPU. The CPU renderer remains the
reference implementation for headless workflows and comparison.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from dot_ebl_preview.core.model import Design
from dot_ebl_preview.optics.presets import get_optical_preset
from dot_ebl_preview.optics.tables import premultiplied_XYZ


VERTEX_SHADER = """#version 330 core
const vec2 corners[3] = vec2[3](vec2(-1.0, -1.0), vec2(3.0, -1.0), vec2(-1.0, 3.0));
void main() { gl_Position = vec4(corners[gl_VertexID], 0.0, 1.0); }
"""


FRAGMENT_SHADER = """#version 330 core
uniform sampler2D u_design;
uniform sampler1D u_spectrum;
uniform ivec2 u_size;
uniform ivec2 u_target_size;
uniform float u_pitch_mm;
uniform float u_orientation_deg;
uniform vec3 u_light_pos;
uniform vec3 u_camera_pos;
uniform float u_aperture_mm;
uniform float u_light_y;
uniform vec2 u_white_xy;
out vec4 pixel_color;

const vec2 red_xy = vec2(0.64, 0.33);
const vec2 green_xy = vec2(0.30, 0.60);
const vec2 blue_xy = vec2(0.15, 0.06);

float cross2(vec2 a, vec2 b) { return a.x * b.y - a.y * b.x; }

bool inside_triangle(vec2 point, vec2 a, vec2 b, vec2 c) {
    bool side = cross2(b - a, point - a) > 0.0;
    if ((cross2(c - a, point - a) > 0.0) == side) return false;
    if ((cross2(c - b, point - b) > 0.0) != side) return false;
    return true;
}

vec2 intersection(vec2 p1, vec2 p2, vec2 p3, vec2 p4) {
    vec2 r = p2 - p1;
    vec2 s = p4 - p3;
    float denominator = cross2(r, s);
    if (abs(denominator) < 1.0e-12) return p1;
    return p1 + r * (cross2(p3 - p1, s) / denominator);
}

vec3 gamut_map(vec3 xyz) {
    float total = xyz.x + xyz.y + xyz.z;
    if (total < 1.0e-9) return vec3(0.0);
    vec2 chroma = xyz.xy / total;
    if (!inside_triangle(chroma, red_xy, blue_xy, green_xy)) {
        vec2 candidates[3];
        candidates[0] = mix(u_white_xy, intersection(chroma, u_white_xy, blue_xy, green_xy), 0.99);
        candidates[1] = mix(u_white_xy, intersection(chroma, u_white_xy, green_xy, red_xy), 0.99);
        candidates[2] = mix(u_white_xy, intersection(chroma, u_white_xy, red_xy, blue_xy), 0.99);
        float closest = 1.0e7;
        vec2 selected = u_white_xy;
        for (int i = 0; i < 3; ++i) {
            float distance_to = distance(chroma, candidates[i]);
            if (distance_to < closest && inside_triangle(candidates[i], red_xy, blue_xy, green_xy)) {
                closest = distance_to;
                selected = candidates[i];
            }
        }
        if (selected.y > 1.0e-9) {
            xyz.x = xyz.y * selected.x / selected.y;
            xyz.z = xyz.y * (1.0 - selected.x - selected.y) / selected.y;
        }
    }
    return xyz;
}

vec3 to_linear_rgb(vec3 xyz) {
    return clamp(vec3(
        dot(vec3(3.2404542, -0.9692660, 0.0556434), xyz),
        dot(vec3(-1.5371385, 1.8760108, -0.2040259), xyz),
        dot(vec3(-0.4985314, 0.0415560, 1.0572252), xyz)), 0.0, 1.0);
}

vec3 to_srgb(vec3 linear_rgb) {
    vec3 low = 12.92 * linear_rgb;
    vec3 high = 1.055 * pow(max(linear_rgb, vec3(1.0e-12)), vec3(1.0 / 2.4)) - 0.055;
    return clamp(mix(low, high, greaterThan(linear_rgb, vec3(0.0031308))), 0.0, 1.0);
}

void main() {
    float scale = min(float(u_target_size.x) / float(u_size.x), float(u_target_size.y) / float(u_size.y));
    vec2 image_span = vec2(u_size) * scale;
    vec2 origin = (vec2(u_target_size) - image_span) * 0.5;
    vec2 design_coord = (gl_FragCoord.xy - origin) / scale;
    if (design_coord.x < 0.0 || design_coord.y < 0.0 ||
        design_coord.x >= float(u_size.x) || design_coord.y >= float(u_size.y)) {
        pixel_color = vec4(0.07, 0.09, 0.13, 1.0);
        return;
    }
    ivec2 output_coord = clamp(ivec2(design_coord), ivec2(0), u_size - ivec2(1));
    int row = u_size.y - 1 - output_coord.y;
    vec4 cell = texelFetch(u_design, ivec2(output_coord.x, row), 0);
    float period_nm = cell.x;
    if (cell.z < 0.5 || period_nm <= 0.0) {
        pixel_color = vec4(vec3(cell.w), 1.0);
        return;
    }

    vec3 world_pos = vec3(
        (float(output_coord.x) + 0.5 - float(u_size.x) * 0.5) * u_pitch_mm,
        -(float(row) + 0.5 - float(u_size.y) * 0.5) * u_pitch_mm, 0.0);
    vec3 light_vector = u_light_pos - world_pos;
    vec3 camera_vector = u_camera_pos - world_pos;
    float light_length = length(light_vector);
    float camera_length = length(camera_vector);
    if (light_length < 1.0e-9 || camera_length < 1.0e-9) {
        pixel_color = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }
    vec3 unit_light = light_vector / light_length;
    vec3 unit_cam = camera_vector / camera_length;

    float radius = max(0.0, u_aperture_mm) / camera_length;

    vec3 unit_normal = vec3(0.0, 0.0, 1.0);
    vec2 actual_light = unit_light.xy + unit_normal.xy;
    vec2 actual_cam_xy = unit_cam.xy + unit_normal.xy;
    float actual_cam_z_sq = max(0.0, 1.0 - dot(actual_cam_xy, actual_cam_xy));
    vec3 actual_cam = vec3(actual_cam_xy, sqrt(actual_cam_z_sq));

    float angle_rad = radians(cell.y + u_orientation_deg);
    vec2 grating_vec = vec2(sin(angle_rad), cos(angle_rad));
    float period_m = period_nm * 1.0e-9;
    float s_factor = grating_vec.x / period_m;
    float c_factor = grating_vec.y / period_m;

    vec3 xyz = vec3(0.0);

    for (int index = 0; index < 77; ++index) {
        float wl_m = (380.0 + 5.0 * float(index)) * 1.0e-9;
        vec3 spectrum = texelFetch(u_spectrum, index, 0).rgb;

        for (int order = -1; order <= 1; order += 2) {
            float m = float(order);
            vec2 alpha_xy = vec2(m * wl_m * s_factor - actual_light.x, -m * wl_m * c_factor - actual_light.y);
            float alpha12 = dot(alpha_xy, alpha_xy);
            if (alpha12 >= 1.0) continue;
            float alpha_z = sqrt(1.0 - alpha12);
            vec3 alpha = vec3(alpha_xy, alpha_z);
            if (distance(actual_cam, alpha) <= radius) {
                xyz += spectrum;
            }
        }
    }

    xyz /= u_light_y;
    if (xyz.x + xyz.y + xyz.z < 1.0e-9) {
        pixel_color = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }
    pixel_color = vec4(to_srgb(to_linear_rgb(gamut_map(xyz))), 1.0);
}
"""


import threading

_tls = threading.local()
_glfw_lock = threading.Lock()
_glfw_refcount = 0


def retain_glfw() -> None:
    """Retain GLFW initialization count."""
    global _glfw_refcount
    import glfw

    with _glfw_lock:
        if _glfw_refcount == 0:
            if not glfw.init():
                raise RuntimeError("OpenGL could not initialize. Select CPU reference in the preview renderer control.")
        _glfw_refcount += 1


def release_glfw() -> None:
    """Release GLFW initialization count, terminating only when no users remain."""
    global _glfw_refcount
    import glfw

    with _glfw_lock:
        _glfw_refcount = max(0, _glfw_refcount - 1)
        if _glfw_refcount == 0:
            try:
                glfw.terminate()
            except Exception:
                pass


class ReusableGLRenderer:
    """Persistent offscreen OpenGL renderer that reuses context, shaders, and design textures."""

    def __init__(self) -> None:
        import glfw
        from OpenGL import GL
        from OpenGL.GL import shaders

        retain_glfw()
        self._retained = True
        glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        self.window = glfw.create_window(16, 16, "Dot EBL offscreen preview", None, None)
        if not self.window:
            raise RuntimeError("OpenGL 3.3 context is unavailable. Select CPU reference in the preview renderer control.")
        glfw.make_context_current(self.window)

        self.program = shaders.compileProgram(
            shaders.compileShader(VERTEX_SHADER, GL.GL_VERTEX_SHADER),
            shaders.compileShader(FRAGMENT_SHADER, GL.GL_FRAGMENT_SHADER),
        )
        self.vertex_array = int(GL.glGenVertexArrays(1))
        self.data_texture, self.spectrum_texture, self.color_texture = [int(v) for v in GL.glGenTextures(3)]
        self.framebuffer = int(GL.glGenFramebuffers(1))

        self.uniforms = {
            name: GL.glGetUniformLocation(self.program, name)
            for name in (
                "u_design", "u_spectrum", "u_size", "u_target_size", "u_pitch_mm",
                "u_orientation_deg", "u_light_pos", "u_camera_pos", "u_aperture_mm",
                "u_light_y", "u_white_xy",
            )
        }

        spectrum = np.ascontiguousarray(premultiplied_XYZ(), dtype=np.float32)
        self.light_xyz = spectrum.sum(axis=0, dtype=np.float64)
        self.white_xy = self.light_xyz[:2] / self.light_xyz.sum()

        GL.glActiveTexture(GL.GL_TEXTURE1)
        GL.glBindTexture(GL.GL_TEXTURE_1D, self.spectrum_texture)
        GL.glTexParameteri(GL.GL_TEXTURE_1D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
        GL.glTexParameteri(GL.GL_TEXTURE_1D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
        GL.glTexImage1D(GL.GL_TEXTURE_1D, 0, GL.GL_RGB32F, 77, 0, GL.GL_RGB, GL.GL_FLOAT, spectrum)

        self.design_hash: str | None = None
        self.design_shape: tuple[int, int] | None = None
        self.target_size: tuple[int, int] | None = None
        self.closed = False

    def render(self, design: Design, light_pos: tuple[float, float, float],
               camera_pos: tuple[float, float, float], orientation_deg: float = 0.0) -> Image.Image:
        import glfw
        from OpenGL import GL

        if self.closed:
            raise RuntimeError("Renderer is closed.")

        glfw.make_context_current(self.window)
        h, w = design.shape
        max_texture = int(GL.glGetIntegerv(GL.GL_MAX_TEXTURE_SIZE))
        max_target = int(GL.glGetIntegerv(GL.GL_MAX_RENDERBUFFER_SIZE))
        limit = min(max_texture, max_target)
        if w > limit or h > limit:
            raise RuntimeError(f"Design {w}×{h} exceeds this GPU's render target limit of {limit} pixels per axis.")

        curr_hash = design.content_hash()
        if curr_hash != self.design_hash or self.design_shape != (h, w):
            packed = np.empty((h, w, 4), dtype=np.float32)
            packed[:, :, 0] = design.period_nm
            packed[:, :, 1] = design.angle_deg
            packed[:, :, 2] = design.active
            packed[:, :, 3] = design.fallback_intensity if design.fallback_intensity is not None else 0.0
            packed = np.ascontiguousarray(packed)

            GL.glActiveTexture(GL.GL_TEXTURE0)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self.data_texture)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
            GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA32F, w, h, 0, GL.GL_RGBA, GL.GL_FLOAT, packed)
            self.design_hash = curr_hash
            self.design_shape = (h, w)

        if self.target_size != (w, h):
            GL.glBindTexture(GL.GL_TEXTURE_2D, self.color_texture)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
            GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, w, h, 0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, None)

            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.framebuffer)
            GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0, GL.GL_TEXTURE_2D, self.color_texture, 0)
            if GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER) != GL.GL_FRAMEBUFFER_COMPLETE:
                raise RuntimeError("OpenGL could not create the preview render target.")
            self.target_size = (w, h)

        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.framebuffer)
        GL.glBindVertexArray(self.vertex_array)
        GL.glViewport(0, 0, w, h)
        GL.glDisable(GL.GL_FRAMEBUFFER_SRGB)
        GL.glUseProgram(self.program)

        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.data_texture)
        GL.glActiveTexture(GL.GL_TEXTURE1)
        GL.glBindTexture(GL.GL_TEXTURE_1D, self.spectrum_texture)

        GL.glUniform1i(self.uniforms["u_design"], 0)
        GL.glUniform1i(self.uniforms["u_spectrum"], 1)
        GL.glUniform2i(self.uniforms["u_size"], w, h)
        GL.glUniform2i(self.uniforms["u_target_size"], w, h)
        GL.glUniform1f(self.uniforms["u_pitch_mm"], design.pitch_nm * 1.0e-6)
        GL.glUniform1f(self.uniforms["u_orientation_deg"], orientation_deg)
        GL.glUniform3f(self.uniforms["u_light_pos"], *light_pos)
        GL.glUniform3f(self.uniforms["u_camera_pos"], *camera_pos)
        GL.glUniform1f(self.uniforms["u_aperture_mm"], get_optical_preset("corrected").aperture_radius_factor)
        GL.glUniform1f(self.uniforms["u_light_y"], float(self.light_xyz[1]))
        GL.glUniform2f(self.uniforms["u_white_xy"], *self.white_xy)

        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
        raw = GL.glReadPixels(0, 0, w, h, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE)
        rgba = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 4)
        rgb = np.ascontiguousarray(rgba[::-1, :, :3])
        return Image.fromarray(rgb, mode="RGB")

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        import glfw
        from OpenGL import GL

        if self.window is not None:
            try:
                glfw.make_context_current(self.window)
                if self.vertex_array:
                    GL.glDeleteVertexArrays(1, [self.vertex_array])
                if self.framebuffer:
                    GL.glDeleteFramebuffers(1, [self.framebuffer])
                textures = [self.data_texture, self.spectrum_texture, self.color_texture]
                GL.glDeleteTextures(textures)
                if self.program:
                    GL.glDeleteProgram(self.program)
                glfw.destroy_window(self.window)
            except Exception:
                pass
            self.window = None
        if getattr(self, "_retained", False):
            self._retained = False
            release_glfw()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


def get_thread_renderer() -> ReusableGLRenderer:
    renderer = getattr(_tls, "renderer", None)
    if renderer is None or renderer.closed:
        renderer = ReusableGLRenderer()
        _tls.renderer = renderer
    return renderer


def render_opengl_preview(design: Design, light_pos: tuple[float, float, float],
                          camera_pos: tuple[float, float, float], orientation_deg: float = 0.0) -> Image.Image:
    """Render the corrected spectral preview using a reusable hidden OpenGL context."""
    renderer = get_thread_renderer()
    return renderer.render(design, light_pos, camera_pos, orientation_deg)
