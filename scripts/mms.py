"""--aligner mms: letter-exact timing from Meta's MMS forced aligner, for songs, long vowels and dialect.

The vowel-marked script is turned into the skill's own sounds (rules.units), each written in Latin
letters (translit.py), and aligned to the audio by MMS in the torch venv (mms_align.py). Every
sound then gets its time:
  - it starts at its aligned onset, corrected by the sound the same way for every letter of a kind:
    stops and nasals end where the sound bursts open, hissing letters start where the hiss rises;
  - a vowel holds until the next sound starts, so it covers the whole held note;
  - a word (a sung note) ends where real voicing stops: pyin's voiced flag AND a level above
    (loudest - 24 dB), with gaps under 0.08 s bridged. Reverb tails are below that level;
  - a word-final consonant goes at the END of the note (the vowel is held, then the closure / f /
    hiss), never in the middle of a held vowel;
  - silent or unaligned gaps longer than 0.08 s become rest.
Mouths, the one-frame minimum and the smooth track are the skill's own (align.py), unchanged.
"""
import json
import os
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

import align
import rules
import translit

VENV_PYTHON = os.environ.get("LIPSYNC_MMS_PYTHON", str(Path.home() / "envs" / "lipsync-mms" /
                             ("Scripts/python.exe" if os.name == "nt" else "bin/python")))
TORCH_HOME = os.environ.get("LIPSYNC_TORCH_HOME") or os.environ.get("TORCH_HOME") or str(Path.home() / ".cache" / "torch")
VOICE_DB = 24.0      # voicing counts only this close to the loudest frame (reverb tails are quieter)
BRIDGE = 0.08        # voiced gaps shorter than this are bridged; silent gaps longer become rest
PITCH = (65.0, 1050.0)   # pyin pitch range, Hz: speech and singing
RELEASE_BEFORE = 0.08    # a stop's burst is looked for this far before its aligned peak...
RELEASE_AFTER = 0.03     # ...and this far after
CLOSURE = 0.08       # longest a stop or nasal is held before its burst when nothing else limits it
SILENT_CLOSURE = 0.04   # ...and when the closure is silence (a stop after a pause)
HISS_REACH = 0.08    # a hissing letter's start is looked for this far before its aligned peak
CODA = 0.10          # room for each word-final consonant at the end of a note
HISS_TAIL = 0.35     # a word-final hissing letter may run this much longer, while it still hisses...
HISS_TAIL_SHARE = 0.5   # ...i.e. while at least this share of the sound is above 3 kHz
LETTER_LEAD = 0.02   # other consonants start this much before their aligned peak
LOW_SCORE = 0.3      # a word whose letters MMS scores below this (mean) is listed as unsure


def voiced_mask(audio, sr=16000):
    """True per 10 ms frame where the voice really sounds: pyin voiced AND loud enough."""
    import librosa
    hop = int(sr * align.HOP)
    _, voiced, _ = librosa.pyin(audio, fmin=PITCH[0], fmax=PITCH[1], sr=sr, frame_length=1024, hop_length=hop)
    rms = librosa.feature.rms(y=audio, frame_length=1024, hop_length=hop)[0]
    db = 20 * np.log10(rms + 1e-9)
    n = min(len(voiced), len(db))
    mask = voiced[:n] & (db[:n] > db.max() - VOICE_DB)
    # bridge short gaps
    f, gap = 0, int(round(BRIDGE / align.HOP))
    while f < n:
        if not mask[f]:
            g = f
            while g < n and not mask[g]:
                g += 1
            if 0 < f and g < n and g - f < gap:
                mask[f:g] = True
            f = g
        else:
            f += 1
    return mask


def run_aligner(audio, latin):
    """Onset (and score) of every sound from MMS, run in the torch venv. None for sounds without letters."""
    if not Path(VENV_PYTHON).exists():
        raise SystemExit(f"--aligner mms needs the torch venv at {VENV_PYTHON} (set LIPSYNC_MMS_PYTHON). "
                         "See SKILL.md; ask the user before installing anything.")
    with tempfile.TemporaryDirectory() as tmp:
        wav, tok, out = Path(tmp) / "a.wav", Path(tmp) / "t.json", Path(tmp) / "o.json"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
        tok.write_text(json.dumps({"units": latin}), encoding="utf-8")
        env = dict(os.environ, TORCH_HOME=TORCH_HOME)
        subprocess.run([VENV_PYTHON, str(Path(__file__).parent / "mms_align.py"), str(wav), str(tok), str(out)],
                       check=True, env=env)
        return json.loads(out.read_text(encoding="utf-8"))["units"]


