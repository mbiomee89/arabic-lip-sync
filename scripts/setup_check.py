"""Check that everything the skill needs is present. Installs and downloads nothing.

Usage: python setup_check.py [--model large-v3]
"""
import importlib.util
import os
import shutil
import sys
from pathlib import Path


def main():
    model = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else "large-v3"
    problems = []
    print(f"python {sys.version.split()[0]}")
    for exe in ("ffmpeg",):
        print(f"{exe}: {'ok' if shutil.which(exe) else 'MISSING'}")
        if not shutil.which(exe):
            problems.append(f"{exe} is not on PATH (install it from ffmpeg.org or a package manager)")
    for mod, pip in (("numpy", "numpy"), ("faster_whisper", "faster-whisper")):
        ok = importlib.util.find_spec(mod) is not None
        print(f"{mod}: {'ok' if ok else 'MISSING'}")
        if not ok:
            problems.append(f"python package {mod}: pip install {pip}")
    hub = Path(os.environ.get("HF_HUB_CACHE") or Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub")
    cached = list(hub.glob(f"models--*faster-whisper-{model}*")) if hub.exists() else []
    print(f"whisper model {model}: {'ok' if cached else 'NOT DOWNLOADED'}")
    if not cached:
        problems.append(f"Whisper model {model} is not downloaded (about 3 GB for large-v3; it downloads on first use "
                        f"without local_files_only). Ask the user before downloading. A smaller model: --model medium.")
    if problems:
        print("\nTo fix (ask the user before installing or downloading anything):")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print("\nAll set.")


if __name__ == "__main__":
    main()
