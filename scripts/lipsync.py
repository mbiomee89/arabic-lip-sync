"""Arabic lip sync: audio + vowel-marked script -> timed mouth shapes.

Usage:
  python lipsync.py <audio or video> --out mouths.json [--script script.txt] [--words words.json] [--model large-v3] [--fps 30]
                    [--aligner whisper|mms] [--dialect egy]

  --aligner  whisper (default): Whisper word times, sounds fitted inside them.
             mms: Meta's MMS forced aligner places every letter and vowel itself (needs --script and the
             torch venv, see SKILL.md). Better for songs, held / long vowels and dialect; Whisper is not used.
  --dialect  egy: in mms mode, ج is said g and ث ذ ظ as t d z.

  --script   the text that was said, with vowel marks (تشكيل). Without it, Whisper's transcript is
             saved to <out>.transcript.txt and the script stops: add the vowel marks, then re-run.
  --words    a file for Whisper's word times: read if it exists, written if not (saves re-running Whisper).
Writes mouths.json: {"mouthCues": [{"start", "end", "mouth"}], "words": [...], "report": {...}}
and prints a check of every mouth the script calls for (all letters weighed the same).
"""
import argparse
import difflib
import json
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import align
import rules

PHRASE_END = ".،؟!:؛?,…"


LOW_CONFIDENCE = 0.5   # Whisper word probability below this counts as unsure
MAX_UNCERTAIN = 0.15   # more guessed + unsure words than this share flags the run for review


def to_wav(src, dst):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)], check=True)
    with wave.open(str(dst)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768


def whisper_words(audio, model_name):
    """Word times from faster-whisper. The script is deliberately not given as a prompt:
    Whisper then tends to skip the words it was told about."""
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device="cpu", compute_type="int8", local_files_only=True)
    segments, _ = model.transcribe(audio, language="ar", word_timestamps=True, beam_size=5, vad_filter=False)
    words = []
    for seg in segments:
        for w in seg.words:
            if w.end - w.start > 0.02 and w.probability > 0.1:   # zero-length, unsure words are usually made up
                words.append({"text": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3), "p": round(w.probability, 2)})
    return words


def plain(word):
    """A word without vowel marks or punctuation, spelled the way Whisper tends to spell it."""
    word = re.sub("^ا(?=مْ)", "", word)   # Jazan article امْ: Whisper drops the alef
    word = re.sub(f"[{''.join(rules.MARKS)}ـ{re.escape(PHRASE_END)}\"'«»()-]", "", word)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي")):
        word = word.replace(a, b)
    return word


def match(script_words, heard):
    """Pair script words with Whisper words in order, so a dropped or merged word doesn't shift the
    rest. Unheard words share the time between their heard neighbours and are marked guessed."""
    a, b = [plain(w) for w in script_words], [plain(w["text"]) for w in heard]
    pairs = {}
    for tag, i0, i1, j0, j1 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal" or (tag == "replace" and i1 - i0 == j1 - j0):
            for k in range(i1 - i0):
                pairs[i0 + k] = heard[j0 + k]
    out = [{"text": w, "start": pairs[i]["start"], "end": pairs[i]["end"], "heard": pairs[i]["text"], "p": pairs[i].get("p")} if i in pairs
           else {"text": w, "start": None, "end": None, "guessed": True} for i, w in enumerate(script_words)]
    i = 0
    while i < len(out):
        if out[i]["start"] is not None:
            i += 1
            continue
        j = i
        while j < len(out) and out[j]["start"] is None:
            j += 1
        t0 = out[i - 1]["end"] if i > 0 else max(0.0, out[j]["start"] - 0.4 * (j - i)) if j < len(out) else None
        t1 = out[j]["start"] if j < len(out) else (t0 + 0.4 * (j - i) if t0 is not None else None)
        if t0 is not None and t1 is not None and t1 > t0:
            step = (t1 - t0) / (j - i)
            for k in range(i, j):
                out[k]["start"], out[k]["end"] = round(t0 + (k - i) * step, 3), round(t0 + (k - i + 1) * step, 3)
        i = j
    return out


def read_script(path):
    """Words in order; a word ending a line or followed by punctuation ends a phrase."""
    words = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        for k, w in enumerate(parts):
            words.append({"text": w, "phrase_end": k == len(parts) - 1 or w[-1] in PHRASE_END})
    return words


def expected_mouths(text, first, last):
    """The mouths a word should show, in order: one per sound, with a sound's repeats (a doubled
    letter, a consonant that shares its vowel's mouth) counted once."""
    seq = []
    for m in align.mouth_shapes(rules.units(text, first, last)):
        if not seq or seq[-1] != m:
            seq.append(m)
    return seq


