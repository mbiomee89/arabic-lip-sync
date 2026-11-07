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
- **Egyptian or Levantine "il-":** writing اِلْ with a kasra is fine.
- **English words** (skill, comment): write the vowel the mouth makes, not the spelling. English short i and e are more open than Arabic kasra, so write a fatha: سْكَل, كومَنْت. A kasra or ي would show a nearly shut mouth.
- **Egyptian and Levantine ق is said as a glottal stop ء:** write it as said (بُقّي → بُؤّي, دقايق → دَأايِء, دلوقتي → دِلْوَأْتي). A written ق is placed as a hard stop with a nearly shut mouth; ء takes the mouth of its vowel, which is what the lips really do.

## Handled automatically
You don't need to do anything for these:
- The silent ل of ال before sun letters (الشَّمْس).
- Hamzat wasl in the middle of a sentence.
- The silent alef in ذَهَبوا and كوبًا.
- Tanween, which adds an n.

## When unsure
- **Not sure of a dialect vowel:** pick the one the speaker most likely used, then list the words you weren't sure about for the user to check.
- **A wrong word costs more than a wrong vowel.** It can make Whisper's word times slip for its neighbours.
