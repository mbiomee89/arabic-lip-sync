"""Rule and cleanup tests that need no audio and no Whisper.

Run: python tests/test_rules.py   (prints "all N tests passed" or stops at the first failure)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import align  # noqa: E402
import rules  # noqa: E402


def shapes(word, first=False, last=False):
    return [(u[0], u[1], u[3]) for u in rules.units(word, first, last)]


def test_closures_on_b_and_m():
    s = shapes("بَاب")
    assert s[0] == ("consonant", "closed", "ب") and s[-1][1] == "closed"


def test_shadda_is_two_units():
    s = shapes("عَمّ")
    assert [x for x in s if x[2] == "م"] == [("consonant", "closed", "م")] * 2


def test_sun_letter_lam_is_silent():
    assert "ل" not in [x[2] for x in shapes("الشَّمْس")]


def test_moon_letter_lam_is_said():
    assert "ل" in [x[2] for x in shapes("الْقَمَر")]


def test_long_vowels():
    assert ("vowel", "wide", "ا") in shapes("باب")[0:3] or any(x[1] == "wide" for x in shapes("بَاب"))
    assert any(x == ("vowel", "round", "و") for x in shapes("بُو"))
    assert any(x == ("vowel", "small", "ي") for x in shapes("بِي"))


def test_damma_rounds_and_kasra_spreads():
    assert ("vowel", "round", "ب") in shapes("بُ")
    assert ("vowel", "small", "ب") in shapes("بِ")


def test_tanween_adds_n():
    assert shapes("كِتابٌ")[-1][2] == "ن"


def test_f_mouth():
    assert shapes("فَ")[0][1] == "f"


def test_throat_letter_takes_vowel_after_doubling():
    units = rules.units("عَّ", False, False)
    assert align.next_vowel(units, 0)[1] in ("wide", "mid")


def test_tidy_joins_split_sound_before_dropping_short_parts():
    cues = [{"start": 0.0, "end": 0.2, "mouth": "round"},
            {"start": 0.2, "end": 0.25, "mouth": "small"}, {"start": 0.25, "end": 0.3, "mouth": "small"},
            {"start": 0.3, "end": 0.5, "mouth": "mid"}]
    out = align.tidy(cues, 0.5)
    assert any(c["mouth"] == "small" and abs(c["end"] - c["start"] - 0.1) < 1e-6 for c in out), out


def test_tidy_keeps_short_closures():
    cues = [{"start": 0.0, "end": 0.2, "mouth": "mid"}, {"start": 0.2, "end": 0.22, "mouth": "closed"},
            {"start": 0.22, "end": 0.5, "mouth": "mid"}]
    out = align.tidy(cues, 0.5)
    c = [x for x in out if x["mouth"] == "closed"][0]
    assert c["end"] - c["start"] >= align.MIN_CUE - 1e-6


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
    print(f"all {len(tests)} tests passed")
