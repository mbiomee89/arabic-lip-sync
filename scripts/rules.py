"""Arabic mouth rules, measured from a real speaker's video (see references/mouth_shapes.md).

Turns one vowel-marked word into timed units: (kind, mouth, weight, letter).
kind is "consonant" or "vowel"; mouth is a mouth name or None (the aligner then uses "small").

Mouth names:
  rest    silence
  closed  ب م: lips pressed together
  f       ف: lower lip pulled in
  small   kasra, long ي and most consonants: nearly shut, lips spread
  mid     fatha: lips apart, top teeth showing
  wide    long ا / ى, and fatha on ع ء: widest opening
  round   damma, long و, consonant و: lips pushed out, mouth narrower
  aw      (off by default) fatha or long ا after heavy letters: open and rounded
  sh      ش: lips pushed out and open
"""
import re

HEAVY = set("صضطظقخر")
THROAT_OPEN = set("عءأإآ")         # measured: fatha on these opens as wide as a long ا
SUN = set("تثدذرزسشصضطظلن")
FATHA, KASRA, DAMMA, SUKUN, SHADDA = "َ", "ِ", "ُ", "ْ", "ّ"
TANWEEN = {"ً": FATHA, "ٍ": KASRA, "ٌ": DAMMA}
MARKS = {FATHA, KASRA, DAMMA, SUKUN, SHADDA, *TANWEEN, "ٰ"}

# Measured in slow syllables, but they made normal speech follow the real mouth less well:
HEAVY_ROUND = False          # "aw" after heavy letters instead of mid/wide
ROUND_BEFORE_DAMMA = False   # the consonant before a damma already round
USE_SH = False               # ش as "sh"; most characters have no such mouth

WEIGHT = {"consonant": 1.0, "short": 1.0, "long": 2.0}   # measured: long syllables ~1.5x short ones
# Shadda: the letter is given as two units, so the aligner gives it about twice the time.


def letters(word):
    """Base letters with their marks: [[letter, set(marks)], ...], punctuation removed."""
    out = []
    for ch in re.sub(r"[ـ،؛؟.,:!?\"'«»()\-]", "", word):
        if ch in MARKS and out:
            out[-1][1].add(ch)
        elif ch not in MARKS:
            out.append([ch, set()])
    return out


def has_marks(word):
    return any(ch in MARKS for ch in word)


def vowel_of(marks):
    for m in (FATHA, KASRA, DAMMA):
        if m in marks:
            return m
    for t, m in TANWEEN.items():
        if t in marks:
            return m
    return None


def units(word, first_in_phrase, last_in_phrase):
    ls = letters(word)
    silent = set()
    # Article ال, alone or after a one-letter prefix (وَال، بِال، فَال، كَال).
    start = 1 if len(ls) > 3 and ls[0][1] and ls[1][0] == "ا" and ls[2][0] == "ل" else 0
    if len(ls) > start + 2 and ls[start][0] == "ا" and ls[start + 1][0] == "ل" and not ls[start][1]:
        if start or not first_in_phrase:
            silent.add(start)                      # hamzat wasl
        if ls[start + 2][0] in SUN:
            silent.add(start + 1)                  # ل joins the sun letter
    # Alef after a final waw (ذَهَبوا) and after fathatan (كوبًا) is not a long ا.
    if len(ls) > 1 and ls[-1][0] == "ا" and (ls[-2][0] == "و" or "ً" in ls[-2][1]):
        silent.add(len(ls) - 1)
    # At a pause the last short vowel and tanween are dropped.
    if last_in_phrase and ls:
        ls[-1][1] -= {FATHA, KASRA, DAMMA, *TANWEEN}

    out = []
    for k, (ch, marks) in enumerate(ls):
        if k in silent:
            continue
        prev = ls[k - 1] if k else None
        nxt = ls[k + 1] if k + 1 < len(ls) else None
        prev_vowel = vowel_of(prev[1]) if prev else None
        if ch in "اىآ" and k > 0:
            heavy = HEAVY_ROUND and prev[0] in HEAVY
            out.append(("vowel", "aw" if heavy else "wide", WEIGHT["long"], ch))
            continue
        if ch == "ي" and prev_vowel == KASRA and not marks - {SHADDA}:
            out.append(("vowel", "small", WEIGHT["long"], ch))
            continue
        if ch == "و" and prev_vowel == DAMMA and not marks - {SHADDA}:
            out.append(("vowel", "round", WEIGHT["long"], ch))
            continue
        if ch in "وي" and prev_vowel == FATHA and SUKUN in marks:      # diphthongs aw / ay
            out.append(("vowel", "round" if ch == "و" else "small", WEIGHT["long"], ch))
            continue
        if ch in "يو" and not marks and prev and prev_vowel is None:    # long vowel written without marks
            out.append(("vowel", "small" if ch == "ي" else "round", WEIGHT["long"], ch))
            continue

        vowel = vowel_of(marks)
        next_round = vowel == DAMMA or (nxt is not None and nxt[0] == "و" and vowel is None and not nxt[1])
        if ch in "بم":
            mouth = "closed"
        elif ch == "ف":
            mouth = "f"
        elif ch == "و":
            mouth = "round"
        elif ch == "ش" and USE_SH:
            mouth = "sh"
        elif ROUND_BEFORE_DAMMA and next_round:
            mouth = "round"
        else:
            mouth = None
        out.append(("consonant", mouth, WEIGHT["consonant"], ch))
        if SHADDA in marks:   # a doubled letter is said twice as long: two units in a row, one held sound
            out.append(("consonant", mouth, WEIGHT["consonant"], ch))
        if vowel == FATHA:
            v = "aw" if HEAVY_ROUND and ch in HEAVY else "wide" if ch in THROAT_OPEN else "mid"
        elif vowel == KASRA:
            v = "small"
        elif vowel == DAMMA:
            v = "round"
        else:
            v = None
        if v:
            out.append(("vowel", v, WEIGHT["short"], ch))
        if any(t in marks for t in TANWEEN):
            out.append(("consonant", None, WEIGHT["consonant"], "ن"))
    return out
