from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import Any

FINE_ENTITY_TYPES = [
    {"tag": "PER", "label": "Person", "description": "Person names", "category": "Person"},
    {"tag": "RR", "label": "Judge", "description": "Judge names (Richter)", "category": "Person"},
    {"tag": "AN", "label": "Lawyer", "description": "Lawyer names (Anwalt)", "category": "Person"},
    {"tag": "LD", "label": "Country", "description": "Country names", "category": "Location"},
    {"tag": "ST", "label": "City", "description": "City names", "category": "Location"},
    {"tag": "STR", "label": "Street", "description": "Street names", "category": "Location"},
    {"tag": "LDS", "label": "Region", "description": "Landscape and region names", "category": "Location"},
    {"tag": "ORG", "label": "Organization", "description": "Organization names", "category": "Organization"},
    {"tag": "UN", "label": "Company", "description": "Company names", "category": "Organization"},
    {"tag": "INN", "label": "Institution", "description": "Institution names", "category": "Organization"},
    {"tag": "GRT", "label": "Legal norm", "description": "Legal norms and standards", "category": "Legal"},
    {"tag": "MRK", "label": "Brand", "description": "Brand names", "category": "Legal"},
    {"tag": "GS", "label": "Law", "description": "Laws and acts (Gesetz)", "category": "Legal"},
    {"tag": "VO", "label": "Regulation", "description": "Regulations (Verordnung)", "category": "Legal"},
    {"tag": "EUN", "label": "EU norm", "description": "EU regulations and norms", "category": "Legal"},
    {"tag": "VS", "label": "Directive", "description": "Ordinances and directives", "category": "Legal"},
    {"tag": "VT", "label": "Treaty", "description": "Treaties and agreements", "category": "Legal"},
    {"tag": "RS", "label": "Court decision", "description": "Court decisions and references", "category": "Legal"},
    {"tag": "LIT", "label": "Literature", "description": "Literary works", "category": "Legal"},
]

ENTITY_LABELS_EN = {
    "PER": "Person",
    "RR": "Judge",
    "AN": "Attorney/Lawyer",
    "LD": "Country",
    "ST": "City",
    "STR": "Street/Address",
    "LDS": "Region/Territory",
    "ORG": "Organization",
    "UN": "Company/Corporation",
    "INN": "Institution",
    "GRT": "Constitutional Right/Norm",
    "MRK": "Trademark/Brand",
    "GS": "Statute/Act",
    "VO": "Regulation",
    "EUN": "EU Regulation",
    "VS": "Directive/Ordinance",
    "VT": "Treaty/Convention",
    "RS": "Case Citation/Court Decision",
    "LIT": "Legal Publication/Commentary",
}

COARSE_ENTITY_TYPES = [
    {"tag": "PER", "label": "Person", "members": ["PER", "RR", "AN"]},
    {"tag": "LOC", "label": "Location", "members": ["LD", "ST", "STR", "LDS"]},
    {"tag": "ORG", "label": "Organization", "members": ["ORG", "UN", "INN"]},
    {"tag": "NRM", "label": "Legal norm", "members": ["GRT", "MRK"]},
    {"tag": "REG", "label": "Regulation", "members": ["GS", "VO", "EUN", "VS", "VT"]},
    {"tag": "RS", "label": "Court decision", "members": ["RS"]},
    {"tag": "LIT", "label": "Literature", "members": ["LIT"]},
]

COARSE_MAP = {
    "PER": "PER",
    "RR": "PER",
    "AN": "PER",
    "LD": "LOC",
    "ST": "LOC",
    "STR": "LOC",
    "LDS": "LOC",
    "ORG": "ORG",
    "UN": "ORG",
    "INN": "ORG",
    "GRT": "NRM",
    "MRK": "NRM",
    "GS": "REG",
    "VO": "REG",
    "EUN": "REG",
    "VS": "REG",
    "VT": "REG",
    "RS": "RS",
    "LIT": "LIT",
}

FINE_LABEL_BY_TAG = {row["tag"]: row["label"] for row in FINE_ENTITY_TYPES}
COARSE_LABEL_BY_TAG = {row["tag"]: row["label"] for row in COARSE_ENTITY_TYPES}

NORMALIZE_WHITESPACE_RE = re.compile(r"\s+")
GAZETTEER_TAGS = {
    "firmennamen.list": "UN",
    "gesetzesnamen.list": "GS",
    "laendernamen.list": "LD",
    "landschaftsbezeichnungen.list": "LDS",
    "personennamen.list": "PER",
    "stadtnamen.list": "ST",
    "strassennamen.list": "STR",
    "verordnungsnamen.list": "VO",
    "vorschriftennamen.list": "VS",
}


