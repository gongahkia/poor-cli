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
    /// Texture mode: 0 = solid color, 1 = glyph atlas, 2 = background image.
    pub tex_kind: f32,
}

/// Compact per-quad instance data consumed by the GPU instanced pipeline.
#[repr(C)]
#[derive(Debug, Clone, Copy, bytemuck::Pod, bytemuck::Zeroable)]
pub struct QuadInstance {
    /// Destination rect: x, y, width, height in pixels.
    pub rect: [f32; 4],
    /// Texture coordinates: u_min, v_min, u_max, v_max.
    pub uv_rect: [f32; 4],
    /// Foreground/tint color.
    pub fg_color: [f32; 4],
    /// Background color.
    pub bg_color: [f32; 4],
    /// Texture mode: 0 = solid color, 1 = glyph atlas, 2 = background image.
    pub tex_kind: f32,
    _padding: [f32; 3],
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
    /// Per-quad instance data for the GPU renderer.
    pub instances: Vec<QuadInstance>,
}

impl QuadBatch {
    /// Create a batch with explicit backing storage sizes.
    pub fn with_capacity(vertex_capacity: usize, index_capacity: usize) -> Self {
        Self {
            vertices: Vec::with_capacity(vertex_capacity),
            indices: Vec::with_capacity(index_capacity),
            instances: Vec::with_capacity(index_capacity / 6),
        }
    }

    /// Create a new empty batch.
    pub fn new() -> Self {
        Self::with_capacity(4_096, 6_144)
    }

