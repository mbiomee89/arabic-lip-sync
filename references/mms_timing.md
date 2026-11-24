# MMS timing: how it works, what was measured, setup

`lipsync.py --aligner mms` places every letter and vowel with Meta's MMS forced aligner (torchaudio
`MMS_FA`). It is the default for final timing in this skill's workflow; Whisper's word times are only
the fallback. Whisper (default `--aligner whisper`) gives back-to-back word times: it can't show where
a held or sung vowel starts and ends, so mouths close early on long notes, and after a pause a word
can be off by up to 1 s. MMS needs `--script` (no script yet: run once without it for Whisper's
transcript). About 30 s for 35 s of audio on CPU.

## How it times the sounds (`scripts/mms.py`)
- The script's sounds (`rules.units`) are written in Latin letters sound by sound (`scripts/translit.py`:
  بَ→ba, long ا→aa, ي after kasra→ii, و after damma→uu, shadda→the letter twice, sukun→no vowel,
  ء and ع→`'`), so every aligned letter maps back to its own Arabic letter or vowel.
  `--dialect egy` says ج as g and ث ذ ظ as t d z. Egyptian ق said as ء is written ء in the script.
- Each sound starts at its aligned onset, corrected the same way for every letter of a kind (stops and
  nasals end at the burst, hissing letters start where the hiss rises).
- A vowel holds until the next sound starts, so it covers the whole held note.
- A word (note) ends where the voice really stops: pyin voiced AND level above loudest − 24 dB, gaps
  under 0.08 s bridged, so reverb tails don't keep the mouth open.
- A word-final consonant goes at the END of the note (vowel held, then the closure / f / hiss), never
  in the middle of a held vowel. A final hissing letter (ش س ف…) keeps going while it still hisses, up
  to 0.35 s past the usual room (fixed 2026-11-23: in مْشْ the quiet م hum ended the word before the ش
  hiss, and the ش mouth disappeared). Silent or unaligned gaps over 0.08 s become `rest`.
- Words get `"timing": "mms"`; `p` is the mean MMS score of their letters. Under 0.3: unsure; under 0.5:
  listed in the report's "check these words first" (on the song test these were exactly the wrong lyrics).
- Very fast stretches (six sounds in 0.13 s, like a quick وَأَنا) are faster than the frame rate. MMS
  gives them their true, crowded times, so `tidy()` joins look-alike neighbours there.

## Measured
- 35 s of Egyptian speech (`--dialect egy`): phrase starts off by 29 ms on average with mms vs 99 ms with Whisper (worst 80 vs 400 ms), phrase ends 15 vs 41 ms, 247 vs 246 of
  252 mouths shown, 4 vs 6 unsure/guessed words.
- 2026-11-23 TTS lyrics (an ElevenLabs voice, Egyptian, 10 s): 21/21 words, 75/75 mouths with the final-hiss fix.
- 2026-11-23 Egyptian song (female singer, 18 s, separated vocals): timing mostly within 0.05 s of the voice;
  the problems were mouth SHAPES (see `--sing` in SKILL.md and `scripts/sing.py`).

## Setup (ask the user before each download; put it on a drive with room)
- A separate venv with CPU torch + torchaudio (~730 MB). Default place: `~/envs/lipsync-mms`; anywhere
  else: set `LIPSYNC_MMS_PYTHON` to its python. `--no-cache-dir` keeps pip's cache from filling the disk:
  `python -m venv ~/envs/lipsync-mms` then (Windows: `Scripts\pip`, Mac / Linux: `bin/pip`)
  `~/envs/lipsync-mms/Scripts/pip install --no-cache-dir torch torchaudio soundfile --index-url https://download.pytorch.org/whl/cpu`
- MMS model (1.2 GB) at `TORCH_HOME/hub/checkpoints/model.pt`. `TORCH_HOME` is `LIPSYNC_TORCH_HOME`,
  else `TORCH_HOME`, else `~/.cache/torch`. The skill never downloads it by itself; to get it once:
  `<venv python> -c "import torchaudio; torchaudio.pipelines.MMS_FA.get_model()"` (with the same `TORCH_HOME` set).
- Demucs (songs) is in the same venv; its model `htdemucs` is in the Hugging Face cache
  (`HF_HOME`), as are the Whisper models.
- `python scripts/setup_check.py --job speech|song --voice ...` checks what a job needs.
