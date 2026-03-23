// Terminal grid vertex/fragment shader.
// Renders background quads and textured glyph quads.

struct Uniforms {
    screen_size: vec2<f32>,
};

@group(0) @binding(0)
var<uniform> uniforms: Uniforms;

@group(0) @binding(1)
var atlas_texture: texture_2d<f32>;

@group(0) @binding(2)
var atlas_sampler: sampler;

@group(0) @binding(3)
var background_texture: texture_2d<f32>;

@group(0) @binding(4)
var background_sampler: sampler;

struct VertexInput {
    @location(0) position: vec2<f32>,
    @location(1) tex_coords: vec2<f32>,
    @location(2) fg_color: vec4<f32>,
    @location(3) bg_color: vec4<f32>,
    @location(4) tex_kind: f32,
};

struct VertexOutput {
    @builtin(position) clip_position: vec4<f32>,
    @location(0) tex_coords: vec2<f32>,
    @location(1) fg_color: vec4<f32>,
    @location(2) bg_color: vec4<f32>,
    @location(3) tex_kind: f32,
};

@vertex
fn vs_main(in: VertexInput) -> VertexOutput {
    var out: VertexOutput;
    // Convert pixel coordinates to clip space [-1, 1]
    let ndc = vec2<f32>(
        (in.position.x / uniforms.screen_size.x) * 2.0 - 1.0,
        1.0 - (in.position.y / uniforms.screen_size.y) * 2.0
    );
    out.clip_position = vec4<f32>(ndc, 0.0, 1.0);
    out.tex_coords = in.tex_coords;
    out.fg_color = in.fg_color;
    out.bg_color = in.bg_color;
    out.tex_kind = in.tex_kind;
    return out;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    if (in.tex_kind < 0.5) {
        return in.bg_color;
    }
    if (in.tex_kind < 1.5) {
        let tex_color = textureSample(atlas_texture, atlas_sampler, in.tex_coords);
        let alpha = tex_color.r * in.fg_color.a;
        return vec4<f32>(in.fg_color.rgb, alpha);
    }

    let bg = textureSample(background_texture, background_sampler, in.tex_coords);
    return vec4<f32>(bg.rgb * in.fg_color.rgb, bg.a * in.fg_color.a);
}
