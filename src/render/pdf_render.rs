use crate::layout::engine::*;
use crate::render::svg_render::Theme;
use printpdf::*;
use std::path::Path;

const PDF_LANE_HEIGHT: f32 = 10.0; // mm
const PDF_MARGIN: f32 = 15.0;
const PDF_BAR_HEIGHT: f32 = 6.0;
const PDF_FONT_SIZE: f32 = 8.0;

/// Render layout to vector PDF using printpdf drawing primitives (Task 13)
pub fn render_pdf(
    svg_data: &str,
    output: &Path,
    width_mm: f32,
    height_mm: f32,
) -> Result<(), String> {
    // Fallback: still parse SVG tree for basic rasterized export
    render_pdf_raster(svg_data, output, width_mm, height_mm)
}

/// Render layout directly to vector PDF with line/rect/text primitives
pub fn render_pdf_vector(
    layout: &Layout,
    theme: &Theme,
    output: &Path,
    width_mm: f32,
    height_mm: f32,
) -> Result<(), String> {
    let (doc, page1, layer1) =
        PdfDocument::new("Seuss Timeline", Mm(width_mm), Mm(height_mm), "Timeline");
    let current_layer = doc.get_page(page1).get_layer(layer1);
    let font = doc
        .add_builtin_font(BuiltinFont::Helvetica)
        .map_err(|e| format!("font error: {}", e))?;

    let vp = &layout.viewport;
    let time_range = vp.time_end - vp.time_start;
    if time_range <= 0.0 {
        return Err("empty time range".into());
    }

    let usable_w = width_mm - PDF_MARGIN * 2.0;
    let scale_x = usable_w as f64 / time_range;

    // Draw timeline regions
    for tl in &layout.timelines {
        let x = PDF_MARGIN as f64 + (tl.x_start - vp.time_start) * scale_x;
        let y_top =
            height_mm as f64 - PDF_MARGIN as f64 - (tl.lane_start as f64 * PDF_LANE_HEIGHT as f64);
        let w = (tl.x_end - tl.x_start) * scale_x;
        let h = (tl.lane_end - tl.lane_start).max(1) as f64 * PDF_LANE_HEIGHT as f64;

        let rect_points = vec![
            (Point::new(Mm(x as f32), Mm(y_top as f32)), false),
            (Point::new(Mm((x + w) as f32), Mm(y_top as f32)), false),
            (
                Point::new(Mm((x + w) as f32), Mm((y_top - h) as f32)),
                false,
            ),
            (Point::new(Mm(x as f32), Mm((y_top - h) as f32)), false),
        ];
        let line = Line {
            points: rect_points,
            is_closed: true,
            ..Default::default()
        };
        current_layer.set_fill_color(Color::Rgb(Rgb::new(0.09, 0.13, 0.24, None)));
        current_layer.set_outline_color(Color::Rgb(Rgb::new(0.3, 0.3, 0.3, None)));
        current_layer.add_line(line);

        // Timeline label
        current_layer.use_text(
            &tl.name,
            PDF_FONT_SIZE,
            Mm(x as f32 + 1.0),
            Mm(y_top as f32 - 3.0),
            &font,
        );
    }

    // Draw entity bars
    for ent in &layout.entities {
        let x = PDF_MARGIN as f64 + (ent.x_start - vp.time_start) * scale_x;
        let y_top =
            height_mm as f64 - PDF_MARGIN as f64 - (ent.lane as f64 * PDF_LANE_HEIGHT as f64);
        let w = ((ent.x_end - ent.x_start) * scale_x).max(2.0);

        let (r, g, b) = parse_hex_color(
            theme
                .entity_colors
                .get(&ent.entity_type)
                .map(|s| s.as_str())
                .unwrap_or("#888888"),
        );
        current_layer.set_fill_color(Color::Rgb(Rgb::new(r, g, b, None)));

        let rect_points = vec![
            (Point::new(Mm(x as f32), Mm(y_top as f32)), false),
            (Point::new(Mm((x + w) as f32), Mm(y_top as f32)), false),
            (
                Point::new(Mm((x + w) as f32), Mm((y_top as f32) - PDF_BAR_HEIGHT)),
                false,
            ),
            (
                Point::new(Mm(x as f32), Mm((y_top as f32) - PDF_BAR_HEIGHT)),
                false,
            ),
        ];
        let line = Line {
            points: rect_points,
            is_closed: true,
            ..Default::default()
        };
        current_layer.add_line(line);

        // Entity label
        current_layer.set_fill_color(Color::Rgb(Rgb::new(0.9, 0.9, 0.9, None)));
        let label_x = (x + w + 1.0) as f32;
        let label_y = y_top as f32 - PDF_BAR_HEIGHT / 2.0 - 1.0;
        let label = if ent.name.len() > 25 {
            format!("{}...", &ent.name[..22])
        } else {
            ent.name.clone()
        };
        current_layer.use_text(&label, PDF_FONT_SIZE - 1.0, Mm(label_x), Mm(label_y), &font);
    }

    // Draw relationship edges
    for edge in &layout.edges {
        let src_x = PDF_MARGIN as f64 + (edge.source_x - vp.time_start) * scale_x;
        let tgt_x = PDF_MARGIN as f64 + (edge.target_x - vp.time_start) * scale_x;
        let src_y = height_mm as f64
            - PDF_MARGIN as f64
            - (edge.source_lane as f64 * PDF_LANE_HEIGHT as f64)
            - PDF_BAR_HEIGHT as f64 / 2.0;
        let tgt_y = height_mm as f64
            - PDF_MARGIN as f64
            - (edge.target_lane as f64 * PDF_LANE_HEIGHT as f64)
            - PDF_BAR_HEIGHT as f64 / 2.0;

        current_layer.set_outline_color(Color::Rgb(Rgb::new(1.0, 0.3, 1.0, None)));
        let line = Line {
            points: vec![
                (Point::new(Mm(src_x as f32), Mm(src_y as f32)), false),
                (Point::new(Mm(tgt_x as f32), Mm(tgt_y as f32)), false),
            ],
            is_closed: false,
            ..Default::default()
        };
        current_layer.add_line(line);

        // Edge label
        if !edge.label.is_empty() {
            let mid_x = ((src_x + tgt_x) / 2.0) as f32;
            let mid_y = ((src_y + tgt_y) / 2.0) as f32;
            current_layer.set_fill_color(Color::Rgb(Rgb::new(0.8, 0.3, 0.8, None)));
            current_layer.use_text(
                &edge.label,
                PDF_FONT_SIZE - 2.0,
                Mm(mid_x),
                Mm(mid_y + 1.5),
                &font,
            );
        }
    }

    doc.save(&mut std::io::BufWriter::new(
        std::fs::File::create(output).map_err(|e| format!("file error: {}", e))?,
    ))
    .map_err(|e| format!("PDF write error: {}", e))?;

    Ok(())
}

