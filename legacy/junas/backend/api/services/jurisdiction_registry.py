"""Multi-jurisdiction registry ported from Junas jurisdictions/."""
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class CitationPattern:
    kind: str
    regex: str  # regex string for the jurisdiction
    description: str

@dataclass
class JurisdictionConfig:
    id: str
    name: str
    short_name: str
    citation_patterns: list[CitationPattern]
    legal_source_domains: dict[str, list[str]]
    system_prompt_addition: str
    template_ids: list[str] = field(default_factory=list)

JURISDICTIONS: dict[str, JurisdictionConfig] = {
    "sg": JurisdictionConfig(
        id="sg", name="Singapore", short_name="SG",
        citation_patterns=[
            CitationPattern("slr_r", r"\[(\d{4})\]\s+(\d+)\s+SLR\(R\)\s+(\d+)", "Singapore Law Reports (Reissue)"),
            CitationPattern("slr", r"\[(\d{4})\]\s+(\d+)\s+SLR\s+(\d+)", "Singapore Law Reports"),
            CitationPattern("sgca", r"\[(\d{4})\]\s+SGCA\s+(\d+)", "Singapore Court of Appeal"),
            CitationPattern("sghc", r"\[(\d{4})\]\s+SGHC\s+(\d+)", "Singapore High Court"),
            CitationPattern("statute_cap", r"\b([A-Z][A-Za-z0-9&'/-]*(?:\s+[A-Z][A-Za-z0-9&'/-]*)*\s+Act)\s*\((Cap\.?\s*[0-9A-Z]+(?:\s*,\s*\d{4}\s+Rev\s+Ed)?)\)", "Singapore statute chapter"),
        ],
        legal_source_domains={
            "case_law": ["judiciary.gov.sg", "singaporelawwatch.sg"],
            "statutes": ["sso.agc.gov.sg", "agc.gov.sg"],
        },
        system_prompt_addition="You are specialized in Singapore law. Use proper Singapore citation formats:\n- [YYYY] X SLR(R) XXX, [YYYY] SLR XXX, [YYYY] SGCA XX, [YYYY] SGHC XX\n- Statute format: Act Name (Cap. XX, YYYY Rev Ed)",
        template_ids=["nda-sg", "employment-sg", "mou-sg", "tenancy-sg", "board-resolution-sg", "share-transfer-sg"],
    ),
    "my": JurisdictionConfig(
        id="my", name="Malaysia", short_name="MY",
        citation_patterns=[
            CitationPattern("mlj", r"\[(\d{4})\]\s+(\d+)\s+MLJ\s+(\d+)", "Malayan Law Journal"),
            CitationPattern("mlju", r"\[(\d{4})\]\s+MLJU\s+(\d+)", "Malayan Law Journal Unreported"),
            CitationPattern("mlra", r"\[(\d{4})\]\s+MLRA\s+(\d+)", "Malayan Law Reports Appellate"),
            CitationPattern("clj", r"\[(\d{4})\]\s+(\d+)\s+CLJ\s+(\d+)", "Current Law Journal"),
        ],
        legal_source_domains={
            "case_law": ["kehakiman.gov.my"],
            "statutes": ["lom.agc.gov.my"],
        },
        system_prompt_addition="You are specialized in Malaysian law. Use proper Malaysian citation formats:\n- [YYYY] X MLJ XXX, [YYYY] MLJU XX, [YYYY] X CLJ XXX",
        template_ids=[],
    ),
    "us": JurisdictionConfig(
        id="us", name="United States", short_name="US",
        citation_patterns=[
            CitationPattern("us_reports", r"(\d+)\s+U\.S\.\s+(\d+)", "United States Reports"),
            CitationPattern("supreme_court", r"(\d+)\s+S\.\s*Ct\.\s+(\d+)", "Supreme Court Reporter"),
            CitationPattern("federal_reporter", r"(\d+)\s+F\.\s*(?:2d|3d|4th)?\s+(\d+)", "Federal Reporter"),
        ],
        legal_source_domains={
            "case_law": ["supremecourt.gov", "law.cornell.edu"],
            "statutes": ["uscode.house.gov"],
        },
        system_prompt_addition="You are specialized in United States law. Use proper US citation formats (Bluebook).",
        template_ids=[],
    ),
    "eu": JurisdictionConfig(
        id="eu", name="European Union", short_name="EU",
        citation_patterns=[
            CitationPattern("ecj", r"Case\s+C-(\d+/\d+)", "European Court of Justice"),
            CitationPattern("ecthr", r"App(?:lication)?\s+[Nn]o\.?\s+(\d+/\d+)", "European Court of Human Rights"),
        ],
        legal_source_domains={
            "case_law": ["curia.europa.eu", "hudoc.echr.coe.int"],
            "statutes": ["eur-lex.europa.eu"],
        },
        system_prompt_addition="You are specialized in EU law. Reference EU directives, regulations, and ECJ case law appropriately.",
        template_ids=[],
    ),
    "intl": JurisdictionConfig(
        id="intl", name="International", short_name="INTL",
        citation_patterns=[
            CitationPattern("icj", r"ICJ\s+Reports\s+(\d{4})", "International Court of Justice"),
            CitationPattern("rome_statute", r"(?:Rome\s+Statute|RS)\s+[Aa]rt(?:icle)?\.?\s*(\d+)", "Rome Statute article"),
        ],
        legal_source_domains={
            "case_law": ["icj-cij.org"],
            "statutes": ["treaties.un.org"],
        },
        system_prompt_addition="You are working with international law. Reference treaties and international court decisions appropriately.",
        template_ids=[],
    ),
}

def get_jurisdiction(jurisdiction_id: str) -> JurisdictionConfig | None:
    return JURISDICTIONS.get(jurisdiction_id.lower())

def list_jurisdictions() -> list[JurisdictionConfig]:
    return list(JURISDICTIONS.values())
