//! Render pipeline: wgpu pipeline for drawing terminal grid cells.

use crate::atlas::AtlasRegion;

/// Vertex format for the terminal grid render pipeline.
#[repr(C)]
#[derive(Debug, Clone, Copy, bytemuck::Pod, bytemuck::Zeroable)]
pub struct Vertex {
    /// Position (x, y).
    pub position: [f32; 2],
    /// Texture coordinates (u, v).
    pub tex_coords: [f32; 2],
    /// Foreground color (r, g, b, a).
    pub fg_color: [f32; 4],
    /// Background color (r, g, b, a).
    pub bg_color: [f32; 4],
}

/// Cursor display shape.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CursorShape {
    /// Filled block cursor.
    Block,
    /// Thin vertical bar (2px wide).
    Bar,
    /// Underline (2px tall).
    Underline,
}

/// A batch of quads ready for GPU submission.
pub struct QuadBatch {
    /// Vertex data.
    pub vertices: Vec<Vertex>,
    /// Index data.
    pub indices: Vec<u32>,
}

impl QuadBatch {
    /// Create a new empty batch.
    pub fn new() -> Self {
        Self {
            vertices: Vec::with_capacity(4_096),
            indices: Vec::with_capacity(6_144),
        }
    }

    /// Add a background quad for a cell.
    pub fn push_bg_quad(&mut self, x: f32, y: f32, w: f32, h: f32, color: [f32; 4]) {
        let base = self.vertices.len() as u32;
        self.vertices.extend_from_slice(&[
            Vertex {
                position: [x, y],
                tex_coords: [0.0, 0.0],
                fg_color: [0.0; 4],
                bg_color: color,
            },
            Vertex {
                position: [x + w, y],
                tex_coords: [1.0, 0.0],
                fg_color: [0.0; 4],
                bg_color: color,
            },
            Vertex {
                position: [x + w, y + h],
                tex_coords: [1.0, 1.0],
                fg_color: [0.0; 4],
                bg_color: color,
            },
            Vertex {
                position: [x, y + h],
                tex_coords: [0.0, 1.0],
                fg_color: [0.0; 4],
                bg_color: color,
            },
        ]);
        self.indices
            .extend_from_slice(&[base, base + 1, base + 2, base, base + 2, base + 3]);
    }

    /// Add a textured glyph quad.
    pub fn push_glyph_quad(
        &mut self,
        x: f32,
        y: f32,
        w: f32,
        h: f32,
        region: &AtlasRegion,
        fg_color: [f32; 4],
    ) {
        let base = self.vertices.len() as u32;
        self.vertices.extend_from_slice(&[
            Vertex {
                position: [x, y],
                tex_coords: [region.u_min, region.v_min],
                fg_color,
                bg_color: [0.0; 4],
            },
            Vertex {
                position: [x + w, y],
                tex_coords: [region.u_max, region.v_min],
                fg_color,
                bg_color: [0.0; 4],
            },
            Vertex {
                position: [x + w, y + h],
                tex_coords: [region.u_max, region.v_max],
                fg_color,
                bg_color: [0.0; 4],
            },
            Vertex {
                position: [x, y + h],
                tex_coords: [region.u_min, region.v_max],
                fg_color,
                bg_color: [0.0; 4],
            },
        ]);
        self.indices
            .extend_from_slice(&[base, base + 1, base + 2, base, base + 2, base + 3]);
    }

    /// Add a cursor quad.
    pub fn push_cursor(
        &mut self,
        x: f32,
        y: f32,
        cell_w: f32,
        cell_h: f32,
        shape: CursorShape,
        color: [f32; 4],
    ) {
        match shape {
            CursorShape::Block => self.push_bg_quad(x, y, cell_w, cell_h, color),
            CursorShape::Bar => self.push_bg_quad(x, y, 2.0, cell_h, color),
            CursorShape::Underline => self.push_bg_quad(x, y + cell_h - 2.0, cell_w, 2.0, color),
        }
    }

    /// Clear the batch for reuse.
    pub fn clear(&mut self) {
        self.vertices.clear();
        self.indices.clear();
    }

    /// Return the number of quads in the batch.
    pub fn quad_count(&self) -> usize {
        self.indices.len() / 6
    }
}

impl Default for QuadBatch {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_push_bg_quad() {
        let mut batch = QuadBatch::new();
        batch.push_bg_quad(0.0, 0.0, 10.0, 20.0, [1.0, 0.0, 0.0, 1.0]);
        assert_eq!(batch.vertices.len(), 4);
        assert_eq!(batch.indices.len(), 6);
        assert_eq!(batch.quad_count(), 1);
    }

    #[test]
    fn test_batch_multiple_quads() {
        let mut batch = QuadBatch::new();
        for i in 0..100 {
            batch.push_bg_quad(i as f32 * 10.0, 0.0, 10.0, 20.0, [1.0; 4]);
        }
        assert_eq!(batch.quad_count(), 100);
    }

    #[test]
    fn test_clear() {
        let mut batch = QuadBatch::new();
        batch.push_bg_quad(0.0, 0.0, 10.0, 20.0, [1.0; 4]);
        batch.clear();
        assert_eq!(batch.quad_count(), 0);
    }
}
