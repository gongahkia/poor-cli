use std::path::Path;

/// Render SVG to PNG using resvg (Task 12)
pub fn render_png(svg_data: &str, output: &Path, dpi: u32) -> Result<(), String> {
    let opt = resvg::usvg::Options::default();
    let tree = resvg::usvg::Tree::from_str(svg_data, &opt)
        .map_err(|e| format!("SVG parse error: {}", e))?;

    let scale = dpi as f32 / 96.0;
    let size = tree.size();
    let width = (size.width() * scale) as u32;
    let height = (size.height() * scale) as u32;

    if width == 0 || height == 0 {
        return Err("SVG has zero dimensions".into());
    }

    let mut pixmap = resvg::tiny_skia::Pixmap::new(width, height)
        .ok_or("failed to create pixmap")?;

    let transform = resvg::tiny_skia::Transform::from_scale(scale, scale);
    resvg::render(&tree, transform, &mut pixmap.as_mut());

    pixmap.save_png(output)
        .map_err(|e| format!("PNG write error: {}", e))?;

    Ok(())
}
