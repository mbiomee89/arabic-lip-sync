# The voice (step 1b)

Ask: **"Do you have a recording of the voice?"**
- **Yes:** take the file (any audio or video format). A song: ask which part (start–end), then
  separate the vocals (step 3).
- **No:** ask **"Free, or best quality?"**, show the options below, recommend one, and **wait for the
  user's choice**. Never install, download or spend credits without their OK.

Recommend: **free → Edge voices** (or recording themselves, for a personal voice);
**best → ElevenLabs** (natural, dialect via accent tags).

## Free

| option | Arabic quality | notes |
|---|---|---|
| **Record yourself** (phone or PC mic) | real voice, matches the character's personality | quiet room, close to the mic, any format |
| **Microsoft Edge voices** (`pip install edge-tts`, small) | natural; Egyptian, Saudi, Gulf, Levantine, Maghrebi and more | uses Microsoft's online service with no official free plan: fine for tests, not a promise for commercial use. **Not yet tested with this skill** (the install wasn't run on 2026-11-23); test one line before relying on it |
| **XTTS v2** (local, Coqui) | good; can copy a voice from a short sample | ~2 GB, better with a GPU; weak accent control |
| **Meta MMS-TTS Arabic** (local) | understandable but robotic | small and offline; fusha only |

Edge example (after the user OKs the install):
```bash
python -m edge_tts --list-voices | grep ^ar-          # pick a voice, e.g. an ar-EG or ar-SA one
python -m edge_tts --voice <name> --file line.txt --write-media voice.mp3
```

## Paid

| option | Arabic quality | notes |
|---|---|---|
| **ElevenLabs** (connector or website) | very natural, many Arabic voices, accent tags work | credits per take. Measured 2026-11-23 with eleven_v4: a 6 s line ≈ 80–130 credits, 10 s of lyrics ≈ 230 |
| **Azure Speech** | the same voices as Edge, official, with control of speed, pitch and pauses | pay per character, small monthly free tier |
| **Google Cloud TTS** | clear standard Arabic | weaker on dialects |
| **OpenAI TTS** | natural but with a foreign accent in Arabic | cheap; tests only |

## ElevenLabs through the connector (tested)
1. `creative_list_voices` with `languages: ["ar"]` (and gender/age if given); or the user names a
   voice. An English voice with an accent tag also works (tested: Sarah).
2. Show the user: the text, voice, model (`eleven_v4`) and **the expected credits**. Wait for go.
3. `creative_generate_speech` with `generations_count: 1`. Put the dialect as a tag at the start:
   `[Egyptian Arabic accent, spoken calmly] …` or `[Saudi Arabic accent, Riyadh dialect] …`.
   The tag is not read aloud (checked with Whisper).
4. Download the mp3 from `creative_get_generations` (`full_res_url`), then check the words with
   Whisper (`lipsync.py voice.mp3 --out check.json` with no script prints the transcript).

## Words the voice says wrong
TTS often skips vowel marks inside a long dialect word (tested: a long contracted word lost a syllable,
then got a hamza with the wrong vowel). Then:
- **Test that one line first** (cheap), not the whole text again.
- Write a **voice spelling**: split the word and start the hard sound as its own chunk
  (for example `ما بِيِعْرَفْش`; splitting is what worked in the test).
- Keep a separate **timing spelling** in the script for lipsync.py, written as it is said
  (`مَبْيِعْرَفْشْ`). The two spellings are allowed to differ.
