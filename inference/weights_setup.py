"""
One-time weights download script for the CubiCasa5k Modal Volume.

Run once before deploying the inference endpoint:
    modal run inference/weights_setup.py

The weights file (~200 MB) is stored in the 'cubicasa-weights' Modal Volume
at /weights/model_best_val_loss_var.pkl and mounted at /weights in the inference app.

If the Google Drive link expires, you can upload manually:
    modal volume put cubicasa-weights model_best_val_loss_var.pkl /model_best_val_loss_var.pkl
"""

import modal

CUBICASA_COMMIT = "c34440266665a11f4484eb06cd2e4b7d72ad76c1"
GDRIVE_FILE_ID = "1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK"
WEIGHTS_DEST = "/weights/model_best_val_loss_var.pkl"

# Minimal image — only needs gdown, no PyTorch or CubiCasa source required
download_image = (
    modal.Image.debian_slim()
    .pip_install(["gdown"])
)

app = modal.App("cubicasa-weights-setup")
volume = modal.Volume.from_name("cubicasa-weights", create_if_missing=True)


@app.function(volumes={"/weights": volume}, image=download_image, timeout=600)
def download_weights() -> None:
    """Download pretrained CubiCasa5k weights from Google Drive into the volume."""
    import os
    import gdown

    if os.path.exists(WEIGHTS_DEST):
        size_mb = os.path.getsize(WEIGHTS_DEST) / (1024 ** 2)
        print(f"Weights already present ({size_mb:.1f} MB). Delete and re-run to refresh.")
        return

    print(f"Downloading weights to {WEIGHTS_DEST} ...")
    url = f"https://drive.google.com/uc?id={GDRIVE_FILE_ID}"
    gdown.download(url, WEIGHTS_DEST, quiet=False)

    size_mb = os.path.getsize(WEIGHTS_DEST) / (1024 ** 2)
    print(f"Downloaded {size_mb:.1f} MB")

    volume.commit()
    print("Volume committed — weights are now available to the inference endpoint.")


@app.local_entrypoint()
def main() -> None:
    download_weights.remote()
