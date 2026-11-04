/**
 * WebGL2 GLSL ES 3.00 shaders for high-fidelity diffraction optical preview.
 * Ported from dot_ebl_preview.preview.gl_renderer.
 */

export const OPTICS_VERTEX_SHADER = `#version 300 es
precision highp float;

const vec2 corners[3] = vec2[3](
    vec2(-1.0, -1.0),
    vec2(3.0, -1.0),
    vec2(-1.0, 3.0)
);

void main() {
    gl_Position = vec4(corners[gl_VertexID], 0.0, 1.0);
}
`;

export const OPTICS_FRAGMENT_SHADER = `#version 300 es
precision highp float;
precision highp int;
precision highp sampler2D;

#define MAX_LIGHTS 8

uniform sampler2D u_design;
uniform sampler2D u_spectrum;
uniform ivec2 u_size;
uniform ivec2 u_target_size;
uniform float u_pitch_mm;
uniform float u_orientation_deg;
uniform int u_num_lights;
uniform vec3 u_light_pos[MAX_LIGHTS];
uniform vec3 u_camera_pos;
uniform float u_aperture_mm;
uniform float u_source_size_mm[MAX_LIGHTS];
uniform float u_light_intensity[MAX_LIGHTS];
uniform float u_light_y;
uniform vec2 u_white_xy;

uniform int u_num_bands;
uniform float u_start_wavelength_nm;
uniform float u_wavelength_step_nm;
uniform int u_diffraction_orders;

out vec4 pixel_color;

const vec2 red_xy = vec2(0.64, 0.33);
const vec2 green_xy = vec2(0.30, 0.60);
const vec2 blue_xy = vec2(0.15, 0.06);

float cross2(vec2 a, vec2 b) {
    return a.x * b.y - a.y * b.x;
}

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
        dot(vec3(3.2404542, -1.5371385, -0.4985314), xyz),
        dot(vec3(-0.9692660, 1.8760108, 0.0415560), xyz),
        dot(vec3(0.0556434, -0.2040259, 1.0572252), xyz)
    ), 0.0, 1.0);
}

vec3 to_srgb(vec3 linear_rgb) {
    vec3 low = 12.92 * linear_rgb;
    vec3 high = 1.055 * pow(max(linear_rgb, vec3(1.0e-12)), vec3(1.0 / 2.4)) - 0.055;
    return clamp(mix(low, high, greaterThan(linear_rgb, vec3(0.0031308))), 0.0, 1.0);
}

vec3 light_contribution(vec3 light_pos, float source_size_mm, float intensity,
                        vec3 world_pos, vec3 camera, float detector_radius,
                        vec2 grating_vector, float period_nm) {
    if (intensity <= 0.0) return vec3(0.0);

    vec3 light_vector = light_pos - world_pos;
    float light_length = length(light_vector);
    if (light_length < 1.0e-9) return vec3(0.0);
    vec3 light = light_vector / light_length;
    float cos_inc = max(0.0, light.z);
    if (cos_inc <= 0.0) return vec3(0.0);

    float source_radius = max(0.0, source_size_mm) / light_length;
    // Accumulate each source independently; mix physical XYZ before display mapping.
    vec3 light_xyz = vec3(0.0);

    for (int index = 0; index < u_num_bands; ++index) {
        float wavelength_nm = u_start_wavelength_nm + u_wavelength_step_nm * float(index);
        float sigma_diff = 0.5 * wavelength_nm / (u_pitch_mm * 1.0e6);
        float sigma_beam_sq = sigma_diff * sigma_diff + 0.25 * source_radius * source_radius;
        float sigma_sq = sigma_beam_sq + 0.25 * detector_radius * detector_radius;
        if (sigma_sq <= 0.0) continue;
        float ratio_sq = (detector_radius * detector_radius) / max(1.0e-12, sigma_beam_sq);
        float aligned_fraction = 1.0 - exp(-0.5 * ratio_sq);
        vec3 spectrum = texelFetch(u_spectrum, ivec2(index, 0), 0).rgb;

        int start_order = (u_diffraction_orders == 1) ? 1 : -1;
        for (int order = start_order; order <= 1; order += 2) {
            vec2 alpha_xy = -light.xy + float(order) * (wavelength_nm / period_nm) * grating_vector;
            float alpha12 = dot(alpha_xy, alpha_xy);
            if (alpha12 > 1.0) continue;
            float alpha_z = sqrt(max(0.0, 1.0 - alpha12));
            vec3 alpha = vec3(alpha_xy, alpha_z);
            float theta = acos(clamp(dot(alpha, camera), -1.0, 1.0));
            float angular_weight = aligned_fraction * exp(-0.5 * theta * theta / sigma_sq);
            light_xyz += spectrum * (intensity * cos_inc * alpha_z * angular_weight);
        }
    }
    return light_xyz;
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

    // Inactive cells: output stored fallback grayscale without gamma
    if (cell.z < 0.5 || period_nm <= 0.0) {
        pixel_color = vec4(vec3(cell.w), 1.0);
        return;
    }

    vec3 world_pos = vec3(
        (float(output_coord.x) + 0.5 - float(u_size.x) * 0.5) * u_pitch_mm,
        -(float(row) + 0.5 - float(u_size.y) * 0.5) * u_pitch_mm,
        0.0
    );

    vec3 camera_vector = u_camera_pos - world_pos;
    float camera_length = length(camera_vector);
    if (camera_length < 1.0e-9 || camera_vector.z <= 0.0) {
        pixel_color = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }
    vec3 camera = camera_vector / camera_length;

    float angle = radians(cell.y + u_orientation_deg);
    vec2 grating_vector = vec2(-sin(angle), cos(angle));
    float detector_radius = max(0.0, u_aperture_mm) / camera_length;
    vec3 xyz = vec3(0.0);

    // Constant array indices avoid driver-dependent dynamic indexing in nested loops.
    if (u_num_lights > 0) xyz += light_contribution(u_light_pos[0], u_source_size_mm[0], u_light_intensity[0],
        world_pos, camera, detector_radius, grating_vector, period_nm);
    if (u_num_lights > 1) xyz += light_contribution(u_light_pos[1], u_source_size_mm[1], u_light_intensity[1],
        world_pos, camera, detector_radius, grating_vector, period_nm);
    if (u_num_lights > 2) xyz += light_contribution(u_light_pos[2], u_source_size_mm[2], u_light_intensity[2],
        world_pos, camera, detector_radius, grating_vector, period_nm);
    if (u_num_lights > 3) xyz += light_contribution(u_light_pos[3], u_source_size_mm[3], u_light_intensity[3],
        world_pos, camera, detector_radius, grating_vector, period_nm);
    if (u_num_lights > 4) xyz += light_contribution(u_light_pos[4], u_source_size_mm[4], u_light_intensity[4],
        world_pos, camera, detector_radius, grating_vector, period_nm);
    if (u_num_lights > 5) xyz += light_contribution(u_light_pos[5], u_source_size_mm[5], u_light_intensity[5],
        world_pos, camera, detector_radius, grating_vector, period_nm);
    if (u_num_lights > 6) xyz += light_contribution(u_light_pos[6], u_source_size_mm[6], u_light_intensity[6],
        world_pos, camera, detector_radius, grating_vector, period_nm);
    if (u_num_lights > 7) xyz += light_contribution(u_light_pos[7], u_source_size_mm[7], u_light_intensity[7],
        world_pos, camera, detector_radius, grating_vector, period_nm);

    xyz /= u_light_y;
    if (xyz.x + xyz.y + xyz.z < 1.0e-9) {
        pixel_color = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }

    pixel_color = vec4(to_srgb(to_linear_rgb(gamut_map(xyz))), 1.0);
}
`;
