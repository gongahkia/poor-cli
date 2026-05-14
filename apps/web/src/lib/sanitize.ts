export async function sanitizeHTML(dirty: string): Promise<string> {
  const DOMPurify = (await import("dompurify")).default;
  return DOMPurify.sanitize(dirty, {
    ALLOWED_TAGS: ["b", "i", "em", "strong", "a", "p", "br", "ul", "ol", "li", "code", "pre"],
    ALLOWED_ATTR: ["href", "title"],
    ALLOW_DATA_ATTR: false,
  });
}

export async function sanitizeSVG(svg: string): Promise<string> {
  const DOMPurify = (await import("dompurify")).default;
  return DOMPurify.sanitize(svg, {
    USE_PROFILES: { svg: true, svgFilters: true },
    FORBID_TAGS: ["script", "foreignObject"],
    FORBID_ATTR: ["onload", "onerror", "onclick", "onmouseover", "onfocus"],
  });
}

export function sanitizePlainText(text: string): string {
  return text
    .replace(/\0/g, "")
    .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}
