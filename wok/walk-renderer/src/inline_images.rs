//! Inline image storage and sampling for terminal protocols.

use std::collections::HashMap;

/// One on-screen placement for a decoded inline image.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ImagePlacement {
    /// Absolute terminal row anchor.
    pub row: usize,
    /// Column anchor.
    pub col: usize,
    /// Width in terminal cells.
    pub display_cols: u16,
    /// Height in terminal cells.
    pub display_rows: u16,
    /// Optional protocol placement id.
    pub placement_id: u32,
}

/// Decoded inline image content.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InlineImage {
    /// Protocol image id.
    pub id: u32,
    /// Pixel width.
    pub width: u32,
    /// Pixel height.
    pub height: u32,
    /// RGBA8 pixels.
    pub pixels: Vec<u8>,
    /// One or more placements for this image.
    pub placements: Vec<ImagePlacement>,
}

/// Store for protocol images and placements.
#[derive(Debug, Default, Clone)]
pub struct InlineImageStore {
    images: HashMap<u32, InlineImage>,
}

impl InlineImageStore {
    /// Create an empty inline image store.
    pub fn new() -> Self {
        Self::default()
    }

    /// Insert or replace image data, replacing existing placements with the provided placement.
    pub fn upsert_image(
        &mut self,
        id: u32,
        width: u32,
        height: u32,
        pixels: Vec<u8>,
        placement: ImagePlacement,
    ) {
        self.images.insert(
            id,
            InlineImage {
                id,
                width: width.max(1),
                height: height.max(1),
                pixels,
                placements: vec![placement],
            },
        );
    }

    /// Add a placement for an already-decoded image id.
    pub fn place_existing(&mut self, id: u32, placement: ImagePlacement) {
        if let Some(image) = self.images.get_mut(&id) {
            image.placements.push(placement);
        }
    }

    /// Delete images and/or placements based on protocol ids.
    pub fn delete(&mut self, image_id: Option<u32>, placement_id: Option<u32>) {
        if image_id.is_none() && placement_id.is_none() {
            self.images.clear();
            return;
        }

        if let Some(image_id) = image_id {
            if let Some(image) = self.images.get_mut(&image_id) {
                if let Some(placement_id) = placement_id {
                    image
                        .placements
                        .retain(|placement| placement.placement_id != placement_id);
                    if image.placements.is_empty() {
                        self.images.remove(&image_id);
                    }
                } else {
                    self.images.remove(&image_id);
                }
            }
            return;
        }

        let placement_id = placement_id.expect("placement id handled above");
        self.images.retain(|_, image| {
            image
                .placements
                .retain(|placement| placement.placement_id != placement_id);
            !image.placements.is_empty()
        });
    }

    /// Return a sampled RGBA color for one terminal cell when covered by an inline image.
    pub fn sample_cell_color(&self, absolute_row: usize, col: usize) -> Option<[f32; 4]> {
        for image in self.images.values() {
            for placement in &image.placements {
                let row_start = placement.row;
                let row_end = row_start + placement.display_rows as usize;
                let col_start = placement.col;
                let col_end = col_start + placement.display_cols as usize;

                if !(row_start..row_end).contains(&absolute_row)
                    || !(col_start..col_end).contains(&col)
                {
                    continue;
                }

                if image.pixels.len() < 4 {
                    continue;
                }

                let relative_row = absolute_row.saturating_sub(row_start);
                let relative_col = col.saturating_sub(col_start);
                let px = ((relative_col as f32 / placement.display_cols.max(1) as f32)
                    * image.width as f32)
                    .floor() as u32;
                let py = ((relative_row as f32 / placement.display_rows.max(1) as f32)
                    * image.height as f32)
                    .floor() as u32;
                let px = px.min(image.width.saturating_sub(1));
                let py = py.min(image.height.saturating_sub(1));
                let index = ((py * image.width + px) * 4) as usize;
                if index + 3 >= image.pixels.len() {
                    continue;
                }

                return Some([
                    f32::from(image.pixels[index]) / 255.0,
                    f32::from(image.pixels[index + 1]) / 255.0,
                    f32::from(image.pixels[index + 2]) / 255.0,
                    f32::from(image.pixels[index + 3]) / 255.0,
                ]);
            }
        }
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_store_and_sample() {
        let mut store = InlineImageStore::new();
        store.upsert_image(
            7,
            1,
            1,
            vec![255, 0, 0, 255],
            ImagePlacement {
                row: 5,
                col: 10,
                display_cols: 2,
                display_rows: 2,
                placement_id: 1,
            },
        );

        let sampled = store.sample_cell_color(5, 10).expect("sampled");
        assert!(sampled[0] > 0.9);
        assert!(sampled[1] < 0.1);
    }

    #[test]
    fn test_delete_specific_placement() {
        let mut store = InlineImageStore::new();
        store.upsert_image(
            7,
            1,
            1,
            vec![255, 0, 0, 255],
            ImagePlacement {
                row: 5,
                col: 10,
                display_cols: 1,
                display_rows: 1,
                placement_id: 11,
            },
        );
        store.place_existing(
            7,
            ImagePlacement {
                row: 6,
                col: 11,
                display_cols: 1,
                display_rows: 1,
                placement_id: 12,
            },
        );

        assert!(store.sample_cell_color(5, 10).is_some());
        assert!(store.sample_cell_color(6, 11).is_some());

        store.delete(Some(7), Some(11));

        assert!(store.sample_cell_color(5, 10).is_none());
        assert!(store.sample_cell_color(6, 11).is_some());
    }
}
