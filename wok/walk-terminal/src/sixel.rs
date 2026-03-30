//! Sixel image parser for DCS `ESC P ... ESC \\` payloads.

use std::collections::HashMap;

/// Parsed Sixel DCS parameters.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SixelParams {
    /// Pn1: aspect ratio / pan.
    pub pn1: u16,
    /// Pn2: background mode (`1` means transparent background).
    pub pn2: u16,
    /// Pn3: grid size.
    pub pn3: u16,
}

impl SixelParams {
    /// Return whether the sixel requests transparent background.
    pub fn transparent_background(self) -> bool {
        self.pn2 == 1
    }
}

/// Decoded Sixel image.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SixelImage {
    /// Raster width in pixels.
    pub width: u32,
    /// Raster height in pixels.
    pub height: u32,
    /// RGBA8 pixel data, row-major.
    pub pixels: Vec<u8>,
    /// Parsed DCS parameters.
    pub params: SixelParams,
}

/// Parse a Sixel DCS payload (without `ESC P` and `ESC \\` wrappers).
pub fn parse_sixel_dcs(payload: &str) -> Result<SixelImage, String> {
    let q_index = payload
        .find('q')
        .ok_or_else(|| "missing sixel 'q' introducer".to_string())?;
    let params = parse_sixel_params(&payload[..q_index]);
    let body = &payload[q_index + 1..];

    let mut parser = SixelParser::new(params);
    parser.parse_body(body)?;
    Ok(parser.finish())
}

struct SixelParser {
    params: SixelParams,
    palette: HashMap<u16, [u8; 3]>,
    current_color: u16,
    pixels: HashMap<(usize, usize), u16>,
    x: usize,
    y: usize,
    max_x: usize,
    max_y: usize,
    declared_width: usize,
    declared_height: usize,
}

impl SixelParser {
    fn new(params: SixelParams) -> Self {
        let mut palette = HashMap::new();
        palette.insert(0, [0, 0, 0]);
        Self {
            params,
            palette,
            current_color: 0,
            pixels: HashMap::new(),
            x: 0,
            y: 0,
            max_x: 0,
            max_y: 0,
            declared_width: 0,
            declared_height: 0,
        }
    }

    fn parse_body(&mut self, body: &str) -> Result<(), String> {
        let bytes = body.as_bytes();
        let mut idx = 0;

        while idx < bytes.len() {
            match bytes[idx] {
                b'#' => {
                    idx += 1;
                    self.parse_color_definition(bytes, &mut idx)?;
                }
                b'!' => {
                    idx += 1;
                    let repeat = read_number(bytes, &mut idx).unwrap_or(1).max(1) as usize;
                    if let Some(next) = bytes.get(idx).copied() {
                        if is_sixel_char(next) {
                            self.paint_sixel_char(next, repeat);
                            idx += 1;
                        }
                    }
                }
                b'-' => {
                    self.x = 0;
                    self.y = self.y.saturating_add(6);
                    idx += 1;
                }
                b'$' => {
                    self.x = 0;
                    idx += 1;
                }
                b'"' => {
                    idx += 1;
                    self.parse_raster_attributes(bytes, &mut idx);
                }
                byte if is_sixel_char(byte) => {
                    self.paint_sixel_char(byte, 1);
                    idx += 1;
                }
                _ => {
                    idx += 1;
                }
            }
        }

        Ok(())
    }

    fn parse_color_definition(&mut self, bytes: &[u8], idx: &mut usize) -> Result<(), String> {
        let color_index = read_number(bytes, idx)
            .ok_or_else(|| "missing color index after sixel '#' introducer".to_string())?;
        self.current_color = color_index;

        if *idx >= bytes.len() || bytes[*idx] != b';' {
            return Ok(());
        }
        *idx += 1;

        let color_type = read_number(bytes, idx).unwrap_or(2);
        if *idx < bytes.len() && bytes[*idx] == b';' {
            *idx += 1;
        }
        let p1 = read_number(bytes, idx).unwrap_or(0);
        if *idx < bytes.len() && bytes[*idx] == b';' {
            *idx += 1;
        }
        let p2 = read_number(bytes, idx).unwrap_or(0);
        if *idx < bytes.len() && bytes[*idx] == b';' {
            *idx += 1;
        }
        let p3 = read_number(bytes, idx).unwrap_or(0);

        let rgb = match color_type {
            1 => hls_to_rgb(p1, p2, p3),
            _ => [
                percent_to_byte(p1),
                percent_to_byte(p2),
                percent_to_byte(p3),
            ],
        };
        self.palette.insert(color_index, rgb);
        Ok(())
    }

    fn parse_raster_attributes(&mut self, bytes: &[u8], idx: &mut usize) {
        let _pan = read_number(bytes, idx).unwrap_or(1);
        if *idx < bytes.len() && bytes[*idx] == b';' {
            *idx += 1;
        }
        let _pad = read_number(bytes, idx).unwrap_or(1);
        if *idx < bytes.len() && bytes[*idx] == b';' {
            *idx += 1;
        }
        self.declared_width = read_number(bytes, idx).unwrap_or(0) as usize;
        if *idx < bytes.len() && bytes[*idx] == b';' {
            *idx += 1;
        }
        self.declared_height = read_number(bytes, idx).unwrap_or(0) as usize;
    }

