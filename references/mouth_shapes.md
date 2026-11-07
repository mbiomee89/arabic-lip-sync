# How the mouth rules were measured

## Recording
One speaker read a 5.5-minute script on video:
- **A syllable table:** 28 letters, each with fatha, kasra, damma, long ا, long ي, long و and sukun, so 196 syllables.
- **8 fusha sentences.**
- **4 dialect sentences.**

The details:
- The video was 30 fps, 9,843 frames.
- A face tracker (MediaPipe Face Landmarker) found the face on every frame.
- Every measure was divided by face width, so camera distance doesn't matter.

## Measures per frame
- **open:** the gap between the inner lip edges.
- **width:** mouth corner to corner.
- **height:** outer lip edge to edge. It drops when the lips press together.
- **lower lip:** the thickness of the lower lip. It thins when the lip is pulled in or pressed.
- **pucker:** the tracker's lip-pucker score.

**Timing:**
- Syllables were timed from the pauses between them.
- Sentence words were timed by Whisper large-v3 and matched to the script.

## Measured mouth types (centre values, face-width units)
| mouth | open | width | height | lower lip | pucker | samples |
|---|---|---|---|---|---|---|
| rest | 0.019 | 0.366 | 0.171 | 0.099 | 0.41 | 1434 frames |
| closed (ب م) | 0.014 | 0.361 | **0.138** | **0.079** | 0.36 | 8 |
| f (ف) | 0.014 | 0.368 | **0.128** | **0.074** | 0.15 | 4 |
| small (kasra, long ي) | 0.026 | 0.376 | 0.177 | 0.098 | 0.40 | 56 |
| mid (fatha) | **0.077** | 0.371 | 0.234 | 0.102 | 0.29 | 19 |
| wide (long ا) | **0.118** | 0.384 | 0.264 | 0.097 | 0.14 | 19 |
| aw (a after heavy letters) | 0.085 | **0.316** | 0.234 | 0.093 | **0.85** | 14 |
| round (damma, و) | 0.023 | **0.289** | 0.166 | 0.082 | **1.00** | 60 |
| sh (ش) | 0.045 | 0.370 | 0.232 | 0.121 | 0.55 | 4 |

**What the table shows:**
- Closed lips are about 20% lower than rest. They're pressed, not just touching.
- The "small" mouth for kasra and long ي is almost the same as rest. A wider "ee" mouth would be wrong for this speaker.
- Round is 20% narrower than rest.
- ف differs from ب/م mainly by the lower lip being pulled in.

## Timing measured
- **Closures in sentences:** ب/م closures last 0.07 to 0.13 s, typically 0.10 s.
- **Voice before the lips open:** for ب/م the voice starts while the lips are still closed. They open about 0.06 s later.
- **Long vowels:** a syllable with a long vowel lasts about 1.5 times a short one.
- **ع:** fatha on ع opens as wide as a long ا.

## Test on running speech
**Preliminary results:** one speaker, recordings not included with the skill (they show a real face), so
these numbers can't be reproduced from this package. Treat them as a first check, not a benchmark.
- The rules were built from the syllable table only.
- The 12 sentences were the test: 61 words, and 1,849 video frames inside them.
- The scores are correlations with the real mouth. 1 means it follows the mouth perfectly, and 0 means no relation.

| method | closures caught | openness, per frame | openness, per word | rounding, per word |
|---|---|---|---|---|
| a general-purpose lip-sync tool, sound only | 7/9 | 0.26 | 0.34 | 0.58 |
| first guessed vowel rules | 3/9 | 0.11 | 0.35 | 0.54 |
| **this skill** | **8/9** | **0.35** | **0.47** | 0.55 |

**Rules tried and switched off**, because they lowered these scores even though they're clear in slow speech:
- aw after heavy letters.
- Rounding the consonant before a damma.

## Limits
- The rules come from one speaker.
- The tracker smooths very quick lip closures, so some closures in fast speech weren't measured.
- Checked by eye only: the top teeth on the lip for ف, the tongue for ث ذ ظ (it didn't clearly show), and the sh shape.
