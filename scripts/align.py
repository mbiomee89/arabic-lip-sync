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
MIN_CUE = 0.034   # one video frame at 30 fps: the shortest any mouth is shown, the same for every
                  # mouth, so every sound gets at least one frame (lipsync.py --fps sets it)
SPEECH_LOUD = 0.45   # a frame counts as clear speech above this loudness...
SPEECH_VOICE = 0.5   # ...and this voicing
SPEECH_COST = 3.0    # cost per frame of a pause placed on clear speech
RISE_SPAN = 3        # frames over which a loudness rise is measured (30 ms)
SNAP_BEFORE = 6      # a letter's edge may move this many frames earlier...
SNAP_AFTER = 20      # ...or later, to end where the sound bursts open
SNAP_MIN_RISE = 0.2  # smallest loudness rise that counts as a stop or nasal opening
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
    """The mouth cues (a list of {"start", "end", "mouth"})."""
    return cues_and_track(audio, words, sr)[0]


def cues_and_track(audio, words, sr=16000, rate=100):
    """The mouth cues, and the smooth mouth track: openness, width and rounding every 1/rate s."""
    loud, hiss, voice, hum = features(audio, sr)
    placed = []   # (start, end, mouth, unit, unit after) for every sound, for the track
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
        spans = snap_sounds(spans, units, kinds, loud[f0:f1], hiss[f0:f1])
        for k, ((a, b), shape) in enumerate(zip(spans, shapes)):
            if b > a:
                out.append({"start": round(t0 + a * HOP - LEAD, 3), "end": round(t0 + b * HOP - LEAD, 3), "mouth": shape})
                placed.append((t0 + a * HOP, t0 + b * HOP, shape, units[k], next_vowel(units, k)))
    length = len(loud) * HOP
    return tidy(out, length), track(placed, length, rate)


# ---- the smooth mouth track ----
# Each mouth's measured shape (references/mouth_shapes.md): lip opening, mouth width, rounding (pucker).
SHAPE = {"rest": (0.019, 0.366, 0.41), "closed": (0.014, 0.361, 0.36), "f": (0.014, 0.368, 0.15),
         "small": (0.026, 0.376, 0.40), "mid": (0.077, 0.371, 0.29), "wide": (0.118, 0.384, 0.14),
         "round": (0.023, 0.289, 1.00), "aw": (0.085, 0.316, 0.85), "sh": (0.045, 0.370, 0.55)}
TRACK_EASE = 0.03      # seconds: the most a sound spends easing in (and out) at each side...
EASE_SHARE = 0.35      # ...and at most this share of its length, so every sound still reaches its shape
TRACK_LEAD = 0.03      # the lips move this much before the sound, as in the cues
HEAVY_PART = 0.0       # how far a fatha after ص ض ط ظ ق خ rounds (0 none .. 1 fully "aw")
PRE_ROUND_PART = 0.5   # how far a consonant before a damma already rounds (measured; tuned on film)
KASRA_SPREAD = 0.0     # extra width for kasra, in face-width units


def target(shape, unit, after):
    """The shape one sound aims for, with the measured letter effects."""
    o, w, p = SHAPE.get(shape, SHAPE["small"])
    kind, _, _, ch = unit
    if kind == "vowel" and shape in ("mid", "wide") and ch in rules.HEAVY:
        ao, aw_, ap = SHAPE["aw"]
        o, w, p = o + HEAVY_PART * (ao - o), w + HEAVY_PART * (aw_ - w), p + HEAVY_PART * (ap - p)
    if kind == "consonant" and shape not in ("closed", "f") and after and after[1] == "round":
        ro, rw, rp = SHAPE["round"]
        o, w, p = o + PRE_ROUND_PART * (ro - o), w + PRE_ROUND_PART * (rw - w), p + PRE_ROUND_PART * (rp - p)
    if kind == "vowel" and shape == "small":
        w += KASRA_SPREAD
    return o, w, p