def script_units(words):
    """Every sound of the script in order: (word index, unit). Phrase edges as align.py uses them."""
    out = []
    for i, w in enumerate(words):
        first = i == 0 or words[i - 1]["phrase_end"]
        for u in rules.units(w["text"], first, w["phrase_end"]):
            out.append((i, u))
    return out


def sharpest(step, f0, f1):
    f0, f1 = max(0, f0), min(len(step), f1)
    if f1 <= f0:
        return None, 0.0
    k = f0 + int(np.argmax(step[f0:f1]))
    return k, float(step[k])


def place(audio, words, dialect=None):
    """Words with MMS times, and every sound placed: [(word index, unit, start, end)]."""
    loud, hiss, voice, hum = align.features(audio)
    length = len(audio) / 16000
    su = script_units(words)
    units = [u for _, u in su]
    latin = translit.latin(units, dialect)
    aligned = run_aligner(audio, latin)
    kinds = [align.kind_of(u) for u in units]
    H = align.HOP
    rise = np.zeros(len(loud))
    rise[:-align.RISE_SPAN] = loud[align.RISE_SPAN:] - loud[:-align.RISE_SPAN]
    hstep = np.zeros(len(hiss))
    hstep[:-align.RISE_SPAN] = hiss[align.RISE_SPAN:] - hiss[:-align.RISE_SPAN]

    quiet = align.quiet_mask(loud)

    # 1. onsets: the aligned peak; sounds without a letter share the time of the sound before them
    onset = [a["start"] if a else None for a in aligned]
    for k in range(len(onset)):
        if onset[k] is None:
            onset[k] = onset[k - 1] if k else next((o for o in onset if o is not None), 0.0)

    # 2. corrected by the sound, the same for every letter of a kind
    start = list(onset)
    release = {}   # stop/nasal index -> burst time (the sound after it starts there)
    for k, (kind, u) in enumerate(zip(kinds, units)):
        if aligned[k] is None:
            continue
        t = onset[k]
        lo_lim = start[k - 1] + align.HOP if k else 0.0   # order only: the one-frame minimum is
                                                           # tidy()'s job, which borrows without drift
        if kind in ("stop", "nasal"):
            f, r = sharpest(rise, int((t - RELEASE_BEFORE) / H), int((t + RELEASE_AFTER) / H) + 1)
            burst = (f + 1) * H if f is not None and r >= align.SNAP_MIN_RISE else t
            burst = max(burst, lo_lim + align.HOP)
            release[k] = burst
            g = int(burst / H) - 1   # a closure held in silence (phrase start) is kept short
            silent = g > 0 and quiet[max(0, g - int(CLOSURE / H)):g].all()
            start[k] = max(lo_lim, burst - (SILENT_CLOSURE if silent else CLOSURE))
        elif kind == "hiss":
            f, r = sharpest(hstep, int((t - HISS_REACH) / H), int(t / H) + 1)
            start[k] = max(lo_lim, (f + 1) * H if f is not None and r >= align.HISS_MIN_STEP else t - LETTER_LEAD)
        elif kind in ("flow", "throat"):
            start[k] = max(lo_lim, t - LETTER_LEAD)
        else:   # a vowel starts where the stop before it bursts open, or at its own onset
            start[k] = max(lo_lim, release.get(k - 1, t) if k and kinds[k - 1] in ("stop", "nasal") else t)
    for k in range(1, len(start)):   # keep them in order
        start[k] = max(start[k], start[k - 1])
    for k in range(len(start) - 1):   # a stop's burst is where the next sound begins
        if k in release:
            start[k + 1] = max(start[k + 1], min(release[k], start[k + 2] if k + 2 < len(start) else length))

    # 3. ends: each sound holds until the next one starts, except where the voice stops
    voiced = voiced_mask(audio)
    end = [start[k + 1] if k + 1 < len(start) else length for k in range(len(start))]
    by_word = {}
    for k, (i, _) in enumerate(su):
        by_word.setdefault(i, []).append(k)
    out_words = []
    for i, w in enumerate(words):
        ks = by_word.get(i, [])
        if not ks:
            out_words.append(dict(w, start=None, end=None, guessed=True))
            continue
        nxt = start[ks[-1] + 1] if ks[-1] + 1 < len(start) else length
        vs = [k for k in ks if units[k][0] == "vowel"]
        v = vs[-1] if vs else ks[0]
        coda = [k for k in ks if k > v]
        # the note: from the last vowel to where voicing really stops
        f = int(start[v] / H)
        while f < len(voiced) and not voiced[f] and (f + 1) * H < start[v] + 0.05:
            f += 1
        while f < len(voiced) and voiced[f]:
            f += 1
        note_end = min(nxt, max(f * H, start[v] + align.MIN_CUE))
        if coda:
            # the final consonants at the end of the note, never inside the held vowel
            last = coda[-1]
            sound_end = note_end
            if True:   # a final consonant sounds on after the voice (pitch) stops: ل ن م fade, س ت ك hiss and burst
                g, limit = int(note_end / H), note_end + CODA * len(coda)
                while g < len(quiet) and not quiet[g] and (g + 1) * H <= limit:
                    g += 1
                # a final hissing letter (ش س ف ث ص ...) sounds as long as its hiss, which can outlast
                # CODA when a quiet voiced letter (the م hum in مْشْ) comes before it
                if kinds[last] == "hiss":
                    while (g < len(quiet) and not quiet[g] and hiss[g] >= HISS_TAIL_SHARE
                           and (g + 1) * H <= limit + HISS_TAIL):
                        g += 1
                sound_end = max(note_end, g * H)
            # ...and never out in the silence after it (MMS can put a last letter anywhere in a pause)
            c0 = max(start[coda[0]], note_end - CODA * len(coda))
            c0 = max(start[v] + H, min(c0, sound_end - align.MIN_CUE * len(coda)))
            word_end = min(nxt, max(sound_end, c0 + align.MIN_CUE * len(coda)))
            if abs(c0 - start[coda[0]]) > 1e-6:   # moved: share the end of the note evenly
                step = (word_end - c0) / len(coda)
                for j, k in enumerate(coda):
                    start[k], end[k] = c0 + j * step, c0 + (j + 1) * step
            end[v] = start[coda[0]]
            end[last] = word_end
        else:
            word_end = note_end
            end[v] = word_end
        if nxt - word_end <= BRIDGE:   # too short a gap for a rest: hold on to the next sound
            end[ks[-1]] = nxt
            word_end = nxt
        scores = [aligned[k]["score"] for k in ks if aligned[k] and units[k][0] == "consonant"] or \
                 [aligned[k]["score"] for k in ks if aligned[k]]
        out_words.append(dict(w, start=round(start[ks[0]], 3), end=round(end[ks[-1]], 3),
                              p=round(float(np.mean(scores)), 2) if scores else None,
                              letters=" ".join(l for l in (latin[k] for k in ks) if l)))
    placed = [(su[k][0], units[k], start[k], end[k]) for k in range(len(units))]
    return out_words, placed


def cues_and_track(audio, words, dialect=None, rate=100):
    """mouthCues and mouthTrack in the skill's own format, from MMS timing."""
    words, placed = place(audio, words, dialect)
    length = len(audio) / 16000
    by_word = {}
    for i, u, a, b in placed:
        by_word.setdefault(i, []).append((u, a, b))
    out, track_in = [], []
    for i in sorted(by_word):
        us = [u for u, _, _ in by_word[i]]
        shapes = align.mouth_shapes(us)
        for k, ((u, a, b), shape) in enumerate(zip(by_word[i], shapes)):
            if b > a:
                out.append({"start": round(a - align.LEAD, 3), "end": round(b - align.LEAD, 3), "mouth": shape})
                track_in.append((a, b, shape, u, align.next_vowel(us, k)))
    return words, align.tidy(out, length), align.track(track_in, length, rate)
