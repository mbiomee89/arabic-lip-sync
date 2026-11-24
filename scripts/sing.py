"""--sing: mouths for singing, on top of the MMS timing (lipsync.py --aligner mms --sing).

MMS and the mouth rules were made for speech. Tested on an Egyptian song (2026-11-23), the
problems were mostly mouth SHAPES, less often timing. This pass fixes what was found there:

  1. dips and hums: MMS can stretch a wavy held vowel and put the next consonant late. A clear
     loudness dip inside the vowel (a consonant or breath) pulls the consonant back to it; a sung
     م / ن is a quiet hum, so the nasal starts where the voice drops and stays low.
  2. onsets: MMS gives sung time to the consonant before a vowel (one ت was held 0.31 s). Plain
     consonants get at most CONS_MAX each, the vowel starts when the singer opens.
  3. one note: a long ي / ا comes as two short pieces; they are joined into one note.
  4. brightness: singers open "e"/"ee" a lot. A kasra / ي vowel as bright as the singer's own
     fatha vowels (spectral centroid 200-3000 Hz) shows "mid" instead of "small".
  5. held notes open: a long vowel held HOLD s or more opens one size, two when loud or high; a
     held kasra / ي opens one size only when also loud or high. A short fatha never opens.
  6. style decides "wide": calm = never wide (every note at most mid); open = wide only on notes
     held WIDE_HOLD s or more. The user is ASKED which, every song (their taste varies).
  7. long notes move with the voice: louder -> one size more, softer -> one size less.
closed, f, round and sh are never changed by this pass.
Closed mouths longer than hum_max are listed in the report to check by eye.
"""
import numpy as np

import align
import mms
import rules

LADDER = ["small", "mid", "wide"]
HOLD = 0.25        # a vowel this long (s) is a held note
SMALL_HOLD = 0.30  # kasra / long ي open up only when held this long AND loud or high
LOUD_DB = 6.0      # within this many dB of the loudest note counts as loud
HIGH_PCT = 75      # pitch above this percentile of the song counts as high
CONS_MAX = 0.10    # most a plain consonant may take before a vowel (s)
SLICE = 0.12       # held notes are re-checked for loudness this often (s)
MOVE_MIN = 0.45    # only notes at least this long move with the voice
SWELL_DB = 3.0     # this much louder than the note's own average -> one size more
FADE_DB = 5.0      # this much softer -> one size less
WIDE_HOLD = {"calm": 99.0, "open": 0.70}   # "wide" only on notes held this long
DIP_DB = 8.0       # a loudness dip this deep (vs. both sides) is a consonant or breath
DIP_SIDE = 0.15    # ...measured against the loudest point this far on each side (s)
DIP_REACH = 0.50   # a consonant MMS placed up to this long after a dip / hum start is moved back
DIP_MIN_GAP = 0.08 # ...but only when it is at least this far after it (s)
BRIGHT = 0.90      # tuned on one female singer; check other voices in the slow preview
HUM_MAX = 0.40     # closed mouths longer than this are listed for checking
H = align.HOP


def voice_features(audio, sr=16000):
    import librosa
    hop = int(sr * H)
    f0, voiced, _ = librosa.pyin(audio, fmin=mms.PITCH[0], fmax=mms.PITCH[1], sr=sr,
                                 frame_length=1024, hop_length=hop)
    rms = librosa.feature.rms(y=audio, frame_length=1024, hop_length=hop)[0]
    db = 20 * np.log10(rms + 1e-9)
    S = np.abs(librosa.stft(audio, n_fft=512, hop_length=hop))
    f = librosa.fft_frequencies(sr=sr, n_fft=512)
    band = (f > 200) & (f < 3000)
    bright = (S[band] * f[band][:, None]).sum(0) / (S[band].sum(0) + 1e-9)
    n = min(len(f0), len(db), len(bright))
    return f0[:n], voiced[:n], db[:n] - db.max(), bright[:n]


def span(arr, a, b):
    f0, f1 = int(a / H), max(int(a / H) + 1, int(b / H))
    return arr[f0:f1]


def step(mouth, n):
    if mouth not in LADDER:
        return mouth
    return LADDER[max(0, min(len(LADDER) - 1, LADDER.index(mouth) + n))]


