import copy
import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seuss.config import ConfigError, validate_config
from seuss.defaults import DEFAULT_CONFIG_YAML


class ConfigValidationTests(unittest.TestCase):
    def _default_config(self) -> dict:
        return yaml.safe_load(DEFAULT_CONFIG_YAML)

    def test_default_config_is_valid(self) -> None:
        cfg = self._default_config()
        validate_config(cfg)

    def test_missing_required_section_raises(self) -> None:
        cfg = self._default_config()
        del cfg["generation"]
        with self.assertRaises(ConfigError):
            validate_config(cfg)

    def test_invalid_generation_level_raises(self) -> None:
        cfg = self._default_config()
        cfg["generation"]["default_level"] = "paragraph"
        with self.assertRaises(ConfigError):
            validate_config(cfg)

    def test_duplicate_source_names_raise(self) -> None:
        cfg = self._default_config()
        duplicate = copy.deepcopy(cfg["sources"][0])
        cfg["sources"].append(duplicate)
        with self.assertRaises(ConfigError):
            validate_config(cfg)

    def test_invalid_ratio_sum_raises(self) -> None:
        cfg = self._default_config()
        cfg["splits"]["train_ratio"] = 0.9
        cfg["splits"]["eval_ratio"] = 0.9
        with self.assertRaises(ConfigError):
            validate_config(cfg)


if __name__ == "__main__":
    unittest.main()
