---
name: arabic-lip-sync
description: Time a cartoon or avatar's mouth to Arabic speech (fusha or dialect). Takes a voice recording plus the vowel-marked text, finds where each letter and vowel is said, and gives each moment a mouth shape (closed for ب م, round for damma and و, wide for long ا, and so on) from rules measured on a real speaker's mouth. Outputs a mouth-timing JSON and an optional preview video from the character's mouth pictures. Use whenever someone wants an Arabic-speaking character to talk, asks for Arabic lip sync or mouth animation (مزامنة الشفاه، حركة الفم), or has Arabic voice audio that needs mouth shapes, even if they don't say "lip sync".
---

# Arabic lip sync

Turns Arabic speech into timed mouth shapes. The timing comes from the sound itself; the shapes come
from the vowel-marked text, using rules measured frame by frame from a real speaker's video
(details and numbers in `references/mouth_shapes.md`).

Everything runs locally. Ask the user before installing or downloading anything.

## 1. Check the setup

```bash
python scripts/setup_check.py
```

Needs ffmpeg, Python with `numpy` and `faster-whisper` (tested versions in `requirements.txt`), and the
Whisper `large-v3` model (about 3 GB). If something is missing, tell the user what and how big, and wait
for their OK before installing. `--model medium` works with a smaller model, with rougher word times.
`python tests/test_rules.py` checks the script rules and cue cleanup without any audio.

## 2. Get the vowel-marked script

The mouth shapes depend on the vowels, so the text needs تشكيل (fatha, kasra, damma, sukun, shadda,
long vowels). One sentence or phrase per line; a line end or punctuation marks a pause.

- **The user gave the text with vowel marks:** use it as is.
- **The user gave text without marks:** add them yourself, following `references/adding_vowel_marks.md`,
  and show the user the marked text to check before running. Dialect words are marked as they are said,
  not as in fusha.
- **No text at all:** run step 3 without `--script`. Whisper's transcript is saved next to the output;
  fix wrong words, add the marks, and show the user before running again.

## 3. Run

```bash
python scripts/lipsync.py <audio or video> --out mouths.json --script script.txt --words words.json
```

`--words` keeps Whisper's word times in a file, so later runs (after fixing the script) skip Whisper.
Any audio or video format works; it is converted to 16 kHz mono first.

Output `mouths.json`:
```json
{"mouthCues": [{"start": 0.0, "end": 1.18, "mouth": "rest"}, {"start": 1.18, "end": 1.31, "mouth": "closed"}],
 "words": [...], "report": {...}}
```
To use the cues in a video, the mouth at frame `n` is the cue where `start <= n / fps < end`.

## 4. Read the check

The script prints, and `report` holds:
- **words heard / guessed / unsure:** words Whisper didn't hear get their time shared out from their
  neighbours (`"timing": "guessed"` on the word); words heard with low confidence are listed as unsure.
  Numbers said in words (٩٨٤٣ read out) are often guessed: their time is only as good as the words around them.
- **REVIEW NEEDED (exit code 3):** more than 15% of word times are guessed or unsure. The cues are still
  written, but **stop and show the user the listed words** before using them: usually the script doesn't
  match what was said. Fix the script (or the audio) and run again.
- **closures shown for ب/م:** each ب/م is counted on its own (a doubled مّ is one long closure).
  Words listed as "fewer closures than expected" are worth checking in the preview; lips that don't
  close on ب/م are the most visible mistake in lip sync.
- **words without vowel marks:** add marks to these and re-run.
- **seconds per mouth:** a quick sanity check (lots of `rest` in the middle of speech means the timing slipped).

## 5. Preview (optional)

```bash
python scripts/render_preview.py mouths.json <audio> <mouth pictures folder> preview.mp4 --slow
```

The folder holds one picture per mouth, same size, named by mouth: `rest closed f small mid wide round aw sh`
(.png or .jpg), all the same size. A missing mouth uses the nearest one the character has, and the
stand-ins are printed **before** rendering; add `--strict` to refuse stand-ins (use it for anything final).
A character with just rest, closed, small, mid, wide and round works; tell the user which of `f`, `aw`
and `sh` their character lacks, since those make Arabic look more right. `--slow` adds a half-speed copy
for checking closures by eye.

## Mouths

| mouth | when | looks like |
|---|---|---|
| rest | silence | lips together, relaxed |
| closed | ب م | lips pressed (about 0.1 s in normal speech) |
| f | ف | lower lip pulled in under the top teeth |
| small | kasra, long ي, most consonants | nearly shut, lips spread |
| mid | fatha | lips apart, top teeth showing |
| wide | long ا / ى, fatha on ع ء | widest opening |
| round | damma, long و, consonant و | lips pushed out, mouth narrower |
| aw | off by default: fatha / long ا after ص ض ط ظ ق خ ر | open and rounded |
| sh | off by default: ش | lips pushed out and open |

`aw`, `sh` and rounding the consonant before a damma are all real (clearly seen in slow speech), but
made normal speech match the real mouth less well, so they are off. Switch them on in `scripts/rules.py`
(`HEAVY_ROUND`, `USE_SH`, `ROUND_BEFORE_DAMMA`) for slow, careful speech or a character that has those mouths.

## Things to know

- Don't pass the script to Whisper as a prompt: it then skips the words it was told about.
  `lipsync.py` matches Whisper's words to the script in order instead.
- Script handling (in `scripts/rules.py`): silent alef in ذَهَبوا and كوبًا, the ل of ال before sun
  letters, hamzat wasl, the last short vowel dropped at a pause, tanween, shadda (the letter is given as
two units, so it is held about twice as long),
  diphthongs (aw round, ay spread).
- Some speakers' ر sounds like غ, or barely sounds at all. The mouth for ر is placed from the script,
  never from the sound, so this doesn't matter as long as the script is right.
- The rules were measured from one speaker. They describe a real mouth; a cartoon needs its own
  drawing for each mouth.
