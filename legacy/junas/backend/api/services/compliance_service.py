"""Compliance checking service ported from Junas compliance/rules.ts."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class ComplianceRule:
    id: str
    name: str
    category: str
    description: str
    keywords: list[str]
    severity: str  # high | medium | low

@dataclass
class ComplianceCheckResult:
    rule_id: str
    rule_name: str
    status: str  # pass | warning | fail
    details: str
    severity: str

DEFAULT_SG_RULES: list[ComplianceRule] = [
    ComplianceRule("pdpa-consent", "PDPA Consent Clause", "Data Protection", "Document must reference consent for personal data collection under PDPA", ["consent", "personal data", "pdpa", "data protection"], "high"),
    ComplianceRule("pdpa-purpose", "PDPA Purpose Limitation", "Data Protection", "Data usage purpose must be clearly stated", ["purpose", "personal data", "collection", "use", "disclosure"], "high"),
    ComplianceRule("governing-law", "Governing Law Clause", "General", "Contract must specify governing law", ["governing law", "governed by", "laws of"], "medium"),
    ComplianceRule("dispute-resolution", "Dispute Resolution", "General", "Contract must include dispute resolution mechanism", ["dispute resolution", "arbitration", "mediation", "jurisdiction"], "medium"),
    ComplianceRule("termination", "Termination Clause", "General", "Contract must include termination provisions", ["termination", "terminate", "notice period"], "medium"),
    ComplianceRule("indemnification", "Indemnification", "Liability", "Indemnification provisions should be present", ["indemnify", "indemnification", "hold harmless"], "low"),
    ComplianceRule("force-majeure", "Force Majeure", "Risk", "Force majeure clause should be present for risk allocation", ["force majeure", "act of god", "unforeseeable", "beyond control"], "low"),
    ComplianceRule("confidentiality", "Confidentiality", "General", "Confidentiality obligations should be specified", ["confidential", "confidentiality", "non-disclosure", "proprietary"], "medium"),
    ComplianceRule("employment-act-notice", "Employment Act Notice Period", "Employment", "Employment contracts must comply with notice period requirements", ["notice period", "termination notice", "employment act"], "high"),
    ComplianceRule("cpf-contribution", "CPF Contribution Reference", "Employment", "Employment contracts should reference CPF obligations", ["cpf", "central provident fund", "employer contribution"], "medium"),
]

DEFAULT_MY_RULES: list[ComplianceRule] = [
    ComplianceRule("pdpa-consent-my", "PDPA Consent Clause (Malaysia)", "Data Protection", "Document should reference consent requirements under Malaysia PDPA 2010", ["consent", "personal data", "pdpa"], "high"),
    ComplianceRule("pdpa-disclosure-my", "PDPA Disclosure Limitation (Malaysia)", "Data Protection", "Personal data disclosure limits should be specified", ["disclosure", "personal data", "data user"], "high"),
    ComplianceRule("governing-law", "Governing Law Clause", "General", "Contract must specify governing law", ["governing law", "governed by", "laws of"], "medium"),
    ComplianceRule("dispute-resolution", "Dispute Resolution", "General", "Contract must include dispute resolution mechanism", ["dispute resolution", "arbitration", "mediation", "jurisdiction"], "medium"),
    ComplianceRule("employment-act-my", "Employment Act 1955 Reference", "Employment", "Employment contracts should align with Employment Act 1955", ["employment act 1955", "termination", "notice"], "high"),
    ComplianceRule("epf-contribution-my", "EPF Contribution Reference", "Employment", "Employment contracts should reference EPF obligations", ["epf", "employees provident fund", "employer contribution"], "medium"),
    ComplianceRule("termination", "Termination Clause", "General", "Contract must include termination provisions", ["termination", "terminate", "notice period"], "medium"),
]

DEFAULT_US_RULES: list[ComplianceRule] = [
    ComplianceRule("governing-law-us", "Governing Law Clause (US)", "General", "Contract should define governing state law", ["governing law", "state of", "laws of"], "high"),
    ComplianceRule("dispute-resolution-us", "Dispute Resolution (US)", "General", "Contract should define forum, venue, or arbitration process", ["forum", "venue", "arbitration", "jurisdiction"], "high"),
    ComplianceRule("privacy-notice-us", "Privacy Notice Reference (US)", "Data Protection", "Document should include privacy notice language where personal data is processed", ["privacy policy", "personal information", "notice"], "medium"),
    ComplianceRule("confidentiality", "Confidentiality", "General", "Confidentiality obligations should be specified", ["confidential", "confidentiality", "non-disclosure", "proprietary"], "medium"),
    ComplianceRule("limitation-liability-us", "Limitation of Liability", "Liability", "Contract should define liability caps or exclusions", ["limitation of liability", "liability cap", "consequential damages"], "medium"),
    ComplianceRule("termination", "Termination Clause", "General", "Contract must include termination provisions", ["termination", "terminate", "notice period"], "medium"),
]

_JURISDICTION_ALIASES = {
    "sg": "sg",
    "singapore": "sg",
    "my": "my",
    "malaysia": "my",
    "us": "us",
    "usa": "us",
    "united states": "us",
}

_JURISDICTION_RULES = {
    "sg": DEFAULT_SG_RULES,
    "my": DEFAULT_MY_RULES,
    "us": DEFAULT_US_RULES,
}


def normalize_jurisdiction(value: str | None) -> str:
    normalized = str(value or "sg").strip().lower()
    return _JURISDICTION_ALIASES.get(normalized, "sg")


def get_default_rules(jurisdiction: str | None = "sg") -> list[ComplianceRule]:
    resolved = normalize_jurisdiction(jurisdiction)
    return list(_JURISDICTION_RULES.get(resolved, DEFAULT_SG_RULES))

def check_compliance(text: str, rules: list[ComplianceRule] | None = None) -> list[ComplianceCheckResult]:
    if rules is None:
        rules = DEFAULT_SG_RULES
    lower = text.lower()
    results: list[ComplianceCheckResult] = []
    for rule in rules:
        match_count = sum(1 for kw in rule.keywords if kw.lower() in lower)
        ratio = match_count / len(rule.keywords) if rule.keywords else 0
        if ratio >= 0.5:
            status = "pass"
            details = f"Found {match_count}/{len(rule.keywords)} expected keywords"
        elif ratio > 0:
            status = "warning"
            details = f"Partial match: {match_count}/{len(rule.keywords)} keywords found"
        else:
            status = "fail"
            details = f"No matching keywords found — {rule.description}"
        results.append(ComplianceCheckResult(rule.id, rule.name, status, details, rule.severity))
    return results
