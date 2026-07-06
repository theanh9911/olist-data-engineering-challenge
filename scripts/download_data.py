"""
Download Olist Brazilian E-Commerce dataset from Kaggle.
Requires: kagglehub (installed via uv)
Usage: uv run python scripts/download_data.py
"""

import shutil
from pathlib import Path


def download_olist_dataset():
    """Download Olist dataset using kagglehub and copy to data/ directory."""
    try:
        import kagglehub
    except ImportError:
        print("ERROR: kagglehub is not installed.")
        print("Run: uv pip install kagglehub")
        return

    print("=" * 60)
    print("Downloading Olist Brazilian E-Commerce dataset...")
    print("=" * 60)

    # Download dataset
    dataset_path = kagglehub.dataset_download("olistbr/brazilian-ecommerce")
    print(f"\nDataset downloaded to: {dataset_path}")

    # Copy CSV files to project data/ directory
    project_root = Path(__file__).resolve().parent.parent
    data_dir = project_root / "data"
    data_dir.mkdir(exist_ok=True)

    csv_files = list(Path(dataset_path).glob("*.csv"))
    print(f"\nFound {len(csv_files)} CSV files. Copying to {data_dir}...")

    for csv_file in csv_files:
        dest = data_dir / csv_file.name
        shutil.copy2(csv_file, dest)
        size_mb = dest.stat().st_size / (1024 * 1024)
        print(f"  [OK] {csv_file.name} ({size_mb:.1f} MB)")

    print(f"\n{'=' * 60}")
    print(f"Done! {len(csv_files)} files copied to {data_dir}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    download_olist_dataset()
