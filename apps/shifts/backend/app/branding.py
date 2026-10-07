"""Filesystem location of the canonical brand assets in local and Docker layouts."""

from pathlib import Path

BRAND_DIR = Path(__file__).resolve().parents[4] / "packages" / "crr-brand"
LOGO_PATH = BRAND_DIR / "assets" / "logo.png"