def dips(db):
    """Times of clear loudness dips: consonants and breaths between sung syllables."""
    sm = np.convolve(db, np.ones(3) / 3, mode="same")
    side = int(DIP_SIDE / H)
    out = []
    for f in range(side, len(sm) - side):
        if sm[f] == sm[f - 2:f + 3].min() and sm[f] <= min(sm[f - side:f].max(), sm[f + 1:f + side + 1].max()) - DIP_DB:
            if not out or f * H - out[-1] > 0.06:
                out.append(f * H)
    return out


def _shift_word(units, k, t):
    """Move unit k's start to t and spread the rest of its word over the new time."""
    ks = [i for i in range(k, len(units)) if units[i]["word"] == units[k]["word"]]
    end, old = units[ks[-1]]["b"], units[k]["a"]
    scale = (end - t) / (end - old)
    for i in ks:
        units[i]["a"] = t + (units[i]["a"] - old) * scale
        units[i]["b"] = t + (units[i]["b"] - old) * scale
    units[k - 1]["b"] = t
    return round(old, 2), round(t, 2)


def snap(units, db):
    moved = []
    for t_d in dips(db):
        for k in range(1, len(units)):
            u, prev = units[k], units[k - 1]
            if u["kind"] != "consonant" or prev["kind"] != "vowel":
                continue
            if not (u["a"] - DIP_REACH <= t_d <= u["a"] - DIP_MIN_GAP) or t_d - prev["a"] < 0.10:
                continue
            moved.append(_shift_word(units, k, t_d) + ("dip",))
            break
    sm = np.convolve(db, np.ones(3) / 3, mode="same")
    for k in range(1, len(units)):
        u = units[k]
        if u["kind"] != "consonant" or u.get("ch") not in ("م", "ن") or units[k - 1]["kind"] != "vowel":
            continue
        j = k - 1
        while j > 0 and units[j - 1]["kind"] == "vowel" and units[j - 1]["word"] == units[k - 1]["word"]:
            j -= 1
        va = units[j]["a"]
        vowel = span(sm, va, u["a"])
        if len(vowel) < 5:
            continue
        low = float(np.percentile(vowel, 90)) - DIP_DB
        f = int(u["a"] / H)
        while f - 1 > int((va + 0.05) / H) and sm[f - 1] <= low and u["a"] - (f - 1) * H <= DIP_REACH:
            f -= 1
        t = f * H
        if u["a"] - t < DIP_MIN_GAP or t <= units[k - 1]["a"] + 0.03:
            continue
        moved.append(_shift_word(units, k, t) + ("hum",))
    return moved


