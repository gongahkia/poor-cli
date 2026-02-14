use std::path::Path;
use crate::lang::parser::parse_program;
use crate::eval::evaluator::Evaluator;
use crate::layout::engine::compute_layout;
use crate::render::svg_render::{render_svg, Theme};

/// Markdown preprocessor (Task 54)
/// Scans for ```seuss fenced code blocks, evaluates them, and replaces with inline SVG images
pub fn process_markdown(content: &str, base_dir: &Path) -> Result<String, String> {
    let mut output = String::new();
    let mut in_seuss_block = false;
    let mut seuss_source = String::new();
    let mut block_count = 0;

    for line in content.lines() {
        if line.trim().starts_with("```seuss") && !in_seuss_block {
            in_seuss_block = true;
            seuss_source.clear();
            continue;
        }

        if line.trim() == "```" && in_seuss_block {
            in_seuss_block = false;
            block_count += 1;

            // Evaluate and render
            match render_seuss_block(&seuss_source, block_count) {
                Ok(svg) => {
                    let svg_filename = format!("seuss_block_{}.svg", block_count);
                    let svg_path = base_dir.join(&svg_filename);
                    std::fs::write(&svg_path, &svg)
                        .map_err(|e| format!("failed to write SVG: {}", e))?;
                    output.push_str(&format!("![Seuss Timeline {}]({})\n", block_count, svg_filename));
                }
                Err(e) => {
                    output.push_str(&format!("<!-- seuss error: {} -->\n", e));
                    output.push_str("```seuss\n");
                    output.push_str(&seuss_source);
                    output.push_str("```\n");
                }
            }
            continue;
        }

        if in_seuss_block {
            seuss_source.push_str(line);
            seuss_source.push('\n');
        } else {
            output.push_str(line);
            output.push('\n');
        }
    }

    Ok(output)
}

fn render_seuss_block(source: &str, block_num: usize) -> Result<String, String> {
    let file_str = format!("markdown:block{}", block_num);
    let program = parse_program(source, &file_str)
        .map_err(|errors| errors.iter().map(|e| e.to_string()).collect::<Vec<_>>().join("; "))?;

    let mut evaluator = Evaluator::new();
    evaluator.eval_program(&program)
        .map_err(|e| e.to_string())?;

    let layout = compute_layout(&evaluator.world);
    let theme = Theme::default();
    Ok(render_svg(&layout, &theme))
}