def in_order(want, seen):
    """Which of the wanted mouths are shown, in order: the best in-order match of want against seen
    (longest common subsequence), so one missing sound never hides the ones after it."""
    n, m = len(want), len(seen)
    best = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            best[i][j] = best[i + 1][j + 1] + 1 if want[i] == seen[j] else max(best[i + 1][j], best[i][j + 1])
    found, i, j = [], 0, 0
    while i < n:
        if j < m and want[i] == seen[j] and best[i][j] == best[i + 1][j + 1] + 1:
            found.append(True)
            i, j = i + 1, j + 1
        elif j < m and best[i][j + 1] >= best[i + 1][j]:
            j += 1
        else:
            found.append(False)
            i += 1
    return found


def check(words, cues, audio, repair=True, low=LOW_CONFIDENCE):
    """What the script expects against what the cues show, for every sound with the same weight.

    For each word, every mouth its letters and vowels call for is looked for, in order, among the
    cues inside the word's time (as the aligner corrected it). Guessed and low-confidence word
    times are counted, and the run is flagged for review when there are too many."""
    timed = align.repair_times(words, align.features(audio)[0]) if repair else words
    expected, shown_n, missing_words, vowels, per_mouth = 0, 0, [], {}, {}
    for i, w in enumerate(timed):
        if w["start"] is None:
            continue
        first = i == 0 or timed[i - 1]["phrase_end"]
        for kind, mouth, _, _ in rules.units(w["text"], first, w["phrase_end"]):
            if kind == "vowel":
                vowels[mouth] = vowels.get(mouth, 0) + 1
        want = expected_mouths(w["text"], first, w["phrase_end"])
        seen = [c["mouth"] for c in cues if c["end"] > w["start"] - align.SLACK and c["start"] < w["end"] + align.SLACK]
        found = in_order(want, seen)
        missing = []
        for m, ok in zip(want, found):
            per_mouth.setdefault(m, [0, 0])
            per_mouth[m][1] += 1
            per_mouth[m][0] += ok
            if not ok:
                missing.append(m)
        expected += len(want)
        shown_n += len(want) - len(missing)
        if missing:
            missing_words.append({"word": w["text"], "at": round(w["start"], 2), "missing": missing})
    shown = {}
    for c in cues:
        shown[c["mouth"]] = round(float(shown.get(c["mouth"], 0) + c["end"] - c["start"]), 2)
    guessed = [w["text"] for w in words if w.get("guessed")]
    unsure = [w["text"] for w in words if not w.get("guessed") and w.get("p") is not None and w["p"] < low]
    share = (len(guessed) + len(unsure)) / max(1, len(words))
    return {
        "words": len(words), "heard": sum(1 for w in words if not w.get("guessed")),
        "guessed": guessed, "low_confidence": unsure, "uncertain_share": round(share, 2),
        "review_needed": share > MAX_UNCERTAIN,
        "no_vowel_marks": [w["text"] for w in words if not rules.has_marks(w["text"]) and len(rules.letters(w["text"])) > 2],
        "sounds_expected": expected, "sounds_shown": shown_n, "words_missing_sounds": missing_words,
        "shown_per_mouth": {m: f"{a}/{b}" for m, (a, b) in sorted(per_mouth.items())},
        "vowels_in_script": vowels, "seconds_per_mouth": shown,
    }


def sh_wanted(mode, mouths):
    if mode != "auto":
        return mode == "on"
    if mouths and any((Path(mouths) / f"sh{ext}").exists() for ext in (".png", ".jpg", ".jpeg")):
        return True
    return rules.USE_SH