def sing_pass(units, f0, voiced, db, bright, style="calm", bright_share=BRIGHT):
    wide_hold = WIDE_HOLD[style]
    pitched = f0[voiced & ~np.isnan(f0)]
    high = np.percentile(pitched, HIGH_PCT) if len(pitched) else np.inf
    stats = {"style": style, "opened_1": 0, "opened_2": 0, "starts_moved": 0, "notes_moving": 0}
    stats["snapped"] = snap(units, db)

    for k, u in enumerate(units):
        if u["kind"] != "vowel" or (k and units[k - 1]["kind"] == "vowel"):
            continue
        j = k - 1
        while j >= 0 and units[j]["kind"] == "consonant" and units[j]["word"] == u["word"]:
            j -= 1
        cons = units[j + 1:k]
        if cons and all(c["mouth"] in LADDER for c in cons) and u["a"] - cons[0]["a"] > CONS_MAX * len(cons) + 1e-6:
            t0 = cons[0]["a"]
            for i, c in enumerate(cons):
                c["a"], c["b"] = t0 + i * CONS_MAX, t0 + (i + 1) * CONS_MAX
            u["a"] = t0 + CONS_MAX * len(cons)
            stats["starts_moved"] += 1

    joined = []
    order = {"round": 3, "wide": 2, "mid": 1, "small": 0}
    for u in units:
        p = joined[-1] if joined else None
        if p and p["kind"] == "vowel" and u["kind"] == "vowel" and p["word"] == u["word"] and abs(p["b"] - u["a"]) < 1e-6:
            p["b"] = u["b"]
            p["long"] = p.get("long") or u.get("long")
            if order.get(u["mouth"], -1) > order.get(p["mouth"], -1):
                p["mouth"] = u["mouth"]
        else:
            joined.append(dict(u))
    units = joined

    def brightness(u):
        b, d = span(bright, u["a"], u["b"]), span(db, u["a"], u["b"])
        b = b[d > -15] if len(d) == len(b) else b
        return float(np.median(b)) if len(b) else None
    fathas = [x for x in (brightness(u) for u in units
                          if u["kind"] == "vowel" and u["mouth"] in ("mid", "wide") and u["b"] - u["a"] >= 0.08) if x]
    ref = float(np.median(fathas)) if fathas else None
    stats["bright_opened"] = []
    for u in units:
        if ref and u["kind"] == "vowel" and u["mouth"] == "small" and u["b"] - u["a"] >= 0.08:
            x = brightness(u)
            if x and x >= bright_share * ref:
                u["mouth"] = "mid"
                stats["bright_opened"].append(round(u["a"], 2))

    for u in units:
        if u["kind"] != "vowel" or u["mouth"] not in LADDER:
            continue
        dur = u["b"] - u["a"]
        if dur < HOLD:
            if u["mouth"] == "wide" and dur < wide_hold:
                u["mouth"] = "mid"
            continue
        d = span(db, u["a"], u["b"])
        p = span(f0, u["a"], u["b"])
        p = p[~np.isnan(p)]
        loud = bool(len(d)) and np.median(d) > -LOUD_DB
        hi = bool(len(p)) and np.median(p) >= high
        if u["mouth"] == "small":
            n = 1 if (loud or hi) and dur >= SMALL_HOLD else 0
        elif not u.get("long"):
            n = 0
        else:
            n = 2 if (loud or hi) else 1
        if n:
            u["mouth"] = step(u["mouth"], n)
            stats["opened_2" if n == 2 else "opened_1"] += 1
        if u["mouth"] == "wide" and dur < wide_hold:
            u["mouth"] = "mid"
        if dur >= MOVE_MIN and len(d):
            mean = float(np.mean(d))
            pieces, t = [], u["a"]
            while t < u["b"] - 1e-6:
                e = min(u["b"], t + SLICE)
                if u["b"] - e < SLICE / 2:
                    e = u["b"]
                s = float(np.mean(span(db, t, e))) if len(span(db, t, e)) else mean
                up = 1 if (u.get("long") or u["mouth"] == "small") else 0
                if step(u["mouth"], up) == "wide" and dur < wide_hold:
                    up = 0
                m = step(u["mouth"], up) if s > mean + SWELL_DB else step(u["mouth"], -1) if s < mean - FADE_DB else u["mouth"]
                pieces.append((t, e, m))
                t = e
            if len({m for _, _, m in pieces}) > 1:
                u["pieces"] = pieces
                stats["notes_moving"] += 1
    return units, stats


def cues_and_track(audio, words, dialect=None, style="calm", bright_share=None, hum_max=None):
    """Like mms.cues_and_track, with the singing pass. Returns words, cues, track, stats."""
    length = len(audio) / 16000
    words, placed = mms.place(audio, words, dialect)
    by_word = {}
    for i, u, s, e in placed:
        by_word.setdefault(i, []).append((u, s, e))
    units, track_in = [], []
    for i in sorted(by_word):
        us = [u for u, _, _ in by_word[i]]
        for k, ((u, s, e), shape) in enumerate(zip(by_word[i], align.mouth_shapes(us))):
            if e > s:
                units.append({"kind": u[0], "mouth": shape, "a": s, "b": e, "word": i,
                              "long": u[0] == "vowel" and u[2] >= rules.WEIGHT["long"], "ch": u[3],
                              "unit": u, "after": align.next_vowel(us, k)})
    f0, voiced, db, bright = voice_features(audio)
    units, stats = sing_pass(units, f0, voiced, db, bright, style, bright_share or BRIGHT)
    cues = []
    for u in units:   # the cues and the smooth track both from the sung times and mouths
        for s, e, m in u.get("pieces", [(u["a"], u["b"], u["mouth"])]):
            if e > s:
                cues.append({"start": round(s - align.LEAD, 3), "end": round(e - align.LEAD, 3), "mouth": m})
                track_in.append((s, e, m, u["unit"], u["after"]))
    cues = align.tidy(cues, length)
    limit = hum_max or HUM_MAX
    stats["long_closed"] = [{"start": c["start"], "end": c["end"]} for c in cues
                            if c["mouth"] == "closed" and c["end"] - c["start"] > limit]
    return words, cues, align.track(track_in, length), stats
