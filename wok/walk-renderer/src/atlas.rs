//! Glyph atlas: caches rasterized glyphs in a GPU texture.

use std::collections::HashMap;

/// A rectangular region within the atlas texture.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct AtlasRegion {
    /// X offset in pixels.
    pub x: u32,
    /// Y offset in pixels.
    pub y: u32,
    /// Width in pixels.
    pub width: u32,
    /// Height in pixels.
    pub height: u32,
    /// U coordinate (left edge, 0.0-1.0).
    pub u_min: f32,
    /// V coordinate (top edge, 0.0-1.0).
    pub v_min: f32,
    /// U coordinate (right edge, 0.0-1.0).
    pub u_max: f32,
    /// V coordinate (bottom edge, 0.0-1.0).
    pub v_max: f32,
}

/// Key for looking up a glyph in the atlas.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct GlyphKey {
    /// Font ID.
    pub font_id: u32,
    /// Glyph ID within the font.
    pub glyph_id: u32,
    /// Font size in tenths of a point (for integer hashing).
    pub font_size_tenths: u32,
}

/// Shelf-packing glyph atlas for efficient GPU texture caching.
pub struct GlyphAtlas {
    /// Atlas texture width.
    width: u32,
    /// Atlas texture height.
    height: u32,
    /// Cached glyph regions.
    entries: HashMap<GlyphKey, AtlasRegion>,
    /// Current shelf Y position.
    shelf_y: u32,
    /// Current X position within the current shelf.
    shelf_x: u32,
    /// Current shelf height.
    shelf_height: u32,
    /// Total occupied pixel area.
    occupied_pixels: u64,
}

impl GlyphAtlas {
    /// Create a new atlas with the given dimensions.
    pub fn new(width: u32, height: u32) -> Self {
        Self {
            width,
            height,
            entries: HashMap::new(),
            shelf_y: 0,
            shelf_x: 0,
            shelf_height: 0,
            occupied_pixels: 0,
        }
    }

    /// Get or insert a glyph into the atlas.
    ///
    /// Returns the atlas region for the glyph. If the glyph is not cached,
    /// allocates space using shelf-packing and returns the new region.
    pub fn get_or_insert(
        &mut self,
        key: GlyphKey,
        glyph_width: u32,
        glyph_height: u32,
    ) -> Option<AtlasRegion> {
        if let Some(region) = self.entries.get(&key) {
            return Some(*region);
        }

        // Allocate space using shelf-packing
        let region = self.allocate(glyph_width, glyph_height)?;
        self.entries.insert(key, region);
        Some(region)
    }

    /// Allocate a rectangular region using shelf-packing.
    fn allocate(&mut self, width: u32, height: u32) -> Option<AtlasRegion> {
        if width == 0 || height == 0 {
            return Some(AtlasRegion {
                x: 0,
                y: 0,
                width: 0,
                height: 0,
                u_min: 0.0,
                v_min: 0.0,
                u_max: 0.0,
                v_max: 0.0,
            });
        }

        // Check if glyph fits in current shelf
        if self.shelf_x + width > self.width {
            // Move to next shelf
            self.shelf_y += self.shelf_height;
            self.shelf_x = 0;
            self.shelf_height = 0;
        }

        // Check if we have vertical space
        if self.shelf_y + height > self.height {
            return None; // Atlas full
        }

        let x = self.shelf_x;
        let y = self.shelf_y;
        self.shelf_x += width;
        self.shelf_height = self.shelf_height.max(height);
        self.occupied_pixels += u64::from(width) * u64::from(height);

        let atlas_w = self.width as f32;
        let atlas_h = self.height as f32;

        Some(AtlasRegion {
            x,
            y,
            width,
            height,
            u_min: x as f32 / atlas_w,
            v_min: y as f32 / atlas_h,
            u_max: (x + width) as f32 / atlas_w,
            v_max: (y + height) as f32 / atlas_h,
        })
    }

    /// Clear all cached entries (e.g., on font size change).
    pub fn clear(&mut self) {
        self.entries.clear();
        self.shelf_y = 0;
        self.shelf_x = 0;
        self.shelf_height = 0;
        self.occupied_pixels = 0;
    }

    /// Get the number of cached glyphs.
    pub fn len(&self) -> usize {
        self.entries.len()
    }

    /// Check if the atlas is empty.
    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    /// Return the approximate atlas occupancy ratio in the range 0.0..=1.0.
    pub fn usage_ratio(&self) -> f32 {
        let total_pixels = u64::from(self.width) * u64::from(self.height);
        if total_pixels == 0 {
            return 0.0;
        }
        (self.occupied_pixels as f32 / total_pixels as f32).clamp(0.0, 1.0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_insert_and_retrieve() {
        let mut atlas = GlyphAtlas::new(2_048, 2_048);
        let key = GlyphKey {
            font_id: 0,
            glyph_id: 65,
            font_size_tenths: 140,
        };
        let region = atlas.get_or_insert(key, 10, 16).unwrap();
        assert_eq!(region.x, 0);
        assert_eq!(region.y, 0);
        assert_eq!(region.width, 10);

        // Second insert returns same region
        let region2 = atlas.get_or_insert(key, 10, 16).unwrap();
        assert_eq!(region, region2);
    }

    #[test]
    fn test_no_overlap() {
        let mut atlas = GlyphAtlas::new(2_048, 2_048);
        let mut regions = Vec::new();
        for i in 0..100 {
            let key = GlyphKey {
                font_id: 0,
                glyph_id: i,
                font_size_tenths: 140,
            };
            let region = atlas.get_or_insert(key, 10, 16).unwrap();
            regions.push(region);
        }

        // Check no two regions overlap
        for (i, a) in regions.iter().enumerate() {
            for b in &regions[i + 1..] {
                let overlaps = a.x < b.x + b.width
                    && a.x + a.width > b.x
                    && a.y < b.y + b.height
                    && a.y + a.height > b.y;
                assert!(!overlaps, "regions {a:?} and {b:?} overlap");
            }
        }
    }

    #[test]
    fn test_shelf_wrapping() {
        let mut atlas = GlyphAtlas::new(100, 100);
        // Fill first shelf
        for i in 0..10 {
            let key = GlyphKey {
                font_id: 0,
                glyph_id: i,
                font_size_tenths: 140,
            };
            atlas.get_or_insert(key, 10, 16).unwrap();
        }
        // Next one should wrap to a new shelf
        let key = GlyphKey {
            font_id: 0,
            glyph_id: 10,
            font_size_tenths: 140,
        };
        let region = atlas.get_or_insert(key, 10, 16).unwrap();
        assert_eq!(region.x, 0);
        assert_eq!(region.y, 16); // second shelf starts at y=16
    }
}
