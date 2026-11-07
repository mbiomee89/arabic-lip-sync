"""Place each letter and vowel of a vowel-marked Arabic script in the audio, then give each a mouth.

The sound is read directly (loudness, hiss, voicing, low hum) and the script's sounds are fitted to
it in order, phrase by phrase, guided by Whisper's word times. Mouths follow rules.py.

Usage (as a module): cues(audio_16k_mono_float, words) -> [{"start", "end", "mouth"}]
  words: [{"text": vowel-marked word, "start", "end", "phrase_end": bool}], Whisper times matched to the script.
"""
import numpy as np

import rules

HOP = 0.01  # seconds per analysis frame
STOPS = set("بتدطكقءأإآؤئضج")
HISS = set("فثذسزصظشخغحه")
NASAL = set("من")
FLOW = set("لروي")
THROAT = set("عحهءأإآ")
# Shortest and longest length of each kind of sound, in frames (measured lengths, rounded).
LENGTH = {"short": (3, 25), "long": (6, 45), "stop": (2, 15), "hiss": (3, 25), "nasal": (3, 20),
          "flow": (2, 15), "throat": (2, 15), "pause": (0, 300)}
SHARPNESS = 3.0   # how firmly each frame prefers its best-fitting kind of sound
OUTSIDE = 2.0     # cost per frame of placing a sound outside its word's Whisper times
SLACK = 0.12      # Whisper's word times are rough by about this much
PAD = 0.25        # audio taken around each phrase
LEAD = 0.03       # mouth shapes start this much before the sound, as real lips do
MIN_CUE = 0.067   # two video frames
KEEP = ("closed", "f", "round")   # lip shapes that must show even when short
SPEECH_LOUD = 0.45   # a frame counts as clear speech above this loudness...
SPEECH_VOICE = 0.5   # ...and this voicing
SPEECH_COST = 3.0    # cost per frame of a pause placed on clear speech
RISE_SPAN = 3        # frames over which a loudness rise is measured (30 ms)
SNAP_BEFORE = 6      # a closure may move this many frames earlier...
SNAP_AFTER = 20      # ...or later, to end where the lips open
SNAP_MIN_RISE = 0.2  # smallest loudness rise that counts as the lips opening
TRIM_LOUD = 0.25     # lowest loudness threshold for silence (used when the recording has little range)
QUIET_DB = 36.0      # sound this many dB below the voice is silence: room noise, breaths, clicks
QUIET_LOUD = TRIM_LOUD
TRIM_KEEP = 0.08     # a trimmed word keeps at least this much time
MIN_SOUND = 0.06     # shorter bursts of sound between silences are breaths or clicks, not words
GAP_MIN = 0.10       # a silence this long inside a word's time is a pause Whisper hung on it
GAP_REACH = 0.6      # how far back to look for it
REACH = 0.4         # how far before/after Whisper's phrase times to look for where the voice really starts/ends


