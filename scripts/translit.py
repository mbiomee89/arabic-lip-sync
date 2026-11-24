"""The skill's own sounds (rules.units) written in Latin letters, sound by sound, for the MMS aligner.

latin(units, dialect) -> one string per unit, in the same order, so every aligned letter goes back
to the exact Arabic letter or vowel it came from. "" means the sound has no letter of its own (it
then shares the time of the sound before it). Only letters the MMS tokenizer knows are used:
a i e n o u t s r m k l d g h y b p w c v j z f ' q x
"""

CONSONANT = {
    "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h", "خ": "kh", "د": "d", "ذ": "dh", "ر": "r",
    "ز": "z", "س": "s", "ش": "sh", "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "'", "غ": "gh",
    "ف": "f", "ق": "q", "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "w", "ي": "y",
    "ء": "'", "أ": "'", "إ": "'", "آ": "'", "ؤ": "'", "ئ": "'", "ة": "", "ا": "", "ى": "",
}
# Said differently in dialect (Egyptian): ج is g, ث ذ ظ are t d z. (ق said as ء is written ء in the script.)
DIALECT = {"egy": {"ج": "g", "ث": "t", "ذ": "d", "ظ": "z"}}
VOWEL = {("mid", 1): "a", ("wide", 1): "a", ("aw", 1): "a", ("small", 1): "i", ("round", 1): "u",
         ("mid", 2): "aa", ("wide", 2): "aa", ("aw", 2): "aa", ("small", 2): "ii", ("round", 2): "uu"}


def latin(units, dialect=None):
    table = dict(CONSONANT, **DIALECT.get(dialect, {}))
    out = []
    for kind, mouth, weight, ch in units:
        if kind == "pause":
            out.append("")
        elif kind == "vowel":
            out.append(VOWEL.get((mouth, 2 if weight >= 2 else 1), "a"))
        else:
            out.append(table.get(ch, ""))
    return out
