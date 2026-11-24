---
name: arabic-lip-sync
description: Make an Arabic-speaking or singing cartoon/avatar video, end to end - the character's 9 mouth pictures (with an image prompt for a 3x3 mouth sheet), the voice (the user's recording, or free/paid TTS options), letter-exact mouth timing for Arabic speech or songs (fusha or dialect), a review loop, and the final video. Timing comes from the sound; mouth shapes come from the vowel-marked text (closed for ب م, round for damma and و, open for fatha/ا, sh for ش…), measured on a real speaker, with a singing mode for songs. Use whenever someone wants an Arabic-speaking or singing character, asks for Arabic lip sync or mouth animation (مزامنة الشفاه، حركة الفم), has Arabic voice or a song that needs mouth shapes, or has a character picture they want to make talk, even if they don't say "lip sync".
---

# Arabic lip sync: character video, step by step

The user decides at every step. **Show what you will do and wait for their go before running,
installing, downloading, generating (credits) or rendering.** Reading and measuring to answer a
question is fine. An earlier OK does not cover the next step.

Scripts are in `scripts/`, run with the user's Python (the MMS parts use the torch venv by themselves).

## 0. The character's mouths
Needed: a folder with 9 same-size pictures named `rest closed f small mid wide round aw sh` (.png/.jpg).
- **No folder:** ask for one image of the character (front-facing, mouth visible). Give the user the
  prompt in `references/mouth_sheet_prompt.md` for their image tool. When the 3×3 sheet comes back:
  `python scripts/mouth_pictures.py cut sheet.png mouths/` (other panel orders: `--order ...`).
  It lines up the panels, pastes ONLY the mouths onto `rest`, and writes `mouths/contact_sheet.png`.
  Show the contact sheet; read any WARNING about a drifting panel; wait for the user's OK.
- **A folder already exists:** `python scripts/mouth_pictures.py check mouths/`. If it says SHIMMER,
  offer `--fix` (writes `mouths_fixed/`, originals untouched), show its contact sheet, use it only
  after the user's OK. Tell the user which mouths are missing (stand-ins will be used).
- Under about 400 px a mouth looks soft in a final video; say so.

## 1. Text and voice
**a) Text.** Ask for the line or lyrics and the dialect (fusha, Egyptian, Saudi, Gulf…).
- Mouth shapes depend on the vowels, so the script needs تشكيل. One phrase per line; a line end or
  punctuation is a pause. Text without marks: add them (`references/adding_vowel_marks.md`, which also
  covers dialect and songs), **show the marked text and wait for the user's OK**. Mark words as they are
  SAID or SUNG, not as written (Egyptian ق as ء, a contraction as one word).
- No text at all: run step 4 once without `--script`; Whisper's transcript is saved next to the
  output. Fix it with the user, add marks, show, then continue. For songs, ask the user for the real
  lyrics: Whisper on singing is unreliable even on separated vocals.
- If a TTS voice will read the text, keep two spellings: a **voice spelling** for the TTS and the
  **timing spelling** (fully marked, as said) for the script (`references/voice_options.md`).

**b) Voice.** Ask: "Do you have a recording?"
- **Yes:** take the file (any audio/video format). A song: ask which part (start–end).
- **No:** ask "free, or best quality?", show the options in `references/voice_options.md`, recommend
  (free → Edge voices or recording themselves; best → ElevenLabs), and wait for their choice.
  Paid: state the expected cost first. Never pick or pay for a voice on your own.

## 2. Tools for this job
```bash
python scripts/setup_check.py --job speech|song --voice none|edge|xtts|mmstts|elevenlabs
```
Checks only what THIS job needs: always ffmpeg, numpy, librosa, Pillow and the MMS aligner; Whisper
for checking words; Demucs for songs; the voice tool the user picked. If something is missing, tell
the user what and how big, ask before installing, and offer the fallback if they say no (Whisper
`--model medium`: rougher checks; no MMS: `--aligner whisper`, about 0.1 s rougher and worse on songs).
Setup details: `references/mms_timing.md`.

## 3. Prepare the audio
- **Song:** cut the part (`ffmpeg -ss START -to END -i song -vn clip.wav`), then separate the vocals:
  `<mms venv python> -m demucs -n htdemucs --two-stems=vocals -o sep clip.wav`
  → `sep/htdemucs/clip/vocals.wav`. **Time on the vocals; play the full clip in the video.**
- **TTS:** generate one take after the user OKs the cost (`references/voice_options.md` has the
  ElevenLabs connector steps). Check the words: `python scripts/lipsync.py voice.mp3 --out check.json`
  (no `--script`) writes the transcript. A word said wrong: test that ONE line with a new voice
  spelling (cheap) before generating the whole text again.
- **Recording:** use it as is. The report warns when it is noisy or echoey.