    fn paint_sixel_char(&mut self, byte: u8, repeat: usize) {
        let mask = byte.saturating_sub(63);
        for _ in 0..repeat {
            self.max_x = self.max_x.max(self.x);
            for bit in 0..6 {
                if mask & (1 << bit) == 0 {
                    continue;
                }
                let py = self.y + bit;
                self.max_y = self.max_y.max(py);
                self.pixels.insert((self.x, py), self.current_color);
            }
            self.x = self.x.saturating_add(1);
        }
    }

    fn finish(self) -> SixelImage {
        let width = (self.max_x + 1).max(self.declared_width).max(1);
        let height = (self.max_y + 1).max(self.declared_height).max(1);

        let mut pixels = vec![0u8; width.saturating_mul(height).saturating_mul(4)];
        let transparent_bg = self.params.transparent_background();
        let bg_color = self.palette.get(&0).copied().unwrap_or([0, 0, 0]);

        for y in 0..height {
            for x in 0..width {
                let idx = (y * width + x) * 4;
                if transparent_bg {
                    pixels[idx + 3] = 0;
                } else {
                    pixels[idx] = bg_color[0];
                    pixels[idx + 1] = bg_color[1];
                    pixels[idx + 2] = bg_color[2];
                    pixels[idx + 3] = 255;
                }
            }
        }

        for ((x, y), color_index) in self.pixels {
            let rgb = self
                .palette
                .get(&color_index)
                .copied()
                .unwrap_or([255, 255, 255]);
            let idx = (y * width + x) * 4;
            pixels[idx] = rgb[0];
            pixels[idx + 1] = rgb[1];
            pixels[idx + 2] = rgb[2];
            pixels[idx + 3] = 255;
        }

        SixelImage {
            width: width as u32,
            height: height as u32,
            pixels,
            params: self.params,
        }
    }
}

fn parse_sixel_params(raw: &str) -> SixelParams {
    let mut numbers = raw
        .split(';')
        .filter_map(|segment| segment.trim().parse::<u16>().ok());
    SixelParams {
        pn1: numbers.next().unwrap_or(0),
        pn2: numbers.next().unwrap_or(0),
        pn3: numbers.next().unwrap_or(0),
    }
}

fn read_number(bytes: &[u8], idx: &mut usize) -> Option<u16> {
    let start = *idx;
    while *idx < bytes.len() && bytes[*idx].is_ascii_digit() {
        *idx += 1;
    }
    if *idx == start {
        return None;
    }
    std::str::from_utf8(&bytes[start..*idx])
        .ok()
        .and_then(|value| value.parse::<u16>().ok())
}

fn is_sixel_char(byte: u8) -> bool {
    (b'?'..=b'~').contains(&byte)
}

fn percent_to_byte(value: u16) -> u8 {
    ((value.min(100) as f32 / 100.0) * 255.0).round() as u8
}

fn hls_to_rgb(hue: u16, lightness: u16, saturation: u16) -> [u8; 3] {
    let h = (hue as f32 % 360.0) / 360.0;
    let l = (lightness.min(100) as f32) / 100.0;
    let s = (saturation.min(100) as f32) / 100.0;

    if s == 0.0 {
        let gray = (l * 255.0).round() as u8;
        return [gray, gray, gray];
    }

    let q = if l < 0.5 {
        l * (1.0 + s)
    } else {
        l + s - l * s
    };
    let p = 2.0 * l - q;

    [
        (hue_to_rgb(p, q, h + 1.0 / 3.0) * 255.0).round() as u8,
        (hue_to_rgb(p, q, h) * 255.0).round() as u8,
        (hue_to_rgb(p, q, h - 1.0 / 3.0) * 255.0).round() as u8,
    ]
}

fn hue_to_rgb(p: f32, q: f32, mut t: f32) -> f32 {
    if t < 0.0 {
        t += 1.0;
    }
    if t > 1.0 {
        t -= 1.0;
    }
    if t < 1.0 / 6.0 {
        return p + (q - p) * 6.0 * t;
    }
    if t < 1.0 / 2.0 {
        return q;
    }
    if t < 2.0 / 3.0 {
        return p + (q - p) * (2.0 / 3.0 - t) * 6.0;
    }
    p
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_rgb_palette_and_pixels() {
        let image = parse_sixel_dcs("1;0;0q#1;2;100;0;0~").expect("parse");
        assert_eq!(image.width, 1);
        assert_eq!(image.height, 6);
        assert_eq!(image.params.pn1, 1);
        assert_eq!(image.params.pn2, 0);
        assert_eq!(image.params.pn3, 0);
        assert_eq!(&image.pixels[0..4], &[255, 0, 0, 255]);
    }

    #[test]
    fn test_repeat_and_newline() {
        let image = parse_sixel_dcs("q#1;2;0;100;0!2~-#2;2;0;0;100~").expect("parse");
        assert_eq!(image.width, 2);
        assert_eq!(image.height, 12);
        let top_left = &image.pixels[0..4];
        assert_eq!(top_left, &[0, 255, 0, 255]);
    }

    #[test]
    fn test_hls_palette_definition() {
        let image = parse_sixel_dcs("q#3;1;120;50;100?").expect("parse");
        let pixel = &image.pixels[0..4];
        assert!(pixel[1] >= pixel[0]);
        assert!(pixel[1] >= pixel[2]);
        assert_eq!(pixel[3], 255);
    }
}
