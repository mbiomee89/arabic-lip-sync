"""Check the tools THIS job needs (step 2). Installs and downloads nothing.

Usage: python setup_check.py [--job speech|song] [--voice none|edge|xtts|mmstts|elevenlabs]
                             [--no-whisper] [--model large-v3]
  --job song     also checks Demucs (vocal separation) and its model
  --voice X      also checks the voice tool the user chose (none = they have a recording)
  --no-whisper   skip Whisper (only when the user has the exact text and the voice needs no check)
  --mms          kept for old commands; MMS is always checked now
Prints what is ready and what is missing (with sizes); exit 1 when something is missing.
"""
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def hf_hub():
    return Path(os.environ.get("HF_HUB_CACHE") or Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub")


def main():
    job, voice, model = arg("--job", "speech"), arg("--voice", "none"), arg("--model", "large-v3")
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import mms   # needs numpy; when it is missing, the rows below say so instead of crashing
    except ImportError as e:
        mms, mms_error = None, e
    rows, problems = [], []

    def need(name, ok, fix):
        rows.append((name, ok))
        if not ok:
            problems.append(fix)

    print(f"job: {job}, voice: {voice}, python {sys.version.split()[0]}")
    need("ffmpeg / ffprobe", bool(shutil.which("ffmpeg") and shutil.which("ffprobe")),
         "ffmpeg and ffprobe on PATH (ffmpeg.org or a package manager)")
    for mod, pip, why in (("numpy", "numpy", "everything"), ("librosa", "librosa", "voice measuring: pitch, loudness, sh hiss, --sing"),
                          ("PIL", "Pillow", "mouth pictures: cut / check / fix")):
        need(f"{mod} ({why})", importlib.util.find_spec(mod) is not None, f"pip install {pip}  (small)")
    if mms is None:
        need("MMS aligner (checked once the packages above are installed)", False,
             f"install the missing packages above, then run this check again ({mms_error})")
    venv = Path(mms.VENV_PYTHON) if mms else Path("(not checked)")
    good = mms is not None and venv.exists() and subprocess.run([str(venv), "-c", "import torch, torchaudio"], capture_output=True).returncode == 0
    if mms: need(f"MMS aligner venv {venv}", good, f"torch + torchaudio venv at {venv} (about 730 MB; see references/mms_timing.md)")
    ckpt = Path(mms.TORCH_HOME) / "hub" / "checkpoints" / "model.pt" if mms else None
    if ckpt: need(f"MMS model {ckpt}", ckpt.exists(), f"MMS_FA model (1.2 GB) at {ckpt}; how to get it: references/mms_timing.md")
    if "--no-whisper" not in sys.argv:
        need("faster_whisper", importlib.util.find_spec("faster_whisper") is not None, "pip install faster-whisper  (small)")
        hub = hf_hub()
        cached = list(hub.glob(f"models--*faster-whisper-{model}*")) if hub.exists() else []
        need(f"Whisper model {model}", bool(cached), f"Whisper {model} (about 3 GB for large-v3; --model medium is smaller and rougher)")
    if job == "song":
        dm = venv.exists() and subprocess.run([str(venv), "-c", "import demucs"], capture_output=True).returncode == 0
        need("demucs (in the MMS venv)", dm, f"{venv} -m pip install --no-cache-dir demucs  (small; the model is separate)")
        hub = hf_hub()
        found = list(hub.glob("models--adefossez--HTDemucs/snapshots/*/*.safetensors")) if hub.exists() else []
        need("Demucs model htdemucs", bool(found), "the htdemucs model (about 80 MB) downloads on first use into the Hugging Face cache")
    if voice == "edge":
        need("edge-tts", importlib.util.find_spec("edge_tts") is not None, "pip install edge-tts  (small; online Microsoft voices)")
    elif voice == "xtts":
        need("TTS (Coqui XTTS v2)", importlib.util.find_spec("TTS") is not None, "pip install TTS + the XTTS v2 model (about 2 GB; a GPU helps)")
    elif voice == "mmstts":
        need("transformers (MMS-TTS ara)", importlib.util.find_spec("transformers") is not None, "pip install transformers + facebook/mms-tts-ara (small)")
    elif voice == "elevenlabs":
        rows.append(("ElevenLabs: through the connector (nothing to install; costs credits)", True))

    for name, ok in rows:
        print(f"  {'ok     ' if ok else 'MISSING'}  {name}")
    if problems:
        print("\nMissing for this job. Tell the user what and how big, and ASK before installing or downloading:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("\nAll set for this job.")


if __name__ == "__main__":
    main()
