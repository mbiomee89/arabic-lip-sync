# arabic-lip-sync

A free [Claude Code](https://claude.com/claude-code) skill that makes a cartoon or avatar talk, or sing, in **Arabic** (fusha or dialect), with the mouth moving correctly for every letter.

Claude takes you through it step by step and waits for your OK at each one:
1. **The character's 9 mouths:** give it one picture of your character. It gives you an image prompt for a 3×3 sheet of mouths, then cuts the sheet and pastes only the mouths onto the face, so nothing else flickers.
2. **The text and the voice:** your own recording, or a text-to-speech voice (free and paid options). It adds the vowel marks (تشكيل) and shows them to you before going on.
3. **The timing:** it finds where each letter and vowel is said or sung, and gives each moment a mouth shape:
   - **closed** for ب and م;
   - **round** for damma and و;
   - **open** for fatha and long ا;
   - **sh** for ش, and more.
4. **A slow preview, then fixes,** until you're happy.
5. **The final video** (Reels/Shorts, square or wide), plus `mouths.json` for any animation tool.

The mouth rules were measured frame by frame from a real speaker's filmed mouth. Every letter gets the same care: each sound is shown for at least one video frame.

Everything runs on your own computer. Nothing is uploaded, except to a voice service if you pick one.

> سكيل مجانية لـ Claude Code بتخلّي الكرتون يتكلم أو يغني بالعربي، والبُق بيتحرك صح مع كل حرف.
> بتديها صورة الشخصية والتسجيل الصوتي والكلام، وهي بتمشي معاك خطوة خطوة لحد الفيديو النهائي.

## What's new in v2.0
- **Letter-exact timing** (`--aligner mms`, Meta's MMS forced aligner). On 35 s of Egyptian speech, phrase starts were off by 29 ms on average, against 99 ms with Whisper alone.
- **Singing mode** (`--sing`), for songs, held notes and sung hums, with a `calm` or `open` style.
- **Mouth pictures:** an image prompt for a 3×3 sheet, plus `mouth_pictures.py` to cut it, check a folder for flicker, and fix it.
- **Voice options:** recording yourself, free TTS or ElevenLabs, with the costs up front.
- **A review loop:** `compare.py` shows what changed between versions.
- **Final videos** with `render_preview.py --size 1080x1920 --bg white`.
- **The ش mouth** is shown when your character has one (`--sh auto`).

## Install

**Option 1: download the ZIP (easiest)**
1. Download `arabic-lip-sync.zip` from the [latest release](../../releases/latest).
2. Unzip it into your Claude Code skills folder:
   - Windows: `C:\Users\<you>\.claude\skills\`
   - Mac / Linux: `~/.claude/skills/`
3. You should now have `.claude/skills/arabic-lip-sync/SKILL.md`.

**Option 2: git**
```bash
git clone https://github.com/mbiomee89/arabic-lip-sync ~/.claude/skills/arabic-lip-sync
```

**What it needs:**
- [ffmpeg](https://ffmpeg.org).
- Python 3.10 or newer, and `pip install -r requirements.txt`.
- **For letter-exact timing:** a separate Python venv with CPU `torch` and `torchaudio` (about 730 MB), and the MMS model (1.2 GB). The steps are in `references/mms_timing.md`. The default places are `~/envs/lipsync-mms` and `~/.cache/torch`; set `LIPSYNC_MMS_PYTHON` and `LIPSYNC_TORCH_HOME` to use another drive. Without it, `--aligner whisper` still works, about 0.1 s rougher.
- **For checking words:** the Whisper `large-v3` model (about 3 GB). It downloads once, the first time.
- **For songs:** Demucs, in the same venv, to separate the vocals.

The skill never installs or downloads anything without asking. To see what a job needs:
```bash
python scripts/setup_check.py --job speech      # or --job song
```

## Use

In Claude Code, just ask, for example:

> Make my character say «أنا بتكلم عربي» in Egyptian. Here's the picture: `character.png`

**Or run it yourself:**
```bash
python scripts/mouth_pictures.py cut sheet.png mouths/
python scripts/lipsync.py voice.wav --out mouths.json --script script.txt --aligner mms --dialect egy --mouths mouths/ --fps 30
python scripts/render_preview.py mouths.json voice.wav mouths/ preview.mp4 --slow --strict
```
For a song, run on the separated vocals and add `--sing --style calm` (or `open`).

**The script file:**
- One phrase per line, with vowel marks.
- Write words as they're said or sung. For example, Egyptian «ق» is written «ء»: بُؤّي.

**The mouth pictures folder:**
- 9 pictures, all the same size, named `rest closed f small mid wide round aw sh` (.png or .jpg).
- A character with only `rest closed small mid wide round` still works.

**Using the output:** the mouth at video frame `n` is the cue where `start <= n / fps < end`. `mouthTrack` gives a smooth open / width / round curve for rigs.

## Mouth shapes

| mouth | when |
|---|---|
| rest | silence |
| closed | ب م |
| f | ف |
| small | kasra, long ي, most consonants |
| mid | fatha |
| wide | long ا, fatha on ع ء |
| round | damma, long و |
| sh | ش, when the character has an sh mouth |
| aw | off by default (see `SKILL.md`) |

**More detail:**
- `SKILL.md`: the full workflow.
- `references/mms_timing.md`: how letter-exact timing works, test results and setup.
- `references/mouth_sheet_prompt.md`: the image prompt for the 9 mouths.
- `references/voice_options.md`: voices, free and paid.
- `references/adding_vowel_marks.md`: how to mark dialect text and lyrics.
- `references/mouth_shapes.md`: how the rules were measured.

## Limits

- The mouth rules come from one speaker, and singing mode was tuned on one female singer. They're a strong starting point; check new voices in the slow preview.
- When a word looks wrong, the report lists it under **CHECK THESE WORDS FIRST** or **REVIEW NEEDED**. It's usually a wrong word or vowel mark in the script.
- Blinks, head movement and in-between mouths aren't part of the skill yet.

## License

MIT. Free to use, change and share, including commercially.
