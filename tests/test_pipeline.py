from __future__ import annotations

from pathlib import Path

from haus.pipeline import run_extraction
from haus.types import ExtractionConfig


PDF_PATH = Path("mount_pleasant_crest.pdf")


def test_end_to_end_extraction_emits_glb_and_metadata(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    debug_dir = tmp_path / "debug"

    cfg = ExtractionConfig(
        pdf_path=PDF_PATH,
        block="100A",
        unit="127",
        out_dir=out_dir,
        storey_variant="typical",
        render_scale=3.0,
        debug_dir=debug_dir,
    )

    metadata = run_extraction(cfg)

    default_glb = out_dir / "block_100A_unit_127_default.glb"
    white_glb = out_dir / "block_100A_unit_127_white_flat.glb"
    metadata_json = out_dir / "block_100A_unit_127.metadata.json"

    assert default_glb.exists()
    assert white_glb.exists()
    assert metadata_json.exists()

    assert metadata["block"] == "100A"
    assert metadata["unit"] == "127"
    assert metadata["source_page_number_1_based"] == 23

    variants = metadata["variants"]
    assert "default" in variants
    assert "white_flat" in variants

    assert (debug_dir / "overlay.png").exists()
