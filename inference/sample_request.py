"""
Local test script for the CubiCasa5k Modal inference endpoint.

Usage:
    python inference/sample_request.py <endpoint_url> <path/to/floorplan.png>

Example:
    python inference/sample_request.py \\
        https://zanechee--cubicasa-inference-floorplaninference-predict.modal.run \\
        tests/fixtures/sample_floorplan.png

The endpoint URL is printed by `modal serve` or `modal deploy`.
"""

import sys
import base64
from collections import Counter
from io import BytesIO

import requests
from PIL import Image


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    url, img_path = sys.argv[1], sys.argv[2]

    print(f"Sending {img_path} to {url} ...")
    with open(img_path, "rb") as f:
        response = requests.post(url, files={"image": f}, timeout=360)

    if not response.ok:
        print(f"Error {response.status_code}: {response.text}")
        sys.exit(1)

    data = response.json()

    # --- Timing ---
    print(f"Inference:      {data['inference_time_ms']} ms")
    print(f"Post-process:   {data['postprocess_time_ms']} ms")

    # --- Vector geometry ---
    print(f"\nWalls detected:    {data['wall_count']}")
    print(f"Openings detected: {data['opening_count']}")
    windows = [o for o in data["openings"] if o["class"] == 1]
    doors   = [o for o in data["openings"] if o["class"] == 2]
    print(f"  Windows: {len(windows)}  Doors: {len(doors)}")

    # --- Segmentation summary ---
    room_classes = data["room_classes"]
    icon_classes = data["icon_classes"]
    room_counts = Counter(cell for row in data["room_map"] for cell in row)
    icon_counts = Counter(cell for row in data["icon_map"]  for cell in row)

    print("\nRoom segmentation (top 5 by pixel count):")
    for cls_idx, count in room_counts.most_common(5):
        label = room_classes.get(str(cls_idx), f"class_{cls_idx}")
        pct = count / (256 * 256) * 100
        print(f"  {label:<20} {count:>6} px  ({pct:.1f}%)")

    print("\nIcon segmentation (non-background):")
    for cls_idx, count in icon_counts.most_common():
        if cls_idx == 0:
            continue
        label = icon_classes.get(str(cls_idx), f"class_{cls_idx}")
        pct = count / (256 * 256) * 100
        print(f"  {label:<20} {count:>6} px  ({pct:.1f}%)")

    # --- Save previews ---
    for key, filename in [
        ("segmentation_preview", "preview_seg.png"),
        ("vector_clean",         "preview_vector_clean.png"),
        ("vector_overlay",       "preview_vector_overlay.png"),
    ]:
        img_bytes = base64.b64decode(data[key])
        Image.open(BytesIO(img_bytes)).save(filename)
        print(f"\nSaved {filename}")


if __name__ == "__main__":
    main()