def audio_warnings(audio):
    """Recordings that will time worse: a noisy or echoey floor (the quiet parts are not quiet)."""
    loud = align.features(audio)[0]
    out = []
    floor = float(np.percentile(loud, 10))
    if floor > 0.35:
        out.append(f"noisy or echoey recording (quiet parts at {floor:.2f} of full loudness): "
                   "timing may be rougher; a cleaner recording or vocal separation helps")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--out", required=True)
    ap.add_argument("--script")
    ap.add_argument("--words")
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--aligner", choices=("whisper", "mms"), default="whisper")
    ap.add_argument("--dialect", choices=("egy",), default=None)
    ap.add_argument("--fps", type=float, default=30,
                    help="frame rate of the video the mouths go into: every sound is shown for at least one frame")
    ap.add_argument("--mouths", help="the character's mouth pictures folder (used by --sh auto)")
    ap.add_argument("--sh", choices=("auto", "on", "off"), default="auto",
                    help="show ش as the 'sh' mouth. auto: on when --mouths has an sh picture")
    ap.add_argument("--sing", action="store_true", help="singing mode (needs --aligner mms): see sing.py")
    ap.add_argument("--style", choices=("calm", "open"), default="calm",
                    help="--sing only. calm: no wide, short fatha stays mid. open: wide on notes held 0.7 s+")
    ap.add_argument("--bright", type=float, default=None, help="--sing only: brightness share that opens kasra/ي")
    ap.add_argument("--hum-max", type=float, default=None, help="--sing only: longest closed mouth before it is flagged")
    a = ap.parse_args()
    align.MIN_CUE = round(1 / a.fps + 0.0005, 3)
    rules.USE_SH = sh_wanted(a.sh, a.mouths)
    if rules.USE_SH:
        print("ش shown as the 'sh' mouth")
    if a.sing and a.aligner != "mms":
        sys.exit("--sing needs --aligner mms")

    with tempfile.TemporaryDirectory() as tmp:
        audio = to_wav(a.audio, Path(tmp) / "a.wav")
    if a.aligner == "mms":
        if not a.script:
            sys.exit("--aligner mms needs --script (run once without it, with Whisper, to get a transcript)")
        import mms
        script = read_script(a.script)
        if a.sing:
            import sing
            words, cues, track, sung = sing.cues_and_track(audio, script, a.dialect, a.style, a.bright, a.hum_max)
        else:
            words, cues, track = mms.cues_and_track(audio, script, a.dialect)
            sung = None
        report = check(words, cues, audio, repair=False, low=mms.LOW_SCORE)
        report["audio_warnings"] = audio_warnings(audio)
        if sung:
            report["singing"] = sung
        for w in words:
            w["timing"] = "guessed" if w.get("guessed") else "mms"
        write_and_print(a.out, cues, track, words, report, "MMS")
        return
    if a.words and Path(a.words).exists():
        heard = json.loads(Path(a.words).read_text(encoding="utf-8"))
    else:
        heard = whisper_words(audio, a.model)
        if a.words:
            Path(a.words).write_text(json.dumps(heard, ensure_ascii=False, indent=1), encoding="utf-8")

    if not a.script:
        text = Path(a.out).with_suffix(".transcript.txt")
        text.write_text(" ".join(w["text"] for w in heard), encoding="utf-8")
        print(f"No script given. Whisper's transcript is in {text}.")
        print("Add the vowel marks (and fix any wrong words), then run again with --script.")
        return

    script = read_script(a.script)
    words = [dict(m, phrase_end=s["phrase_end"]) for m, s in zip(match([s["text"] for s in script], heard), script)]
    cues, track = align.cues_and_track(audio, words)
    report = check(words, cues, audio)
    for w in words:   # where each word's time came from
        w["timing"] = "guessed" if w.get("guessed") else "whisper"
    write_and_print(a.out, cues, track, words, report, "Whisper")


CHECK_FIRST = 0.5   # aligner scores below this usually mean a wrong word or wrong marks in the script


def write_and_print(out, cues, track, words, report, by):
    first = sorted((w for w in words if w.get("p") is not None and w["p"] < CHECK_FIRST), key=lambda w: w["p"])
    report["check_first"] = [{"word": w["text"], "at": w["start"], "p": w["p"]} for w in first]
    Path(out).write_text(json.dumps({"mouthCues": cues, "mouthTrack": track, "words": words, "report": report}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(cues)} mouth cues -> {out}")
    if first:
        print("CHECK THESE WORDS FIRST (low aligner score: often a wrong word or vowel mark):",
              ", ".join(f"{w['text']} at {w['start']:.2f}s (p {w['p']})" for w in first))
    for warn in report.get("audio_warnings", []):
        print("WARNING:", warn)
    if report.get("singing"):
        s = report["singing"]
        print("singing:", {k: v for k, v in s.items() if k not in ("long_closed",)})
        for c in s.get("long_closed", []):
            print(f"  long closed mouth {c['start']:.2f}-{c['end']:.2f}s ({c['end'] - c['start']:.2f}s): check it in the slow preview")
    print(f"words: {report['heard']} of {report['words']} timed by {by}" + (f"; guessed: {' '.join(report['guessed'])}" if report["guessed"] else ""))
    if report["low_confidence"]:
        print("heard but unsure (check these words):", " ".join(report["low_confidence"]))
    print(f"sounds: {report['sounds_shown']} of {report['sounds_expected']} mouths the script calls for are shown")
    print("  shown per mouth:", report["shown_per_mouth"])
    for s_ in report["words_missing_sounds"]:
        print(f"  missing in {s_['word']} at {s_['at']}s: {' '.join(s_['missing'])}")
    print("vowels in the script:", report["vowels_in_script"])
    print("seconds per mouth:", report["seconds_per_mouth"])
    if report["no_vowel_marks"]:
        print("words without vowel marks (add them for better vowels):", " ".join(report["no_vowel_marks"]))
    if report["review_needed"]:
        print(f"REVIEW NEEDED: {round(report['uncertain_share'] * 100)}% of word times are guessed or unsure"
              f" (limit {round(MAX_UNCERTAIN * 100)}%)."
              " Check those words in the preview, fix the script or the audio, and run again.")
        sys.exit(3)


if __name__ == "__main__":
    main()
