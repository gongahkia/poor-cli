use crate::layout::engine::*;
use std::collections::HashMap;

const LANE_HEIGHT: f64 = 40.0;
const MARGIN_TOP: f64 = 60.0;
const MARGIN_LEFT: f64 = 20.0;
const BAR_HEIGHT: f64 = 24.0;
const FONT_SIZE: f64 = 12.0;

/// Color theme (Task 68)
#[derive(Debug, Clone)]
pub struct Theme {
    pub bg: String,
    pub text: String,
    pub axis: String,
    pub entity_colors: HashMap<String, String>,
    pub rel_colors: HashMap<String, String>,
    pub selection: String,
    pub timeline_bg: String,
}

impl Default for Theme {
    fn default() -> Self {
        let mut ec = HashMap::new();
        ec.insert("character".into(), "#4a9eff".into());
        ec.insert("event".into(), "#ff4a4a".into());
        ec.insert("location".into(), "#4aff4a".into());
        ec.insert("artifact".into(), "#ff4aff".into());
        ec.insert("org".into(), "#4affff".into());

        Self {
            bg: "#1a1a2e".into(),
            text: "#e0e0e0".into(),
            axis: "#666666".into(),
            entity_colors: ec,
            rel_colors: HashMap::new(),
            selection: "#ffcc00".into(),
            timeline_bg: "#16213e".into(),
        }
    }
}

