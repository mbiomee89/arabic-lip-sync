# Adding vowel marks for lip sync

The goal is the mouth, not grammar. Mark what the speaker actually says.

## What matters most
- **Every vowel that's said:** fatha َ, kasra ِ, damma ُ. These set mid, small and round.
- **Long vowels:**
  - ا / ى after a fatha gives wide.
  - ي after a kasra gives small.
  - و after a damma gives round.
  - Write the short vowel on the letter before, for example بُو and بِي. A long vowel written without one still works.
- **Sukun ْ** on a consonant with no vowel. It stops the script from inventing a vowel.
- **Shadda ّ** on doubled letters. The letter gets more time, and a doubled م closes the lips for longer.
- **Diphthongs:** write the sukun, as in بَيْت and يَوْم. aw is round, ay is spread.

## Pauses
- Put one phrase on each line, or end it with punctuation (، . ؟ !).
- At a pause the last short vowel isn't said, so the script drops it on its own. Writing it is harmless.

## Dialect
- **Write words as they are said,** not as in fusha.
  - Egyptian: اِلْمُعادَلات, بِيِتْكَلِّم, إِزّاي.
  - Jazan: امْيوم, امْسوق.
- **The Jazan article امْ** closes the lips. Write it with sukun on م, as in امْيوم, and keep it joined to the word.
- **Egyptian or Levantine "il-":** writing اِلْ with a kasra is fine.
- **English words** (skill, comment): write the vowel the mouth makes, not the spelling. English short i and e are more open than Arabic kasra, so write a fatha: سْكَل, كومَنْت. A kasra or ي would show a nearly shut mouth.
- **Egyptian and Levantine ق is said as a glottal stop ء:** write it as said (بُقّي → بُؤّي, دقايق → دَأايِء, دلوقتي → دِلْوَأْتي). A written ق is placed as a hard stop with a nearly shut mouth; ء takes the mouth of its vowel, which is what the lips really do.

## Songs (tested on an Egyptian song, 2026-11-23)
- **Write what is sung, not the written lyric.** ق sung as ء is ء (أَلْبي, not قلبي), and a
  contraction sung as one word is one word: مَبْيِعْرَفْشْ, never مَا بِيِعْرَفْشْ… (a separate مَا with a
  long ا shows a wide mouth that the singer never makes).
- **Short "ma" stays short:** مَ, not مَا, when the singer doesn't hold it.
- **Kasra and ي in songs:** mark them as usual. Singers open "e"/"ee" much more than speakers;
  `--sing` measures that from the voice and opens the mouth, so don't change the marks for it.
- **Check the low-score words first.** Wrong lyric words showed up exactly as aligner scores
  under 0.5 (the report's "check these words first"). Get the real lyrics from the user; Whisper
  on a song is unreliable even on separated vocals.

## Two spellings when a TTS voice reads the text
The voice may need a different spelling than the timing (see voice_options.md): keep the
**timing spelling** (as said, fully marked) in the script for lipsync.py, and send the TTS its own
**voice spelling** (e.g. split a hard word: ما بِيِعْرَفْش).

## Handled automatically
You don't need to do anything for these:
- The silent ل of ال before sun letters (الشَّمْس).
- Hamzat wasl in the middle of a sentence.
- The silent alef in ذَهَبوا and كوبًا.
- Tanween, which adds an n.

## When unsure
- **Not sure of a dialect vowel:** pick the one the speaker most likely used, then list the words you weren't sure about for the user to check.
- **A wrong word costs more than a wrong vowel.** It can make Whisper's word times slip for its neighbours.