def track(placed, length, rate=100):
    """Openness, width and rounding every 1/rate s.

    Every sound has the same priority: each one holds its own full shape over the middle of its
    time, and eases into the next with the same S-curve, whatever the letter. No sound is blurred
    away because it is short, and none is held more firmly than the others. Silences go to rest."""
    n = int(length * rate) + 1
    rest = np.array(SHAPE["rest"], float)
    keys = []   # (time, shape): the moments each sound's full shape is held from and to
    prev_end = None
    for a, b, shape, unit, after in sorted(placed, key=lambda p: p[0]):
        a, b = a - TRACK_LEAD, b - TRACK_LEAD
        if b <= a:
            continue
        if prev_end is None:
            keys.append((max(0.0, a - TRACK_EASE), rest))
        elif a - prev_end > 2 * TRACK_EASE:   # a silence between sounds: back to rest
            keys += [(prev_end + TRACK_EASE, rest), (a - TRACK_EASE, rest)]
        e = min(TRACK_EASE, EASE_SHARE * (b - a))
        v = np.array(target(shape, unit, after), float)
        keys += [(a + e, v), (b - e, v)]
        prev_end = b
    if not keys:
        vals = np.tile(rest, (n, 1))
    else:
        keys.append((prev_end + TRACK_EASE, rest))
        kt = np.array([k[0] for k in keys])
        kv = np.stack([k[1] for k in keys])
        kt = np.maximum.accumulate(kt)   # keep the key times in order
        t = np.arange(n) / rate
        i = np.clip(np.searchsorted(kt, t, side="right") - 1, 0, len(kt) - 1)
        j = np.minimum(i + 1, len(kt) - 1)
        span = kt[j] - kt[i]
        s = np.where(span > 0, np.clip((t - kt[i]) / np.where(span > 0, span, 1), 0, 1), 0.0)
        w = ((1 - np.cos(np.pi * s)) / 2)[:, None]   # the same ease for every change of shape
        vals = kv[i] * (1 - w) + kv[j] * w
        vals[t < kt[0]] = kv[0]
        vals[t >= kt[-1]] = kv[-1]
    return {"rate": rate, "open": np.round(vals[:, 0], 4).tolist(), "width": np.round(vals[:, 1], 4).tolist(),
            "round": np.round(vals[:, 2], 3).tolist()}


HISS_MIN_STEP = 0.1   # smallest change in hiss share that counts as a hissing letter starting or ending


def doubled_next(units, u):
    """True when unit u is the first half of a doubled letter (the next unit is the same letter)."""
    return (u + 1 < len(units) and units[u][0] == "consonant" and units[u + 1][0] == "consonant"
            and units[u + 1][3] == units[u][3])


def snap_sounds(spans, units, kinds, loud, hiss):
    """Move letter edges onto the moment the sound really changes. The same for every letter of a
    kind, whatever its mouth:
      stops and nasals (ب ت د ط ك ق ض ج م ن): end where the sound bursts open, the sharpest
        loudness rise near the end (measured on video for ب/م: within about 20 ms of the lips opening);
      hissing letters (ف ث ذ س ز ص ظ ش خ غ ح ه): start where the hiss rises and end where it falls."""
    spans = snap_releases(spans, units, kinds, loud)
    return snap_hiss(spans, units, kinds, hiss)


def next_sound(spans, kinds, u, step):
    """The nearest unit before (step -1) or after (step 1) unit u that isn't an empty optional pause."""
    k = u + step
    while 0 <= k < len(spans) and kinds[k] == "pause" and spans[k][1] <= spans[k][0]:
        k += step
    return k if 0 <= k < len(spans) else None


def move_border(spans, left, right, t):
    """Put the border between units left and right at frame t; empty pauses between them stay empty."""
    spans[left][1] = t
    for k in range(left + 1, right):
        spans[k] = [t, t]
    spans[right][0] = t


def snap_hiss(spans, units, kinds, hiss):
    spans = [list(s) for s in spans]
    step = np.zeros(len(hiss))
    step[:-RISE_SPAN] = hiss[RISE_SPAN:] - hiss[:-RISE_SPAN]
    for u, kind in enumerate(kinds):
        if kind != "hiss" or spans[u][1] <= spans[u][0]:
            continue
        a, b = spans[u]
        prv = next_sound(spans, kinds, u, -1)
        if prv is not None and not doubled_next(units, prv):   # where the hiss starts
            lo, hi = max(spans[prv][0] + 1, a - SNAP_BEFORE), min(b - 1, a + SNAP_BEFORE)
            if hi > lo:
                r = lo + int(np.argmax(step[lo:hi]))
                if step[r] >= HISS_MIN_STEP:
                    move_border(spans, prv, u, r + 1)
        nxt = next_sound(spans, kinds, u, 1)
        if nxt is not None and not doubled_next(units, u):   # where it stops
            a = spans[u][0]
            lo, hi = max(a + 1, b - SNAP_BEFORE), min(spans[nxt][1] - 1, b + SNAP_BEFORE)
            if hi > lo:
                r = lo + int(np.argmin(step[lo:hi]))
                if -step[r] >= HISS_MIN_STEP:
                    move_border(spans, u, nxt, r + 1)
    return [tuple(s) for s in spans]