/// Convert Layout to SVG string (Task 65)
pub fn render_svg(layout: &Layout, theme: &Theme) -> String {
    let vp = &layout.viewport;
    let time_range = vp.time_end - vp.time_start;
    if time_range <= 0.0 {
        return String::from("<svg xmlns='http://www.w3.org/2000/svg'></svg>");
    }

    let svg_width = 1200.0_f64;
    let svg_height = MARGIN_TOP + (layout.total_lanes as f64) * LANE_HEIGHT + 40.0;
    let scale_x = (svg_width - MARGIN_LEFT * 2.0) / time_range;

    let mut svg = format!(
        r#"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {} {}" width="{}" height="{}">"#,
        svg_width, svg_height, svg_width, svg_height
    );

    // Background (Task 68)
    svg.push_str(&format!(
        r#"<rect width="{}" height="{}" fill="{}"/>"#,
        svg_width, svg_height, theme.bg
    ));

    // Defs for arrowheads (Task 66)
    svg.push_str("<defs><marker id=\"arrow\" markerWidth=\"10\" markerHeight=\"7\" refX=\"10\" refY=\"3.5\" orient=\"auto\"><polygon points=\"0 0, 10 3.5, 0 7\" fill=\"#ff4aff\"/></marker></defs>");

    // Timeline regions
    for tl in &layout.timelines {
        let x = MARGIN_LEFT + (tl.x_start - vp.time_start) * scale_x;
        let y = MARGIN_TOP + tl.lane_start as f64 * LANE_HEIGHT - 5.0;
        let w = (tl.x_end - tl.x_start) * scale_x;
        let h = (tl.lane_end - tl.lane_start).max(1) as f64 * LANE_HEIGHT + 10.0;

        svg.push_str(&format!(
            r#"<rect x="{:.1}" y="{:.1}" width="{:.1}" height="{:.1}" rx="4" fill="{}" opacity="0.3"/>"#,
            x, y, w, h, theme.timeline_bg
        ));

        // Loop indicator (Task 43 visual)
        let label = if tl.is_loop {
            format!("{} ↻×{}", tl.name, tl.loop_count.unwrap_or(1))
        } else {
            tl.name.clone()
        };
        svg.push_str(&format!(
            r#"<text x="{:.1}" y="{:.1}" fill="{}" font-size="{}" font-weight="bold">{}</text>"#,
            x + 4.0, y + 14.0, theme.text, FONT_SIZE, escape_xml(&label)
        ));
    }

    // Time axis ticks
    for tick in &layout.ticks {
        let x = MARGIN_LEFT + (tick.x - vp.time_start) * scale_x;
        if x >= MARGIN_LEFT && x <= svg_width - MARGIN_LEFT {
            svg.push_str(&format!(
                r#"<line x1="{:.1}" y1="{}" x2="{:.1}" y2="{:.1}" stroke="{}" stroke-width="0.5" opacity="0.3"/>"#,
                x, MARGIN_TOP - 20.0, x, svg_height - 20.0, theme.axis
            ));
            svg.push_str(&format!(
                r#"<text x="{:.1}" y="{}" fill="{}" font-size="{}" text-anchor="middle">{}</text>"#,
                x, MARGIN_TOP - 25.0, theme.axis, FONT_SIZE - 2.0, escape_xml(&tick.label)
            ));
        }
    }

    // Entity bars as rounded rects (Task 65)
    for ent in &layout.entities {
        let x = MARGIN_LEFT + (ent.x_start - vp.time_start) * scale_x;
        let y = MARGIN_TOP + ent.lane as f64 * LANE_HEIGHT;
        let w = ((ent.x_end - ent.x_start) * scale_x).max(8.0);
        let color = theme.entity_colors.get(&ent.entity_type)
            .cloned()
            .unwrap_or_else(|| "#888888".into());

        svg.push_str(&format!(
            r#"<rect x="{:.1}" y="{:.1}" width="{:.1}" height="{}" rx="4" fill="{}" opacity="0.85"/>"#,
            x, y, w, BAR_HEIGHT, color
        ));

        // Label placement (Task 67)
        let label_x = x + w + 4.0;
        let label_y = y + BAR_HEIGHT / 2.0 + 4.0;
        let label = if w / FONT_SIZE < ent.name.len() as f64 {
            truncate_with_ellipsis(&ent.name, (w / FONT_SIZE * 1.5) as usize)
        } else {
            ent.name.clone()
        };

        svg.push_str(&format!(
            r#"<text x="{:.1}" y="{:.1}" fill="{}" font-size="{}" dominant-baseline="middle">{}</text>"#,
            label_x, label_y, theme.text, FONT_SIZE, escape_xml(&label)
        ));
    }

    // Relationship edges as SVG paths (Task 66)
    for edge in &layout.edges {
        let src_y = MARGIN_TOP + edge.source_lane as f64 * LANE_HEIGHT + BAR_HEIGHT / 2.0;
        let tgt_y = MARGIN_TOP + edge.target_lane as f64 * LANE_HEIGHT + BAR_HEIGHT / 2.0;
        let src_x = MARGIN_LEFT + (edge.source_x - vp.time_start) * scale_x;
        let tgt_x = MARGIN_LEFT + (edge.target_x - vp.time_start) * scale_x;

        let color = theme.rel_colors.get(&edge.label)
            .cloned()
            .unwrap_or_else(|| "#ff4aff".into());

        // Spline routing (Task 45 visual)
        let mid_x = (src_x + tgt_x) / 2.0;
        let ctrl_offset = (tgt_y - src_y).abs() * 0.3;
        let path = format!(
            "M {:.1},{:.1} C {:.1},{:.1} {:.1},{:.1} {:.1},{:.1}",
            src_x, src_y,
            mid_x - ctrl_offset, src_y,
            mid_x + ctrl_offset, tgt_y,
            tgt_x, tgt_y
        );

        let marker = if edge.directed { r#" marker-end="url(#arrow)""# } else { "" };
        svg.push_str(&format!(
            r#"<path d="{}" stroke="{}" stroke-width="1.5" fill="none" opacity="0.7"{}"/>"#,
            path, color, marker
        ));

        // Edge label at midpoint
        if !edge.label.is_empty() {
            svg.push_str(&format!(
                r#"<text x="{:.1}" y="{:.1}" fill="{}" font-size="{}" text-anchor="middle" opacity="0.8">{}</text>"#,
                mid_x, (src_y + tgt_y) / 2.0 - 4.0, color, FONT_SIZE - 2.0, escape_xml(&edge.label)
            ));
        }
    }

    // Branch/merge connectors
    for conn in &layout.connectors {
        let from_x = MARGIN_LEFT + (conn.from_x - vp.time_start) * scale_x;
        let from_y = MARGIN_TOP + conn.from_lane as f64 * LANE_HEIGHT + BAR_HEIGHT / 2.0;
        let to_y = MARGIN_TOP + conn.to_lane as f64 * LANE_HEIGHT + BAR_HEIGHT / 2.0;

        let color = match conn.kind {
            ConnectorKind::Fork => "#4aff4a",
            ConnectorKind::Merge => "#ffcc00",
        };

        svg.push_str(&format!(
            r#"<line x1="{:.1}" y1="{:.1}" x2="{:.1}" y2="{:.1}" stroke="{}" stroke-width="2" stroke-dasharray="4,2"/>"#,
            from_x, from_y, from_x, to_y, color
        ));
    }

    svg.push_str("</svg>");
    svg
}

fn escape_xml(s: &str) -> String {
    s.replace('&', "&amp;")
     .replace('<', "&lt;")
     .replace('>', "&gt;")
     .replace('"', "&quot;")
}

fn truncate_with_ellipsis(s: &str, max_len: usize) -> String {
    if s.len() <= max_len { return s.to_string(); }
    if max_len <= 3 { return "...".to_string(); }
    format!("{}...", &s[..max_len - 3])
}
