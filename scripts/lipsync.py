"""Arabic lip sync: audio + vowel-marked script -> timed mouth shapes.

Usage:
  python lipsync.py <audio or video> --out mouths.json [--script script.txt] [--words words.json] [--model large-v3]

  --script   the text that was said, with vowel marks (تشكيل). Without it, Whisper's transcript is
             saved to <out>.transcript.txt and the script stops: add the vowel marks, then re-run.
  --words    a file for Whisper's word times: read if it exists, written if not (saves re-running Whisper).
Writes mouths.json: {"mouthCues": [{"start", "end", "mouth"}], "words": [...], "report": {...}}
and prints a check of closures and vowels against the script.
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

PHRASE_END = ".،؟!:؛?,"


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


def check(words, cues, audio):
    """What the script expects against what the cues show.

    Closures are counted as events, one per ب/م (a doubled مّ is one long closure), and compared
    word by word, using the word times as the aligner corrected them. Guessed and low-confidence
    word times are counted, and the run is flagged for review when there are too many."""
    timed = align.repair_times(words, align.features(audio)[0])
    closed = [c for c in cues if c["mouth"] == "closed"]
    expected, short, vowels = 0, [], {}
    for i, w in enumerate(timed):
        if w["start"] is None:
            continue
        us = rules.units(w["text"], i == 0 or timed[i - 1]["phrase_end"], w["phrase_end"])
        need = sum(1 for k, u in enumerate(us) if u[1] == "closed" and not (k and us[k - 1][1] == "closed" and us[k - 1][3] == u[3]))
        expected += need
        for kind, mouth, _, _ in us:
            if kind == "vowel":
                vowels[mouth] = vowels.get(mouth, 0) + 1
        if need:
            got = sum(1 for c in closed if c["end"] >= w["start"] - align.SLACK and c["start"] <= w["end"] + align.SLACK)
            if got < need:
                short.append({"word": w["text"], "at": round(w["start"], 2), "expected": need, "shown": got})
    shown = {}
    for c in cues:
        shown[c["mouth"]] = round(float(shown.get(c["mouth"], 0) + c["end"] - c["start"]), 2)
    guessed = [w["text"] for w in words if w.get("guessed")]
    unsure = [w["text"] for w in words if not w.get("guessed") and w.get("p") is not None and w["p"] < LOW_CONFIDENCE]
    share = (len(guessed) + len(unsure)) / max(1, len(words))
    return {
        "words": len(words), "heard": sum(1 for w in words if not w.get("guessed")),
        "guessed": guessed, "low_confidence": unsure, "uncertain_share": round(share, 2),
        "review_needed": share > MAX_UNCERTAIN,
        "no_vowel_marks": [w["text"] for w in words if not rules.has_marks(w["text"]) and len(rules.letters(w["text"])) > 2],
        "closures_expected": expected, "closures_shown": len(closed), "words_short_of_closures": short,
        "vowels_in_script": vowels, "seconds_per_mouth": shown,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--out", required=True)
    ap.add_argument("--script")
    ap.add_argument("--words")
    ap.add_argument("--model", default="large-v3")
    a = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        audio = to_wav(a.audio, Path(tmp) / "a.wav")
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
    cues = align.cues(audio, words)
    report = check(words, cues, audio)
    for w in words:   # where each word's time came from
        w["timing"] = "guessed" if w.get("guessed") else "whisper"
    Path(a.out).write_text(json.dumps({"mouthCues": cues, "words": words, "report": report}, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{len(cues)} mouth cues -> {a.out}")
    print(f"words: {report['heard']} of {report['words']} heard by Whisper" + (f"; guessed: {' '.join(report['guessed'])}" if report["guessed"] else ""))
    if report["low_confidence"]:
        print("heard but unsure (check these words):", " ".join(report["low_confidence"]))
    print(f"closures: {report['closures_shown']} shown for {report['closures_expected']} ب/م in the script")
    for s_ in report["words_short_of_closures"]:
        print(f"  fewer closures than expected: {s_['word']} at {s_['at']}s ({s_['shown']} of {s_['expected']})")
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