def features(audio, sr=16000):
    """Per 10 ms: loudness 0..1, hiss (share of energy above 3 kHz), voicing 0..1, hum (share below 500 Hz)."""
    hop, win = int(sr * HOP), int(sr * 0.025)
    n = max(1, (len(audio) - win) // hop)
    frames = np.lib.stride_tricks.sliding_window_view(audio, win)[::hop][:n] * np.hanning(win)
    spec = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    freqs = np.fft.rfftfreq(win, 1 / sr)
    total = spec.sum(1) + 1e-10
    db = 10 * np.log10(total)
    lo, hi = np.percentile(db, 10), np.percentile(db, 98)
    global QUIET_LOUD   # silence = QUIET_DB or more below the voice, in this recording's loudness scale
    QUIET_LOUD = float(np.clip((hi - QUIET_DB - lo) / (hi - lo + 1e-6), TRIM_LOUD, 0.8))
    loud = np.clip((db - lo) / (hi - lo + 1e-6), 0, 1)
    hiss = spec[:, freqs > 3000].sum(1) / total
    hum = spec[:, freqs < 500].sum(1) / total
    # Voicing: strongest normalised self-similarity for pitch between 70 and 400 Hz.
    ac = np.fft.irfft(np.abs(np.fft.rfft(frames, 2 * win, axis=1)) ** 2, axis=1)[:, :win]
    lag0 = ac[:, :1] + 1e-10
    lags = slice(int(sr / 400), int(sr / 70))
    voice = np.clip(ac[:, lags].max(1) / lag0[:, 0], 0, 1)
    return loud, hiss, voice, hum


def kind_of(unit):
    kind, _, weight, ch = unit
    if kind == "vowel":
        return "long" if weight >= rules.WEIGHT["long"] else "short"
    if ch in THROAT:
        return "throat"
    if ch in NASAL:
        return "nasal"
    if ch in HISS:
        return "hiss"
    if ch in FLOW:
        return "flow"
    return "stop"


def fit_scores(loud, hiss, voice, hum):
    """How well each frame fits each kind of sound, as a log share across the kinds, so that no
    kind wins just because its raw numbers run larger."""
    quiet = 1 - loud
    raw = {
        "short": loud + 0.5 * voice - hiss,
        "long": loud + 0.5 * voice - hiss,
        "stop": quiet - 0.3 * voice,
        "hiss": 1.5 * hiss + 0.3 * quiet,
        "nasal": voice + hum - np.abs(loud - 0.5) - hiss,
        "flow": voice + 0.5 * loud - hiss,
        "throat": 0.5 * loud + 0.5 * hiss,
        "pause": 1.5 * quiet - voice - 0.3,
    }
    names = list(raw)
    z = SHARPNESS * np.stack([raw[k] for k in names])
    z = z - (np.log(np.exp(z - z.max(0)).sum(0)) + z.max(0))
    return dict(zip(names, z))


def align(fit, kinds, windows, t0):
    """Fit the sounds in order to frames 0..T. windows[u] = (from, to) seconds where unit u's word
    was heard; a unit outside its word's window pays OUTSIDE per frame.
    Returns each unit's (first frame, end frame)."""
    T, U = len(next(iter(fit.values()))), len(kinds)
    times = t0 + np.arange(T) * HOP
    cums = []
    for kind, (w0, w1) in zip(kinds, windows):
        e = fit[kind] - OUTSIDE * ((times < w0 - SLACK) | (times > w1 + SLACK))
        cums.append(np.concatenate([[0], np.cumsum(e)]))
    lead_pause = np.concatenate([[0], np.cumsum(fit["pause"])])
    best = np.full((U + 1, T + 1), -np.inf)
    back = np.zeros((U + 1, T + 1), int)
    best[0, :] = lead_pause
    for u, kind in enumerate(kinds):
        lo, hi = LENGTH[kind]
        cum = cums[u]
        for end in range(T + 1):
            starts = np.arange(max(0, end - hi), end - lo + 1)
            if len(starts) == 0:
                continue
            score = best[u, starts] + cum[end] - cum[starts]
            k = int(np.argmax(score))
            best[u + 1, end], back[u + 1, end] = score[k], starts[k]
    total = best[U] + lead_pause[T] - lead_pause[np.arange(T + 1)]   # trailing pause
    end = int(np.argmax(total))
    spans = []
    for u in range(U, 0, -1):
        start = back[u, end]
        spans.append((start, end))
        end = start
    return spans[::-1]


def phrases(words):
    out, cur = [], []
    for w in words:
        if w.get("start") is None:
            continue
        cur.append(w)
        if w.get("phrase_end"):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def speech_edge(speech, t, step, limit=REACH):
    """From time t, walk while the sound is still speech, up to `limit` seconds; returns the edge.
    Whisper often marks the first word of a phrase late, or the last one early."""
    f, n = int(t / HOP), 0
    while 0 <= f + step < len(speech) and n * HOP < limit and speech[f + step]:
        f += step
        n += 1
    return f * HOP


def quiet_mask(loud):
    """True where it's silent. A burst of sound shorter than MIN_SOUND (a breath, a lip smack)
    counts as silence too, so it's never taken for the start of a word."""
    quiet = loud < QUIET_LOUD
    f = 0
    while f < len(quiet):
        if not quiet[f]:
            g = f
            while g < len(quiet) and not quiet[g]:
                g += 1
            if (g - f) * HOP < MIN_SOUND and f > 0 and g < len(quiet) and quiet[f - 1] and quiet[g]:
                quiet[f:g] = True
            f = g
        else:
            f += 1
    return quiet


def silence_runs(loud, f0, f1):
    """(start, end) frames of each silence at least GAP_MIN long between frames f0 and f1."""
    out, f = [], f0
    quiet = quiet_mask(loud)
    while f < f1:
        if quiet[f]:
            g = f
            while g < f1 and quiet[g]:
                g += 1
            if (g - f) * HOP >= GAP_MIN:
                out.append((f, g))
            f = g
        else:
            f += 1
    return out


def repair_times(words, loud):
    """Whisper often hangs a pause on the end of one word or the start of the next. Where a clear
    silence lies near the border of two words, move the border to it: the first word ends where
    the silence starts, the next starts where the sound comes back."""
    words = [dict(w) for w in words]
    quiet = quiet_mask(loud)
    timed = [w for w in words if w.get("start") is not None]
    for prev, w in zip(timed, timed[1:]):
        lo = int(max(prev["start"] + TRIM_KEEP, w["start"] - GAP_REACH) / HOP)
        hi = int((w["end"] - TRIM_KEEP) / HOP)
        reach = int((w["start"] + GAP_REACH) / HOP)   # a pause must start near the border, but may run on
        runs = [r for r in silence_runs(loud, max(lo, 0), min(hi, len(loud))) if r[0] <= reach]
        if not runs:
            continue
        g, f = max(runs, key=lambda r: r[1] - r[0])   # the longest silence is the pause
        said = int(prev["start"] / HOP)
        if (~quiet[said:g]).sum() * HOP < TRIM_KEEP:   # nothing said before it: not a pause between words
            continue
        prev["end"] = min(max(prev["start"] + TRIM_KEEP, g * HOP), prev["end"]) if g * HOP < prev["end"] else prev["end"]
        w["start"] = f * HOP
    return words


def cues(audio, words, sr=16000):
    loud, hiss, voice, hum = features(audio, sr)
    fit_all = fit_scores(loud, hiss, voice, hum)
    speech = (loud > SPEECH_LOUD) & (voice > SPEECH_VOICE)
    # Never fit a pause (a closed, resting mouth) over clear voiced speech.
    fit_all["pause"] = fit_all["pause"] - SPEECH_COST * speech
    out = []
    quiet = quiet_mask(loud)
    groups = phrases(repair_times(words, loud))
    for g, group in enumerate(groups):
        # Each phrase keeps to its own stretch of audio: the phrases around it are never overlapped.
        floor = groups[g - 1][-1]["end"] if g > 0 else 0.0
        ceil = groups[g + 1][0]["start"] if g + 1 < len(groups) else len(loud) * HOP
        first = max(floor, speech_edge(speech, group[0]["start"], -1))
        last = min(ceil, speech_edge(speech, group[-1]["end"], 1))
        group = [dict(w) for w in group]
        group[0]["start"], group[-1]["end"] = min(group[0]["start"], first), max(group[-1]["end"], last)
        for w in group:   # a word Whisper starts in silence starts where the sound does
            f, stop = int(w["start"] / HOP), int((w["end"] - TRIM_KEEP) / HOP)
            while f < stop and f < len(loud) and quiet[f]:
                f += 1
            w["start"] = max(w["start"], f * HOP)
        t0 = max(0.0, floor, group[0]["start"] - PAD)
        t1 = min(len(loud) * HOP, ceil, group[-1]["end"] + PAD)
        f0, f1 = int(t0 / HOP), int(t1 / HOP)
        fit = {k: v[f0:f1] for k, v in fit_all.items()}
        units, kinds, windows = [], [], []
        for i, w in enumerate(group):
            us = rules.units(w["text"], i == 0, w.get("phrase_end", False) or i == len(group) - 1)
            if not us:
                continue
            if units:   # an optional pause between words, anywhere between their times
                units.append(("pause", None, 0, " "))
                kinds.append("pause")
                windows.append((windows[-1][0], w["end"]))
            for u in us:
                units.append(u)
                kinds.append(kind_of(u))
                windows.append((w["start"], w["end"]))
        if not units:
            continue
        spans = align(fit, kinds, windows, t0)
        shapes = mouth_shapes(units)
        spans = snap_closures(spans, shapes, loud[f0:f1])
        for (a, b), shape in zip(spans, shapes):
            if b > a:
                out.append({"start": round(t0 + a * HOP - LEAD, 3), "end": round(t0 + b * HOP - LEAD, 3), "mouth": shape})
    return tidy(out, len(loud) * HOP)


def snap_closures(spans, shapes, loud):
    """Move each lip closure so it ends where the lips open again: the sharpest rise in loudness
    near the closure's end (measured on video: within about 20 ms of the real lip opening).
    The closure keeps its length; the sounds around it give way."""
    spans = [list(s) for s in spans]
    rise = np.zeros(len(loud))
    rise[:-RISE_SPAN] = loud[RISE_SPAN:] - loud[:-RISE_SPAN]
    for u, shape in enumerate(shapes):
        if shape != "closed" or spans[u][1] <= spans[u][0]:
            continue
        a, b = spans[u]
        lo = max(a + 1, b - SNAP_BEFORE)
        hi = min(len(loud) - 1, b + SNAP_AFTER)
        if u + 1 < len(spans):   # the lips open for the sound right after, never a later one
            hi = min(hi, spans[u + 1][1])
        if hi <= lo:
            continue
        r = lo + int(np.argmax(rise[lo:hi]))
        if rise[r] < SNAP_MIN_RISE:
            continue
        r += 1   # the rise starts as the lips part
        length = b - a
        prev_start = spans[u - 1][0] if u > 0 else 0
        new_a = max(prev_start + 1 if u > 0 else 0, r - length)
        spans[u] = [new_a, r]
        if u > 0:
            spans[u - 1][1] = new_a
        k = u + 1
        while k < len(spans) and spans[k][0] < r:   # sounds after it start once the lips open
            spans[k][0] = min(r, spans[k][1])
            k += 1
    return [tuple(s) for s in spans]


def next_vowel(units, k):
    """The vowel right after unit k, looking past the second half of a doubled letter."""
    j = k + 1
    while j < len(units) and units[j][0] == "consonant" and units[j][3] == units[k][3]:
        j += 1
    return units[j] if j < len(units) and units[j][0] == "vowel" else None


def mouth_shapes(units):
    """The mouth for each unit. Plain consonants are nearly shut ("small"); a throat letter takes
    the mouth of the vowel after it (measured: ع ح ء open with their vowel)."""
    shapes = []
    for k, (kind, shape, weight, ch) in enumerate(units):
        if kind == "pause":
            shapes.append("rest")
        elif shape:
            shapes.append(shape)
        elif kind == "consonant" and ch in THROAT and next_vowel(units, k):
            shapes.append(next_vowel(units, k)[1] or "small")
        else:
            shapes.append("small")
    return shapes


def tidy(cs, length):
    """Fill gaps with rest, join equal neighbours, and fold shapes shorter than two frames into the
    previous one. Lip shapes (closed, f) are stretched to two frames instead: a closure that never
    shows is the worst mistake."""
    cs = sorted(cs, key=lambda c: c["start"])
    out, t = [], 0.0
    for c in cs:
        if c["start"] > t + 0.001:
            out.append({"start": round(t, 3), "end": c["start"], "mouth": "rest"})
        out.append(dict(c, start=max(c["start"], t)))
        t = max(t, c["end"])
    out.append({"start": round(t, 3), "end": round(length, 3), "mouth": "rest"})
    joined = []   # equal neighbours first, so a sound split in parts (a doubled letter) counts at full length
    for c in out:
        if c["end"] - c["start"] <= 0:
            continue
        if joined and c["mouth"] == joined[-1]["mouth"]:
            joined[-1]["end"] = c["end"]
        else:
            joined.append(dict(c))
    merged = []
    for c in joined:
        if c["end"] - c["start"] <= 0:
            continue
        if merged and (c["mouth"] == merged[-1]["mouth"] or (c["end"] - c["start"] < MIN_CUE and c["mouth"] not in KEEP)):
            merged[-1]["end"] = c["end"]
        elif c["mouth"] in KEEP and c["end"] - c["start"] < MIN_CUE:
            merged.append(dict(c, end=round(c["start"] + MIN_CUE, 3)))
        else:
            merged.append(c)
    for a, b in zip(merged, merged[1:]):   # a stretched closure pushes the next start
        if b["start"] < a["end"]:
            b["start"] = a["end"]
    return [c for c in merged if c["end"] > c["start"]]
