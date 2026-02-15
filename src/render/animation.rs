use crate::layout::engine::Layout;
use crate::render::svg_render::{render_svg, Theme};

/// Animation export: render time scrubber as animated SVG with SMIL (Task 58)
pub fn render_animated_svg(layout: &Layout, theme: &Theme, frames: usize) -> String {
    let time_range = layout.viewport.time_end - layout.viewport.time_start;
    if time_range <= 0.0 || frames == 0 {
        return render_svg(layout, theme);
    }

    let base_svg = render_svg(layout, theme);

    // Wrap the base SVG with SMIL animation for entity visibility
    let mut output = String::new();
    let total_width = layout.total_width.max(800.0);
    let total_height = (layout.total_lanes as f64) * 40.0;

    output.push_str(&format!(
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{}\" height=\"{}\" viewBox=\"0 0 {} {}\">\n",
        total_width, total_height + 40.0, total_width, total_height + 40.0
    ));

    // Background
    output.push_str(&format!(
        "<rect width=\"100%\" height=\"100%\" fill=\"{}\"/>\n",
        theme.bg
    ));

    // CSS animation fallback (browsers that lack SMIL support)
    let dur = frames as f64 / 10.0;
    output.push_str("<style>\n");
    output.push_str(&format!(
        "@keyframes cursor-sweep {{ from {{ transform: translateX(0); }} to {{ transform: translateX({}px); }} }}\n",
        total_width
    ));
    output.push_str(&format!(
        ".anim-cursor {{ animation: cursor-sweep {}s linear infinite; }}\n",
        dur
    ));
    for (i, ent) in layout.entities.iter().enumerate() {
        let x_start = ent.x_start - layout.viewport.time_start;
        let x_end = ent.x_end - layout.viewport.time_start;
        let begin_pct = (x_start / time_range * 100.0).max(0.0);
        let end_pct = (x_end / time_range * 100.0).min(100.0);
        let p0 = ((begin_pct - 5.0).max(0.0)) as u32;
        let p1 = begin_pct as u32;
        let p2 = end_pct as u32;
        let p3 = ((end_pct + 5.0).min(100.0)) as u32;
        output.push_str(&format!(
            "@keyframes ent-{} {{ 0%,{}% {{ opacity:0.1; }} {}% {{ opacity:1; }} {}% {{ opacity:1; }} {}%,100% {{ opacity:0.3; }} }}\n",
            i, p0, p1, p2, p3
        ));
        output.push_str(&format!(
            ".anim-ent-{} {{ animation: ent-{} {}s linear infinite; }}\n",
            i, i, dur
        ));
    }
    output.push_str("</style>\n");

    // Time cursor line with animation (SMIL + CSS fallback)
    output.push_str("<line class=\"anim-cursor\" x1=\"0\" y1=\"0\" x2=\"0\" y2=\"100%\" stroke=\"#ff0\" stroke-width=\"2\" opacity=\"0.7\">\n");
    output.push_str(&format!(
        "  <animate attributeName=\"x1\" from=\"0\" to=\"{}\" dur=\"{}s\" repeatCount=\"indefinite\"/>\n",
        total_width, dur
    ));
    output.push_str(&format!(
        "  <animate attributeName=\"x2\" from=\"0\" to=\"{}\" dur=\"{}s\" repeatCount=\"indefinite\"/>\n",
        total_width, dur
    ));
    output.push_str("</line>\n");

    // Entity bars with fade animation based on temporal position
    for (i, ent) in layout.entities.iter().enumerate() {
        let x_start = ent.x_start - layout.viewport.time_start;
        let x_end = ent.x_end - layout.viewport.time_start;
        let x = (x_start / time_range * total_width).max(0.0);
        let w = ((x_end - x_start) / time_range * total_width).max(1.0);
        let y = ent.lane as f64 * 40.0;

        let begin_pct = (x_start / time_range * 100.0).max(0.0);
        let end_pct = (x_end / time_range * 100.0).min(100.0);

        let entity_fill = theme
            .entity_colors
            .get(&ent.entity_type)
            .map(|s| s.as_str())
            .unwrap_or("#4a9eff");

        output.push_str(&format!(
            "<g class=\"anim-ent-{}\">\n  <rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"30\" rx=\"4\" fill=\"{}\" opacity=\"0.3\">\n",
            i, x, y, w, entity_fill
        ));
        // Fade in at appearance, fade out after
        output.push_str(&format!(
            "    <animate attributeName=\"opacity\" values=\"0.1;0.1;1;1;0.3;0.3\" keyTimes=\"0;{};{};{};{};1\" dur=\"{}s\" repeatCount=\"indefinite\"/>\n",
            (begin_pct - 5.0).max(0.0) / 100.0,
            begin_pct / 100.0,
            end_pct / 100.0,
            (end_pct + 5.0).min(100.0) / 100.0,
            dur
        ));
        output.push_str("  </rect>\n");
        output.push_str(&format!(
            "  <text x=\"{}\" y=\"{}\" font-size=\"12\" fill=\"{}\">{}</text>\n",
            x + 4.0,
            y + 20.0,
            theme.text,
            ent.name
        ));
        output.push_str("</g>\n");
    }

    // Time axis label
    output.push_str(&format!(
        "<text x=\"10\" y=\"{}\" font-size=\"10\" fill=\"#888\">",
        total_height + 25.0
    ));
    output.push_str("Time →</text>\n");

    output.push_str("</svg>\n");
    output
}