def snap_releases(spans, units, kinds, loud):
    """Move each stop or nasal so it ends where the sound bursts open again: the sharpest rise in
    loudness near its end. It keeps its length; the sounds around it give way."""
    spans = [list(s) for s in spans]
    rise = np.zeros(len(loud))
    rise[:-RISE_SPAN] = loud[RISE_SPAN:] - loud[:-RISE_SPAN]
    for u, kind in enumerate(kinds):
        if kind not in ("stop", "nasal") or spans[u][1] <= spans[u][0] or doubled_next(units, u):
            continue
        a, b = spans[u]
        lo = max(a + 1, b - SNAP_BEFORE)
        hi = min(len(loud) - 1, b + SNAP_AFTER)
        nxt = next_sound(spans, kinds, u, 1)
        if nxt is not None:   # it opens into the sound right after, which keeps at least a frame
            hi = min(hi, spans[nxt][1] - 1)
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


def prev_vowel(units, k):
    """The vowel right before unit k (looking past the first half of a doubled letter)."""
    j = k - 1
    while j >= 0 and units[j][0] == "consonant" and units[j][3] == units[k][3]:
        j -= 1
    return units[j] if j >= 0 and units[j][0] == "vowel" else None


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
        elif kind == "consonant" and not next_vowel(units, k) and prev_vowel(units, k) and prev_vowel(units, k)[1] in ("mid", "wide"):
            # measured: a consonant with sukun that isn't made with the lips (حْ عْ لْ كْ يْ)
            # keeps the mouth of the vowel before it
            shapes.append(prev_vowel(units, k)[1] or "small")
        else:
            shapes.append("small")
    return shapes


SHAPE_SCALE = (0.10, 0.10, 0.85)   # rough full range of open, width and rounding, to compare mouths fairly


def shape_distance(a, b):
    """How different two mouths look (0 = the same), each measure scaled by its full range."""
    pa, pb = SHAPE.get(a, SHAPE["small"]), SHAPE.get(b, SHAPE["small"])
    return sum(((x - y) / s) ** 2 for x, y, s in zip(pa, pb, SHAPE_SCALE)) ** 0.5


def join_equal(cs):
    out = []
    for c in cs:
        if c["end"] - c["start"] <= 1e-9:
            continue
        if out and c["mouth"] == out[-1]["mouth"]:
            out[-1]["end"] = c["end"]
        else:
            out.append(dict(c))
    return out


def tidy(cs, length):
    """Fill gaps with rest, join equal neighbours, then make every shape last at least MIN_CUE.

    Every letter has the same priority: no mouth is favoured and none is dropped for being short.
    A short shape borrows the time it needs from its neighbours (evenly, from whichever can spare
    it), so nothing after it drifts. Only when neither neighbour can spare the time is it joined
    to the neighbour that looks most like it."""
    cs = sorted(cs, key=lambda c: c["start"])
    out, t = [], 0.0
    for c in cs:
        if c["start"] > t + 0.001:
            out.append({"start": t, "end": c["start"], "mouth": "rest"})
        out.append(dict(c, start=max(c["start"], t)))
        t = max(t, c["end"])
    out.append({"start": t, "end": length, "mouth": "rest"})
    # Equal neighbours first, so a sound split in parts (a doubled letter) counts at full length.
    cs = join_equal(out)
    tol = 1e-6
    while len(cs) > 1:
        short = [k for k, c in enumerate(cs) if c["end"] - c["start"] < MIN_CUE - tol]
        if not short:
            break
        k = min(short, key=lambda k: cs[k]["end"] - cs[k]["start"])   # the shortest first
        c = cs[k]
        need = MIN_CUE - (c["end"] - c["start"])
        left = cs[k - 1] if k > 0 else None
        right = cs[k + 1] if k + 1 < len(cs) else None
        spare_l = max(0.0, left["end"] - left["start"] - MIN_CUE) if left else 0.0
        spare_r = max(0.0, right["end"] - right["start"] - MIN_CUE) if right else 0.0
        if spare_l + spare_r >= need - tol:
            take_l = min(spare_l, need / 2)
            take_r = min(spare_r, need - take_l)
            take_l = min(spare_l, need - take_r)
            if left:
                left["end"] -= take_l
                c["start"] -= take_l
            if right:
                right["start"] += take_r
                c["end"] += take_r
            if take_l + take_r < need - tol:   # rounding left it a hair short: nothing more to borrow
                c["end"] = c["start"] + MIN_CUE
                if right:
                    right["start"] = c["end"]
        else:
            n = min((x for x in (left, right) if x), key=lambda x: shape_distance(x["mouth"], c["mouth"]))
            if n is left:
                left["end"] = c["end"]
            else:
                right["start"] = c["start"]
            del cs[k]
            cs = join_equal(cs)
    return [dict(c, start=round(c["start"], 3), end=round(c["end"], 3)) for c in cs if c["end"] - c["start"] > 1e-9]