    /// Add a background quad for a cell.
    pub fn push_bg_quad(&mut self, x: f32, y: f32, w: f32, h: f32, color: [f32; 4]) {
        self.instances.push(QuadInstance {
            rect: [x, y, w, h],
            uv_rect: [0.0, 0.0, 1.0, 1.0],
            fg_color: [0.0; 4],
            bg_color: color,
            tex_kind: 0.0,
            _padding: [0.0; 3],
        });

        let base = self.vertices.len() as u32;
        self.vertices.extend_from_slice(&[
            Vertex {
                position: [x, y],
                tex_coords: [0.0, 0.0],
                fg_color: [0.0; 4],
                bg_color: color,
                tex_kind: 0.0,
            },
            Vertex {
                position: [x + w, y],
                tex_coords: [1.0, 0.0],
                fg_color: [0.0; 4],
                bg_color: color,
                tex_kind: 0.0,
            },
            Vertex {
                position: [x + w, y + h],
                tex_coords: [1.0, 1.0],
                fg_color: [0.0; 4],
                bg_color: color,
                tex_kind: 0.0,
            },
            Vertex {
                position: [x, y + h],
                tex_coords: [0.0, 1.0],
                fg_color: [0.0; 4],
                bg_color: color,
                tex_kind: 0.0,
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
        self.instances.push(QuadInstance {
            rect: [x, y, w, h],
            uv_rect: [region.u_min, region.v_min, region.u_max, region.v_max],
            fg_color,
            bg_color: [0.0; 4],
            tex_kind: 1.0,
            _padding: [0.0; 3],
        });

        let base = self.vertices.len() as u32;
        self.vertices.extend_from_slice(&[
            Vertex {
                position: [x, y],
                tex_coords: [region.u_min, region.v_min],
                fg_color,
                bg_color: [0.0; 4],
                tex_kind: 1.0,
            },
            Vertex {
                position: [x + w, y],
                tex_coords: [region.u_max, region.v_min],
                fg_color,
                bg_color: [0.0; 4],
                tex_kind: 1.0,
            },
            Vertex {
                position: [x + w, y + h],
                tex_coords: [region.u_max, region.v_max],
                fg_color,
                bg_color: [0.0; 4],
                tex_kind: 1.0,
            },
            Vertex {
                position: [x, y + h],
                tex_coords: [region.u_min, region.v_max],
                fg_color,
                bg_color: [0.0; 4],
                tex_kind: 1.0,
            },
        ]);
        self.indices
            .extend_from_slice(&[base, base + 1, base + 2, base, base + 2, base + 3]);
    }

    /// Add a textured background image quad.
    pub fn push_image_quad(&mut self, x: f32, y: f32, w: f32, h: f32, tint: [f32; 4]) {
        self.push_image_quad_with_uv(x, y, w, h, [0.0, 0.0, 1.0, 1.0], tint);
    }

    /// Add a textured background image quad with custom UV coordinates.
    pub fn push_image_quad_with_uv(
        &mut self,
        x: f32,
        y: f32,
        w: f32,
        h: f32,
        uv_rect: [f32; 4],
        tint: [f32; 4],
    ) {
        self.instances.push(QuadInstance {
            rect: [x, y, w, h],
            uv_rect,
            fg_color: tint,
            bg_color: [0.0; 4],
            tex_kind: 2.0,
            _padding: [0.0; 3],
        });

        let base = self.vertices.len() as u32;
        self.vertices.extend_from_slice(&[
            Vertex {
                position: [x, y],
                tex_coords: [uv_rect[0], uv_rect[1]],
                fg_color: tint,
                bg_color: [0.0; 4],
                tex_kind: 2.0,
            },
            Vertex {
                position: [x + w, y],
                tex_coords: [uv_rect[2], uv_rect[1]],
                fg_color: tint,
                bg_color: [0.0; 4],
                tex_kind: 2.0,
            },
            Vertex {
                position: [x + w, y + h],
                tex_coords: [uv_rect[2], uv_rect[3]],
                fg_color: tint,
                bg_color: [0.0; 4],
                tex_kind: 2.0,
            },
            Vertex {
                position: [x, y + h],
                tex_coords: [uv_rect[0], uv_rect[3]],
                fg_color: tint,
                bg_color: [0.0; 4],
                tex_kind: 2.0,
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
        self.instances.clear();
    }

    /// Append another batch, offsetting its indices to match the current vertex base.
    pub fn append(&mut self, other: &Self) {
        self.append_translated(other, 0.0, 0.0);
    }

    /// Append another batch with a positional translation.
    pub fn append_translated(&mut self, other: &Self, dx: f32, dy: f32) {
        let base = self.vertices.len() as u32;
        self.vertices
            .extend(other.vertices.iter().copied().map(|mut vertex| {
                vertex.position[0] += dx;
                vertex.position[1] += dy;
                vertex
            }));
        self.indices
            .extend(other.indices.iter().map(|index| index + base));
        self.instances
            .extend(other.instances.iter().copied().map(|mut instance| {
                instance.rect[0] += dx;
                instance.rect[1] += dy;
                instance
            }));
    }

    /// Return the number of quads in the batch.
    pub fn quad_count(&self) -> usize {
        self.instances.len()
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
        assert_eq!(batch.instances.len(), 1);
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

    #[test]
    fn test_push_image_quad_with_uv_records_custom_texture_region() {
        let mut batch = QuadBatch::new();
        let uv = [0.25, 0.0, 0.75, 1.0];

        batch.push_image_quad_with_uv(0.0, 0.0, 10.0, 20.0, uv, [1.0; 4]);

        assert_float_array_eq(batch.instances[0].uv_rect, uv);
        assert_float_array_eq(batch.vertices[0].tex_coords, [0.25, 0.0]);
        assert_float_array_eq(batch.vertices[1].tex_coords, [0.75, 0.0]);
        assert_float_array_eq(batch.vertices[2].tex_coords, [0.75, 1.0]);
        assert_float_array_eq(batch.vertices[3].tex_coords, [0.25, 1.0]);
    }

    #[test]
    fn test_append_offsets_indices() {
        let mut first = QuadBatch::with_capacity(8, 12);
        let mut second = QuadBatch::with_capacity(8, 12);

        first.push_bg_quad(0.0, 0.0, 10.0, 20.0, [1.0; 4]);
        second.push_bg_quad(10.0, 0.0, 10.0, 20.0, [0.5; 4]);

        first.append(&second);

        assert_eq!(first.vertices.len(), 8);
        assert_eq!(first.indices, vec![0, 1, 2, 0, 2, 3, 4, 5, 6, 4, 6, 7]);
        assert_eq!(first.instances.len(), 2);
        assert_eq!(first.quad_count(), 2);
    }

    #[test]
    fn test_append_translated_offsets_positions_and_instances() {
        let mut first = QuadBatch::new();
        let mut second = QuadBatch::new();
        second.push_bg_quad(10.0, 20.0, 30.0, 40.0, [1.0; 4]);

        first.append_translated(&second, 2.5, -3.5);

        assert_float_array_eq(first.vertices[0].position, [12.5, 16.5]);
        assert_float_array_eq(first.vertices[1].position, [42.5, 16.5]);
        assert_float_array_eq(first.instances[0].rect, [12.5, 16.5, 30.0, 40.0]);
    }

    fn assert_float_array_eq<const N: usize>(actual: [f32; N], expected: [f32; N]) {
        for (actual, expected) in actual.iter().zip(expected.iter()) {
            assert!((actual - expected).abs() < f32::EPSILON);
        }
    }
}
