from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from html import unescape
from pathlib import Path

GLOSSARY_FILENAMES = {
    "aus_law_handbook.json",
    "dv-glossary.json",
    "ip-glossary.json",
    "doj-glossaries.json",
    "parliamentary-glossary.json",
    "courts-glossary.json",
    "justice-glossary.json",
    "cpr_glossary.json",
    "fpr_glossary.json",
    "us-courts-glossary.json",
    "uscis-glossary.json",
    "usa_ca_criminal_glossary.json",
}

HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


@dataclass(slots=True)
class GlossaryEntry:
    phrase: str
    definition_html: str
    definition_text: str
    jurisdiction: str
    domain: str
    source_title: str
    source_url: str
    source_creator: str
    language: str
    license: str
    last_modified: str

    def to_document(self) -> dict[str, str]:
        return asdict(self)


def strip_html(value: str) -> str:
    if not value:
        return ""
    text = HTML_TAG_RE.sub(" ", value)
    text = unescape(text)
    return WHITESPACE_RE.sub(" ", text).strip()


def infer_domain(filepath: str | Path, metadata: dict) -> str:
    stem = Path(filepath).stem.lower()
    domain_map = {
        "aus_law_handbook": "general",
        "dv-glossary": "domestic_violence",
        "ip-glossary": "intellectual_property",
        "doj-glossaries": "criminal",
        "parliamentary-glossary": "parliamentary",
        "courts-glossary": "courts",
        "justice-glossary": "justice",
        "cpr_glossary": "civil_procedure",
        "fpr_glossary": "family_procedure",
        "us-courts-glossary": "federal_courts",
        "uscis-glossary": "immigration",
        "usa_ca_criminal_glossary": "criminal",
    }
    domain = domain_map.get(stem, "general")
    title = str(metadata.get("dcterms:title", "")).lower()

    if stem == "doj-glossaries":
        if "family" in title or "spousal" in title or "parenting" in title:
            return "family"
        if "victim" in title:
            return "victims"
        if "criminal" in title:
            return "criminal"
        return "general"

    if domain == "general":
        subjects = metadata.get("dcterms:subject", [])
        labels = []
        for subject in subjects if isinstance(subjects, list) else []:
            if isinstance(subject, dict):
                labels.append(str(subject.get("rdfs:label", "")).lower())
        joined = " ".join(labels)
        if "immigration" in joined:
            return "immigration"
        if "criminal" in joined:
            return "criminal"
        if "family" in joined:
            return "family"

    return domain


def infer_jurisdiction(filepath: str | Path, metadata: dict) -> str:
    if Path(filepath).name == "usa_ca_criminal_glossary.json":
        return "USA-CA"
    return str(metadata.get("dcterms:coverage", "UNKNOWN"))


def parse_glossary_file(filepath: str | Path) -> list[GlossaryEntry]:
    with Path(filepath).open(encoding="utf-8") as handle:
        data = json.load(handle)

    objects = data if isinstance(data, list) else [data]
    entries: list[GlossaryEntry] = []

    for glossary_object in objects:
        if not isinstance(glossary_object, dict):
            continue
        metadata = glossary_object.get("metadata", {}) if isinstance(glossary_object, dict) else {}
        source_entries = glossary_object.get("entries", []) if isinstance(glossary_object, dict) else []

        domain = infer_domain(filepath, metadata)
        jurisdiction = infer_jurisdiction(filepath, metadata)

        for raw_entry in source_entries if isinstance(source_entries, list) else []:
            if not isinstance(raw_entry, dict):
                continue
            phrase = str(raw_entry.get("phrase", "")).strip()
            definition_html = str(raw_entry.get("definition", "")).strip()
            if not phrase or not definition_html:
                continue
            definition_text = strip_html(definition_html)
            if not definition_text:
                continue

            entries.append(
                GlossaryEntry(
                    phrase=phrase,
                    definition_html=definition_html,
                    definition_text=definition_text,
                    jurisdiction=jurisdiction,
                    domain=domain,
                    source_title=str(metadata.get("dcterms:title", "")),
                    source_url=str(metadata.get("dcterms:source", "")),
                    source_creator=str(metadata.get("publiclaw:sourceCreator", "")),
                    language=str(metadata.get("dcterms:language", "en")),
                    license=str(metadata.get("dcterms:license", "")),
                    last_modified=str(metadata.get("dcterms:modified", "")),
                )
            )

    return entries


def discover_glossary_files(dataset_root: str | Path) -> list[Path]:
    root = Path(dataset_root)
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.json") if path.name in GLOSSARY_FILENAMES)


def discover_dataset_root() -> Path:
    candidates = [
        Path("datasets"),
        Path("vendor-data/datasets"),
        Path("../vendor-data/datasets"),
        Path("../../vendor-data/datasets"),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return Path("vendor-data/datasets")