def normalize_text(value: str) -> str:
    return NORMALIZE_WHITESPACE_RE.sub(" ", value.strip().lower())


def discover_model_path() -> Path:
    candidates = [
        Path("models/ner-german-legal/best"),
        Path("junas/models/ner-german-legal/best"),
        Path("../models/ner-german-legal/best"),
        Path("../junas/models/ner-german-legal/best"),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return Path("models/ner-german-legal/best")


def discover_multilingual_model_path() -> Path:
    candidates = [
        Path("models/ner-multilingual-legal/best"),
        Path("junas/models/ner-multilingual-legal/best"),
        Path("../models/ner-multilingual-legal/best"),
        Path("../junas/models/ner-multilingual-legal/best"),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return Path("models/ner-multilingual-legal/best")


def discover_gazetteer_dir() -> Path:
    candidates = [
        Path("Legal-Entity-Recognition/gazetteers"),
        Path("vendor-data/Legal-Entity-Recognition/gazetteers"),
        Path("../vendor-data/Legal-Entity-Recognition/gazetteers"),
        Path("../../vendor-data/Legal-Entity-Recognition/gazetteers"),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return Path("vendor-data/Legal-Entity-Recognition/gazetteers")


def _optional_import(module_name: str, attr_name: str | None = None) -> Any:
    module = importlib.import_module(module_name)
    if attr_name is None:
        return module
    return getattr(module, attr_name)


class GazetteerMatcher:
    def __init__(self, gazetteer_dir: str | Path):
        self.gazetteers: dict[str, set[str]] = {}
        self.entry_to_types: dict[str, set[str]] = {}

        path = Path(gazetteer_dir)
        if not path.exists() or not path.is_dir():
            return

        for filename, entity_type in GAZETTEER_TAGS.items():
            filepath = path / filename
            if not filepath.exists() or not filepath.is_file():
                continue

            entries: set[str] = set()
            with filepath.open(encoding="utf-8", errors="replace") as handle:
                for raw_line in handle:
                    normalized = normalize_text(raw_line)
                    if not normalized:
                        continue
                    entries.add(normalized)
                    self.entry_to_types.setdefault(normalized, set()).add(entity_type)

            if entries:
                self.gazetteers[entity_type] = entries

    def check(self, text: str) -> list[tuple[str, str]]:
        normalized = normalize_text(text)
        entity_types = sorted(self.entry_to_types.get(normalized, set()))
        return [(text, entity_type) for entity_type in entity_types]


class EntityExtractor:
    def __init__(
        self,
        pipeline_obj: Any,
        model_name: str,
        gazetteer: GazetteerMatcher,
        multilingual_pipeline: Any = None,
        multilingual_model_name: str | None = None,
    ):
        self.ner_pipeline = pipeline_obj
        self.model_name = model_name
        self.gazetteer = gazetteer
        self.multilingual_pipeline = multilingual_pipeline
        self.multilingual_model_name = multilingual_model_name

    @staticmethod
    def _load_ner_pipeline(model_dir: Path) -> tuple[Any, str]:
        AutoModelForTokenClassification = _optional_import("transformers", "AutoModelForTokenClassification")
        AutoTokenizer = _optional_import("transformers", "AutoTokenizer")
        pipeline = _optional_import("transformers", "pipeline")

        tokenizer = AutoTokenizer.from_pretrained(model_dir)
        model = AutoModelForTokenClassification.from_pretrained(model_dir)
        pipeline_obj = pipeline(
            "ner",
            model=model,
            tokenizer=tokenizer,
            aggregation_strategy="simple",
        )
        inferred_name = model_dir.parent.name if model_dir.name == "best" else model_dir.name
        return pipeline_obj, (inferred_name or "ner-model")

    @classmethod
    def from_paths(
        cls,
        model_path: str | Path,
        gazetteer_dir: str | Path,
        multilingual_model_path: str | Path | None = None,
    ) -> EntityExtractor:
        model_dir = Path(model_path)
        if not model_dir.exists() or not model_dir.is_dir():
            raise RuntimeError(f"NER model path is missing: {model_dir}")

        try:
            pipeline_obj, model_name = cls._load_ner_pipeline(model_dir)
        except ModuleNotFoundError as exc:  # pragma: no cover - runtime dependency
            raise RuntimeError("transformers is not installed") from exc

        multilingual_pipeline = None
        multilingual_model_name: str | None = None
        if multilingual_model_path is not None:
            multilingual_dir = Path(multilingual_model_path)
            if multilingual_dir.exists() and multilingual_dir.is_dir():
                try:
                    multilingual_pipeline, multilingual_model_name = cls._load_ner_pipeline(multilingual_dir)
                except Exception:
                    multilingual_pipeline = None
                    multilingual_model_name = None

        return cls(
            pipeline_obj=pipeline_obj,
            model_name=model_name,
            gazetteer=GazetteerMatcher(gazetteer_dir),
            multilingual_pipeline=multilingual_pipeline,
            multilingual_model_name=multilingual_model_name,
        )

    def get_entity_types(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "fine_grained": list(FINE_ENTITY_TYPES),
            "coarse_grained": list(COARSE_ENTITY_TYPES),
        }

    def model_name_for_language(self, language: str) -> str:
        if language == "en" and self.multilingual_pipeline is not None and self.multilingual_model_name:
            return self.multilingual_model_name
        return self.model_name

    def extract(
        self,
        text: str,
        granularity: str = "fine",
        use_gazetteer: bool = True,
        language: str = "de",
    ) -> list[dict[str, Any]]:
        if granularity not in {"fine", "coarse"}:
            raise ValueError("granularity must be 'fine' or 'coarse'")
        if language not in {"de", "en"}:
            raise ValueError("language must be 'de' or 'en'")

        pipeline_obj = self.ner_pipeline
        if language == "en" and self.multilingual_pipeline is not None:
            pipeline_obj = self.multilingual_pipeline

        raw_entities = pipeline_obj(text)
        entities: list[dict[str, Any]] = []

        for raw in raw_entities:
            fine_type = str(raw.get("entity_group", "")).upper()
            if not fine_type:
                continue
            confidence = float(raw.get("score", 0.0))
            entity: dict[str, Any] = {
                "text": str(raw.get("word", "")).strip(),
                "type": fine_type,
                "start": int(raw.get("start", 0)),
                "end": int(raw.get("end", 0)),
                "confidence": round(confidence, 4),
                "language": language,
            }
            entities.append(entity)

        entities.sort(key=lambda row: (row["start"], row["end"]))

        if use_gazetteer and language == "de":
            entities = self._apply_gazetteer(entities)

        if granularity == "coarse":
            for entity in entities:
                coarse_type = COARSE_MAP.get(entity["type"], entity["type"])
                entity["type"] = coarse_type
                entity["type_label"] = COARSE_LABEL_BY_TAG.get(coarse_type, coarse_type)
        else:
            label_map = ENTITY_LABELS_EN if language == "en" else FINE_LABEL_BY_TAG
            for entity in entities:
                fine_type = entity["type"]
                entity["type_label"] = label_map.get(fine_type, fine_type)

        return entities

    def _apply_gazetteer(self, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for entity in entities:
            matches = self.gazetteer.check(entity["text"])
            if not matches:
                continue

            gazetteer_types = [entity_type for _, entity_type in matches]
            if entity["type"] in gazetteer_types:
                entity["confidence"] = round(min(entity["confidence"] + 0.05, 1.0), 4)
            else:
                entity["type"] = gazetteer_types[0]
                entity["confidence"] = round(min(entity["confidence"] + 0.03, 1.0), 4)
                entity["gazetteer_corrected"] = True
            entity["gazetteer_match"] = True

        return entities


def create_entity_extractor(
    model_path: str | Path | None = None,
    gazetteer_dir: str | Path | None = None,
    multilingual_model_path: str | Path | None = None,
) -> EntityExtractor | None:
    if model_path is None:
        resolved_model_path = discover_model_path()
    else:
        configured_model_path = Path(model_path)
        resolved_model_path = (
            configured_model_path
            if configured_model_path.exists() and configured_model_path.is_dir()
            else discover_model_path()
        )
    if not resolved_model_path.exists() or not resolved_model_path.is_dir():
        return None

    if gazetteer_dir is None:
        resolved_gazetteer_dir = discover_gazetteer_dir()
    else:
        configured_gazetteer_dir = Path(gazetteer_dir)
        resolved_gazetteer_dir = (
            configured_gazetteer_dir
            if configured_gazetteer_dir.exists() and configured_gazetteer_dir.is_dir()
            else discover_gazetteer_dir()
        )

    resolved_multilingual_model_path: Path | None
    if multilingual_model_path is None:
        discovered = discover_multilingual_model_path()
        resolved_multilingual_model_path = discovered if discovered.exists() and discovered.is_dir() else None
    else:
        candidate = Path(multilingual_model_path)
        resolved_multilingual_model_path = candidate if candidate.exists() and candidate.is_dir() else None

    return EntityExtractor.from_paths(
        model_path=resolved_model_path,
        gazetteer_dir=resolved_gazetteer_dir,
        multilingual_model_path=resolved_multilingual_model_path,
    )
