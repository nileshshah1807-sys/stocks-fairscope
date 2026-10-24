"""Assemble the Hugging Face Space (Docker + Streamlit) for the browser version.

Usage: python packaging/huggingface/build_space.py [target-folder]   (default: space_build/)
Then upload the folder's contents to a new Docker Space, e.g. `hf upload <user>/<space> space_build . --repo-type space`.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
# The Streamlit page and every app module it imports (directly or through data_provider / pdf_report).
MODULES = ["streamlit_app.py", "data_provider.py", "sec_facts.py", "fundamentals.py", "india_sources.py", "local_database.py",
           "logger.py", "secure_storage.py", "ttl_cache.py", "valuation.py", "version.py", "pdf_report.py"]


def build(target: Path = ROOT / "space_build") -> Path:
    if target.exists():
        if not (target / "streamlit_app.py").exists():
            raise SystemExit(f"Refusing to replace {target}: it is not a previous Space build.")
        shutil.rmtree(target)
    (target / "assets").mkdir(parents=True)
    for name in MODULES:
        shutil.copy2(ROOT / name, target / name)
    shutil.copy2(ROOT / "assets" / "logo_256.png", target / "assets" / "logo_256.png")
    shutil.copy2(ROOT / "requirements-web.txt", target / "requirements.txt")
    for name in ("Dockerfile", "README.md"):
        shutil.copy2(HERE / name, target / name)
    return target


if __name__ == "__main__":
    print(build(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "space_build"))
