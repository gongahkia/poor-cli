import importlib
import sys

from poor_cli.config import Config
from poor_cli.research_loader import load_research_module


def _clear_research_modules() -> None:
    for name in list(sys.modules):
        if name == "poor_cli.research" or name.startswith("poor_cli.research."):
            sys.modules.pop(name, None)


def test_research_modules_not_imported_by_default() -> None:
    _clear_research_modules()
    importlib.import_module("poor_cli")
    assert [name for name in sys.modules if name.startswith("poor_cli.research.")] == []


def test_feature_flag_enables_research_module() -> None:
    _clear_research_modules()
    config = Config()
    assert load_research_module("latent_communication", config=config) is None
    config.research.latent_communication.enabled = True
    module = load_research_module("latent_communication", config=config)
    assert module is not None
    assert module.__name__ == "poor_cli.research.latent_communication"
