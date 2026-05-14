use crate::error::AppError;
use serde::{Deserialize, Serialize};
use std::io::Read;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParsedDocument {
    pub filename: String,
    pub text: String,
    pub page_count: usize,
    pub char_count: usize,
}

#[tauri::command]
pub fn parse_pdf(path: String) -> Result<ParsedDocument, AppError> {
    let data = std::fs::read(&path)?;
    let text = pdf_extract::extract_text_from_mem(&data)
        .map_err(|e| AppError::Parse(format!("PDF extraction failed: {e}")))?;
    let page_count = text.matches('\u{000C}').count().max(1); // form feeds as page breaks
    let filename = std::path::Path::new(&path)
        .file_name().and_then(|n| n.to_str())
        .unwrap_or("document.pdf").to_string();
    let char_count = text.len();
    Ok(ParsedDocument { filename, text, page_count, char_count })
}

#[tauri::command]
pub fn parse_docx(path: String) -> Result<ParsedDocument, AppError> {
    let file = std::fs::File::open(&path)?;
    let mut archive = zip::ZipArchive::new(file)
        .map_err(|e| AppError::Parse(format!("invalid DOCX (not a ZIP): {e}")))?;
    let mut xml = String::new();
    {
        let mut entry = archive.by_name("word/document.xml")
            .map_err(|e| AppError::Parse(format!("missing word/document.xml: {e}")))?;
        entry.read_to_string(&mut xml)
            .map_err(|e| AppError::Io(format!("read error: {e}")))?;
    }
    // strip XML tags, keep text content
    let text = strip_xml_tags(&xml);
    let filename = std::path::Path::new(&path)
        .file_name().and_then(|n| n.to_str())
        .unwrap_or("document.docx").to_string();
    let char_count = text.len();
    let page_count = 1; // DOCX doesn't have reliable page count in XML
    Ok(ParsedDocument { filename, text, page_count, char_count })
}

fn strip_xml_tags(xml: &str) -> String {
    let mut result = String::with_capacity(xml.len() / 3);
    let mut in_tag = false;
    let mut last_was_para = false;
    for c in xml.chars() {
        match c {
            '<' => {
                in_tag = true;
                // check for paragraph/break tags
                let remaining = &xml[xml.len().min(result.len())..];
                if (remaining.starts_with("<w:p ")
                    || remaining.starts_with("<w:p>")
                    || remaining.starts_with("<w:br"))
                    && !last_was_para
                {
                    result.push('\n');
                    last_was_para = true;
                }
            }
            '>' => { in_tag = false; }
            _ if !in_tag => {
                result.push(c);
                last_was_para = false;
            }
            _ => {}
        }
    }
    // collapse multiple blank lines
    let mut cleaned = String::with_capacity(result.len());
    let mut blank_count = 0;
    for line in result.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            blank_count += 1;
            if blank_count <= 1 { cleaned.push('\n'); }
        } else {
            blank_count = 0;
            if !cleaned.is_empty() { cleaned.push('\n'); }
            cleaned.push_str(trimmed);
        }
    }
    cleaned.trim().to_string()
}
