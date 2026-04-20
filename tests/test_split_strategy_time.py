import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seuss.commands.ingest_cmd import run_ingest
from seuss.commands.init_cmd import run_init
from seuss.jsonl_store import read_jsonl


class SplitStrategyTimeTests(unittest.TestCase):
    def test_time_strategy_prefers_earlier_records_for_train(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "seuss.yaml"
            self.assertEqual(run_init(config_path=config_path, force=False), 0)

            chat_path = root / "data" / "chat_export.jsonl"
            chat_path.parent.mkdir(parents=True, exist_ok=True)
            rows = [
                {"text": "alpha beta.", "speaker": "user", "timestamp": "2025-01-01T00:00:00Z"},
                {"text": "gamma zeta.", "speaker": "user", "timestamp": "2025-01-02T00:00:00Z"},
            ]
            chat_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            cfg["splits"]["strategy"] = "time"
            cfg["splits"]["train_ratio"] = 0.5
            for source in cfg["sources"]:
                if source["name"] == "notes":
                    source["enabled"] = False
                if source["name"] == "chat_export":
                    source["enabled"] = True
            config_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

            self.assertEqual(
                run_ingest(
                    config_path=config_path,
                    source_name="chat_export",
                    direct_path=None,
                    dry_run=False,
                    rebuild=True,
                ),
                0,
            )

            fragments = read_jsonl(root / ".seuss" / "corpus" / "fragments.jsonl")
            train_ts = []
            eval_ts = []
            for row in fragments:
                ts = row.get("event_timestamp")
                if not ts:
                    continue
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if row.get("split") == "train":
                    train_ts.append(dt)
                if row.get("split") == "eval":
                    eval_ts.append(dt)

            self.assertTrue(train_ts)
            self.assertTrue(eval_ts)
            self.assertLessEqual(max(train_ts), min(eval_ts))


if __name__ == "__main__":
    unittest.main()
