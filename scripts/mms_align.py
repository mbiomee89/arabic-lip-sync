"""Letter-exact forced alignment with Meta's MMS aligner (torchaudio MMS_FA). Runs in the torch venv.

Usage (called by lipsync.py --aligner mms; not normally run by hand):
  <venv python> mms_align.py <16 kHz mono wav> <tokens.json> <out.json>

tokens.json: {"units": ["ba", "", "aa", ...]}: the Latin letters for each sound of the script, in
order ("" = a sound with no letter of its own, e.g. a silent ة; it is skipped here).
out.json:    {"frame": seconds per emission frame,
              "units": [null | {"start", "end", "score", "letters": [[start, end, score], ...]}]}
Every span start is when that sound starts (CTC spans are short peaks, so only the starts are onsets).

Model: torchaudio's MMS_FA checkpoint, read from TORCH_HOME (default ~/.cache/torch:
hub/checkpoints/model.pt). It is never downloaded here: if it is missing this stops
(how to get it: references/mms_timing.md).
"""
import json
import os
import sys
import wave
from pathlib import Path

os.environ.setdefault("TORCH_HOME", str(Path.home() / ".cache" / "torch"))

import numpy as np
import torch
import torchaudio

CHUNK = 20.0     # seconds of audio per pass through the model (attention memory grows with length squared)
CONTEXT = 1.0    # extra audio each side of a chunk, thrown away after, so chunk edges hear their neighbours


def emissions(model, wav, sr=16000):
    """Log-probabilities per 20 ms frame for the whole file, computed in overlapping chunks."""
    n = wav.size(1)
    if n <= (CHUNK + 2 * CONTEXT) * sr:
        with torch.inference_mode():
            em, _ = model(wav)
        return em[0]
    step, ctx = int(CHUNK * sr), int(CONTEXT * sr)
    parts = []
    with torch.inference_mode():
        for s in range(0, n, step):
            a, b = max(0, s - ctx), min(n, s + step + ctx)
            em, _ = model(wav[:, a:b])
            em = em[0]
            per = (b - a) / em.size(0)          # samples per frame in this chunk
            k0 = int(round((s - a) / per))
            k1 = int(round((min(n, s + step) - a) / per))
            parts.append(em[k0:k1])
    return torch.cat(parts)


def main():
    wav_path, tok_path, out_path = sys.argv[1:4]
    ckpt = Path(os.environ["TORCH_HOME"]) / "hub" / "checkpoints" / "model.pt"
    if not ckpt.exists():
        sys.exit(f"MMS model not found at {ckpt}. It is about 1.2 GB; ask the user before downloading it.")
    units = json.loads(Path(tok_path).read_text(encoding="utf-8"))["units"]

    with wave.open(wav_path) as w:
        sr = w.getframerate()
        audio = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    if sr != 16000:
        sys.exit("expected 16 kHz mono audio")
    wav = torch.from_numpy(audio)[None]

    bundle = torchaudio.pipelines.MMS_FA
    model = bundle.get_model(with_star=False)
    model.eval()
    tokenizer, aligner = bundle.get_tokenizer(), bundle.get_aligner()

    em = emissions(model, wav)
    frame = wav.size(1) / em.size(0) / 16000
    said = [u for u in units if u]
    spans = aligner(em, tokenizer(said))
    out, k = [], 0
    for u in units:
        if not u:
            out.append(None)
            continue
        letters = [[round(s.start * frame, 3), round(s.end * frame, 3), round(float(s.score), 3)] for s in spans[k]]
        k += 1
        out.append({"start": letters[0][0], "end": letters[-1][1],
                    "score": round(float(np.mean([l[2] for l in letters])), 3), "letters": letters})
    Path(out_path).write_text(json.dumps({"frame": frame, "units": out}), encoding="utf-8")


if __name__ == "__main__":
    main()