fn parse_hex_color(hex: &str) -> (f32, f32, f32) {
    let hex = hex.trim_start_matches('#');
    if hex.len() >= 6 {
        let r = u8::from_str_radix(&hex[0..2], 16).unwrap_or(128) as f32 / 255.0;
        let g = u8::from_str_radix(&hex[2..4], 16).unwrap_or(128) as f32 / 255.0;
        let b = u8::from_str_radix(&hex[4..6], 16).unwrap_or(128) as f32 / 255.0;
        (r, g, b)
    } else {
        (0.5, 0.5, 0.5)
    }
}

/// Bitmap PDF export fallback
fn render_pdf_raster(
    svg_data: &str,
    output: &Path,
    width_mm: f32,
    height_mm: f32,
) -> Result<(), String> {
    let (doc, page1, layer1) =
        PdfDocument::new("Seuss Timeline", Mm(width_mm), Mm(height_mm), "Timeline");
    let current_layer = doc.get_page(page1).get_layer(layer1);

    let opt = resvg::usvg::Options::default();
    let tree = resvg::usvg::Tree::from_str(svg_data, &opt)
        .map_err(|e| format!("SVG parse error: {}", e))?;

    let svg_w = tree.size().width();
    let svg_h = tree.size().height();

    let scale = 2.0f32;
    let px_w = (svg_w * scale) as u32;
    let px_h = (svg_h * scale) as u32;

    if px_w == 0 || px_h == 0 {
        return Err("SVG has zero dimensions".into());
    }

    let mut pixmap = resvg::tiny_skia::Pixmap::new(px_w, px_h).ok_or("failed to create pixmap")?;
    let transform = resvg::tiny_skia::Transform::from_scale(scale, scale);
    resvg::render(&tree, transform, &mut pixmap.as_mut());

    let rgba = pixmap.data();
    let mut rgb = Vec::with_capacity((px_w * px_h * 3) as usize);
    for chunk in rgba.chunks(4) {
        rgb.push(chunk[0]);
        rgb.push(chunk[1]);
        rgb.push(chunk[2]);
    }

    let image = Image::from(ImageXObject {
        width: Px(px_w as usize),
        height: Px(px_h as usize),
        color_space: ColorSpace::Rgb,
        bits_per_component: ColorBits::Bit8,
        interpolate: true,
        image_data: rgb,
        image_filter: None,
        clipping_bbox: None,
        smask: None,
    });

    image.add_to_layer(
        current_layer,
        ImageTransform {
            translate_x: Some(Mm(0.0)),
            translate_y: Some(Mm(0.0)),
            scale_x: Some(width_mm / px_w as f32),
            scale_y: Some(height_mm / px_h as f32),
            ..Default::default()
        },
    );

    doc.save(&mut std::io::BufWriter::new(
        std::fs::File::create(output).map_err(|e| format!("file error: {}", e))?,
    ))
    .map_err(|e| format!("PDF write error: {}", e))?;

    Ok(())
}
