use std::path::Path;
use printpdf::*;

/// Render SVG to PDF (Task 13)
pub fn render_pdf(svg_data: &str, output: &Path, width_mm: f32, height_mm: f32) -> Result<(), String> {
    let (doc, page1, layer1) = PdfDocument::new("Seuss Timeline", Mm(width_mm), Mm(height_mm), "Timeline");
    let current_layer = doc.get_page(page1).get_layer(layer1);

    // Embed SVG as text annotation since printpdf doesn't natively render SVG paths
    // For production, svg2pdf would be better, but we provide a basic PDF wrapper
    let font = doc.add_builtin_font(BuiltinFont::Helvetica)
        .map_err(|e| format!("font error: {}", e))?;

    // Parse SVG to extract text and basic structure info
    let opt = resvg::usvg::Options::default();
    let tree = resvg::usvg::Tree::from_str(svg_data, &opt)
        .map_err(|e| format!("SVG parse error: {}", e))?;

    let svg_w = tree.size().width();
    let svg_h = tree.size().height();
    let scale_x = width_mm / svg_w;
    let scale_y = height_mm / svg_h;

    // Rasterize SVG and embed as image
    let scale = 2.0f32; // 2x for quality
    let px_w = (svg_w * scale) as u32;
    let px_h = (svg_h * scale) as u32;

    if px_w == 0 || px_h == 0 {
        return Err("SVG has zero dimensions".into());
    }

    let mut pixmap = resvg::tiny_skia::Pixmap::new(px_w, px_h)
        .ok_or("failed to create pixmap")?;
    let transform = resvg::tiny_skia::Transform::from_scale(scale, scale);
    resvg::render(&tree, transform, &mut pixmap.as_mut());

    // Convert RGBA to RGB for PDF
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
            scale_x: Some(width_mm as f32 / px_w as f32),
            scale_y: Some(height_mm as f32 / px_h as f32),
            ..Default::default()
        },
    );

    doc.save(&mut std::io::BufWriter::new(
        std::fs::File::create(output).map_err(|e| format!("file error: {}", e))?,
    )).map_err(|e| format!("PDF write error: {}", e))?;

    Ok(())
}
