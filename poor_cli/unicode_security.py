"""Unicode security scanner — detects dangerous invisible/bidi characters."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List

# bidi override/embedding/isolate chars (trojan source attacks)
_BIDI_CHARS = set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A))
# zero-width / invisible formatting chars
_ZERO_WIDTH_CHARS = {0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0xFEFF}
_DANGEROUS_CHARS = _BIDI_CHARS | _ZERO_WIDTH_CHARS

_CHAR_NAMES = {
    0x202A: "LRE", 0x202B: "RLE", 0x202C: "PDF", 0x202D: "LRO", 0x202E: "RLO",
    0x2066: "LRI", 0x2067: "RLI", 0x2068: "FSI", 0x2069: "PDI",
    0x200B: "ZWSP", 0x200C: "ZWNJ", 0x200D: "ZWJ",
    0x200E: "LRM", 0x200F: "RLM", 0xFEFF: "BOM/ZWNBSP",
}


@dataclass
class UnicodeWarning:
    """A single dangerous Unicode character finding."""
    line: int
    col: int
    codepoint: int
    name: str
    category: str  # "bidi" or "zero_width"

    def __str__(self) -> str:
        return f"line {self.line}, col {self.col}: U+{self.codepoint:04X} ({self.name}) [{self.category}]"


@dataclass
class ScanResult:
    """Result of scanning text for dangerous Unicode."""
    warnings: List[UnicodeWarning] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return len(self.warnings) == 0

    def summary(self) -> str:
        if self.clean:
            return ""
        lines = [f"[unicode-security] {len(self.warnings)} dangerous character(s) detected:"]
        for w in self.warnings[:10]: # cap display
            lines.append(f"  {w}")
        if len(self.warnings) > 10:
            lines.append(f"  ... and {len(self.warnings) - 10} more")
        return "\n".join(lines)


def scan_text(text: str) -> ScanResult:
    """Scan text for dangerous Unicode characters."""
    result = ScanResult()
    for line_num, line in enumerate(text.split("\n"), 1):
        for col, ch in enumerate(line, 1):
            cp = ord(ch)
            if cp in _DANGEROUS_CHARS:
                category = "bidi" if cp in _BIDI_CHARS else "zero_width"
                name = _CHAR_NAMES.get(cp, f"U+{cp:04X}")
                result.warnings.append(UnicodeWarning(
                    line=line_num, col=col, codepoint=cp,
                    name=name, category=category,
                ))
    return result
