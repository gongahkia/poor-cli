from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium

from haus.pdf import calibrate_scale, load_page_texts, select_floorplan_page


PDF_PATH = Path("mount_pleasant_crest.pdf")


def test_select_floorplan_page_for_block_100a_unit_127_typical() -> None:
    texts = load_page_texts(str(PDF_PATH))
    match = select_floorplan_page(texts, block="100A", unit="127", storey_variant="typical")

    assert match.page_index == 22
    assert "29TH TO 35TH STOREY FLOOR PLAN" in match.page_text.upper()


def test_scale_calibration_returns_expected_range() -> None:
    doc = pdfium.PdfDocument(str(PDF_PATH))
    page = doc[22]

    calibration = calibrate_scale(page, render_scale=4.0)

    assert 0.03 < calibration.m_per_px < 0.05
    assert calibration.tick_std_error_cm < 2.0
