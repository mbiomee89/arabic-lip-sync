# arabic-lip-sync

A free [Claude Code](https://claude.com/claude-code) skill that makes a cartoon or avatar's mouth move correctly with **Arabic** speech, in fusha or in dialect.

You give it a voice recording and the text with vowel marks (تشكيل). It finds when each letter and vowel is said, and gives each moment a mouth shape:
- **closed** for ب and م.
- **round** for damma and و.
- **wide** for long ا.

The rules were measured frame by frame from a real speaker's filmed mouth.

**What you get:**
- `mouths.json`: the timed mouth shapes, ready for any animation tool.
- Optionally, a preview video made from your character's mouth pictures.

Everything runs on your own computer. Nothing is uploaded.

> سكيل مجانية لـ Claude Code بتحرّك بُق الكرتون مع الكلام العربي صح.
> بتديها التسجيل الصوتي والكلام مكتوب بالتشكيل، وهي بتطلّعلك توقيت حركة البُق لكل حرف.

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
- Python 3.10 or newer.
- The Python packages:
  ```bash
  pip install -r requirements.txt
  ```
- The Whisper `large-v3` model, about 3 GB. It downloads once, the first time you run the skill. `--model medium` uses a smaller model, with rougher timing.

To check your setup:
```bash
python scripts/setup_check.py
```

## Use

In Claude Code, just ask, for example:

> Lip-sync `voice.wav` to this text: «أنا بتكلم عربي»

Claude adds the vowel marks if they're missing and shows you the marked text. Then it runs the skill and tells you which words to check.

**Or run it yourself:**
```bash
python scripts/lipsync.py voice.wav --out mouths.json --script script.txt --words words.json
python scripts/render_preview.py mouths.json voice.wav mouth_pictures/ preview.mp4 --slow
```

**The script file:**
- One sentence per line, with vowel marks.
- Write dialect words as they're said. For example, Egyptian «ق» is written «ء»: بُؤّي.

**The mouth pictures folder:**
- One picture per mouth, all the same size.
- Named `rest closed f small mid wide round aw sh` (.png or .jpg).
- A character with only `rest closed small mid wide round` still works.

**Using the output:** the mouth at video frame `n` is the cue where `start <= n / fps < end`.

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
| aw, sh | off by default (see `SKILL.md`) |

**More detail:**
- `SKILL.md`: the full workflow.
- `references/mouth_shapes.md`: how the rules were measured.
- `references/adding_vowel_marks.md`: how to mark dialect text.

## Limits

- The rules come from one speaker's mouth. Treat them as a strong starting point, not a final word.
- Word times come from Whisper. When it isn't sure, the skill prints **REVIEW NEEDED** and lists the words to check.
- Check the ب/م closures in the slow preview before using the result in a final video.

## License

MIT. Free to use, change and share, including commercially.