## 4. Timing
```bash
# speech
python scripts/lipsync.py voice.mp3 --out mouths.json --script script.txt --aligner mms [--dialect egy] --mouths mouths/ --fps 30
# song (on the separated vocals)
python scripts/lipsync.py vocals.wav --out mouths.json --script lyrics.txt --aligner mms [--dialect egy] --mouths mouths/ --fps 30 --sing --style calm|open
```
- `--aligner mms` places every letter and vowel (how and why: `references/mms_timing.md`).
- `--mouths` + `--sh auto` (default): ش shows the `sh` mouth when the character has `sh.png`.
- `--fps` = the final video's frame rate; every sound gets at least one frame.
- **Songs: ask the style before running, every song** (tastes differ): `calm` = no wide mouth, a
  short fatha stays medium (the tested user's choice); `open` = wide only on notes held 0.7 s or more.
  `--sing` also starts vowels when the singer opens, opens kasra/ي the singer sings open (measured
  from the voice), closes on sung م/ن hums, and lets long notes move with the voice. Details and
  settings (`--bright`, `--hum-max`) at the top of `scripts/sing.py`.

## 5. Read the report before rendering
- **CHECK THESE WORDS FIRST** (aligner score under 0.5): usually a wrong word or vowel mark. Show them
  to the user before anything else.
- **REVIEW NEEDED** (exit code 3): over 15% of words guessed/unsure. Stop, show the words, fix the text.
- **sounds shown / missing:** each mouth a word calls for, looked for in order. A miss is worth a look.
  With `--sing` the count is lower on purpose (it is counted against the speech shapes, and `--sing`
  opens some of them): the tested song showed 69 of 75. Judge songs in the slow preview.
- **long closed mouth** (songs): a closed mouth over 0.4 s, often a hummed م; check it by eye.
- **WARNING noisy or echoey recording:** timing may be rougher.
- **seconds per mouth:** lots of `rest` inside speech means the timing slipped.

## 6. Preview
```bash
python scripts/render_preview.py mouths.json <full audio> mouths/ preview.mp4 --slow --strict
```
Send both videos (normal and `_slow`), and ask the user to watch the slow one. `--strict` refuses stand-in
mouths; without it, missing mouths borrow the nearest one (listed before rendering).

## 7. The review loop
- The user names the word or moment. **Measure the voice there and explain the cause before changing
  anything**: wrong word, wrong mark, mouth too open/closed, timing. Use RMS loudness (librosa) when
  measuring; a quick spectrum sum misled once.
- Propose the fix, wait for go, then make the next version (`v2`, `v3`…). Never overwrite a version.
- Show what changed: `python scripts/compare.py mouths_v2.json mouths_v3.json`.
- Note the user's taste for the next run (for example: no wide mouth, short fatha stays medium).

## 8. Final video
Ask the format: size (1080x1920 Reels/Shorts, 1080x1080 square, 1920x1080 wide), background
colour, frame rate (the same as step 4's `--fps`). Then:
```bash
python scripts/render_preview.py mouths.json <full audio> mouths/ final.mp4 --strict --size 1080x1920 --bg white --fps 30
```
Hand over the video and `mouths.json` (for After Effects, Remotion, a game engine…).
Blinks, head movement and in-between mouths are not part of this skill yet.

## Mouths and rules

| mouth | when | looks like |
|---|---|---|
| rest | silence | lips together, relaxed |
| closed | ب م, the Jazan article امْ | lips pressed (about 0.1 s in normal speech) |
| f | ف | lower lip pulled in under the top teeth |
| small | kasra, long ي, most consonants | nearly shut, lips spread |
| mid | fatha | lips apart, top teeth showing |
| wide | long ا / ى, fatha on ع ء | widest opening |
| round | damma, long و, consonant و | lips pushed out, mouth narrower |
| aw | off by default: fatha / long ا after ص ض ط ظ ق خ ر | open and rounded |
| sh | ش, when the character has an sh mouth (`--sh auto`) | lips pushed out and open |

`aw` and rounding the consonant before a damma are real but made normal speech match a real mouth
less well, so they are off (`HEAVY_ROUND`, `ROUND_BEFORE_DAMMA` in `scripts/rules.py`).

Every letter has the same priority: every sound gets at least one frame (a short one borrows time
from its neighbours; only speech faster than the frame rate joins look-alike neighbours); every stop
and nasal ends where the sound bursts open, every hissing letter follows its hiss; the report checks
every mouth a word calls for.

Output `mouths.json`: `mouthCues` (one picture at a time; the mouth at frame n is the cue with
`start <= n/fps < end`), `mouthTrack` (a smooth open/width/round curve for rigs, every 1/rate s),
`words`, `report`.

## Things to know
- In songs, most problems were mouth SHAPES, less often timing (tested 2026-11-23); use `--sing`.
- Don't pass the script to Whisper as a prompt: it then skips the words it was told about.
- Script handling (`scripts/rules.py`): silent alef in ذَهَبوا and كوبًا, the ل of ال before sun
  letters, hamzat wasl, the last short vowel dropped at a pause, tanween, shadda (held about twice as
  long), diphthongs (aw round, ay spread), the Jazan article امْ, `…` as a pause.
- The mouth for ر is placed from the script, never from the sound (some speakers' ر sounds like غ).
- The rules were measured from one speaker; `--sing`'s brightness setting from one female singer.
  Check other voices in the slow preview.
- `python tests/test_rules.py` checks the rules without audio.
