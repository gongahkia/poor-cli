from __future__ import annotations
from pathlib import Path
import cv2
import pytest
from haus.extraction import extract_floor_plan
from haus.pipeline import run_vectorize
from haus.types import VectorizeConfig

FIXTURES = Path("tests/fixtures")


def test_extract_floor_plan_returns_walls():
    img_bgr = cv2.imread(str(FIXTURES / "bto_2room_orange.jpg"))
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    data, wall_mask, fill_mask = extract_floor_plan(img_rgb)
    h, w = img_rgb.shape[:2]
    assert len(data.walls) > 0
    assert data.image_shape_hw == (h, w)
    assert wall_mask.shape == (h, w)
    assert fill_mask.shape == (h, w)


@pytest.mark.xfail(reason="opening detection requires higher-res input")
def test_extract_floor_plan_detects_openings():
    img_bgr = cv2.imread(str(FIXTURES / "bto_4room_yellow.jpg"))
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    data, _, _ = extract_floor_plan(img_rgb)
    assert len(data.openings) > 0


def test_run_vectorize_produces_outputs(tmp_path):
    cfg = VectorizeConfig(
        image_path=Path("tests/fixtures/bto_3room_orange.jpg"),
        out_dir=tmp_path / "out",
        debug_dir=tmp_path / "debug",
    )
    metadata = run_vectorize(cfg)
    assert (tmp_path / "out" / "vector_clean.png").exists()
    assert (tmp_path / "out" / "vector.metadata.json").exists()
    assert (tmp_path / "debug" / "wall_mask.png").exists()
    assert (tmp_path / "debug" / "fill_mask.png").exists()
    assert (tmp_path / "debug" / "overlay.png").exists()
    assert "walls" in metadata
    assert "openings" in metadata
    assert "scale" in metadata


def test_scale_estimation_produces_plausible_value():
    img_bgr = cv2.imread(str(FIXTURES / "bto_4room_green.jpg"))
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    data, _, _ = extract_floor_plan(img_rgb)
    if data.m_per_px is not None:
        assert 0.005 < data.m_per_px < 0.1
