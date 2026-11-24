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


def test_tidy_keeps_every_short_shape_alike():
    # Same rule for every mouth: a short one between long neighbours is kept at MIN_CUE, never dropped.
    for m in ("closed", "f", "round", "small", "wide", "sh"):
        cues = [{"start": 0.0, "end": 0.2, "mouth": "mid"}, {"start": 0.2, "end": 0.22, "mouth": m},
                {"start": 0.22, "end": 0.5, "mouth": "mid"}]
        out = align.tidy(cues, 0.5)
        c = [x for x in out if x["mouth"] == m]
        assert c and c[0]["end"] - c[0]["start"] >= align.MIN_CUE - 1e-3, (m, out)


def test_tidy_borrows_without_drift():
    # A short shape takes time from its neighbours: the cues after them keep their times.
    cues = [{"start": 0.0, "end": 0.2, "mouth": "mid"}, {"start": 0.2, "end": 0.21, "mouth": "small"},
            {"start": 0.21, "end": 0.4, "mouth": "wide"}, {"start": 0.4, "end": 0.6, "mouth": "round"}]
    out = align.tidy(cues, 0.6)
    assert [c for c in out if c["mouth"] == "round"][0]["start"] == 0.4, out
    assert all(c["end"] - c["start"] >= align.MIN_CUE - 1e-3 for c in out), out


def test_tidy_merges_by_look_when_no_room():
    # No room to borrow: the short shape joins the neighbour that looks most like it, whatever it is.
    cues = [{"start": 0.0, "end": 0.04, "mouth": "wide"}, {"start": 0.04, "end": 0.06, "mouth": "mid"},
            {"start": 0.06, "end": 0.1, "mouth": "round"}]
    out = align.tidy(cues, 0.1)
    assert all(c["end"] > c["start"] for c in out) and abs(out[-1]["end"] - 0.1) < 1e-6, out
    assert not any(c["mouth"] == "mid" and c["start"] >= 0.06 for c in out), out   # mid went to wide, not round


def test_open_vowel_carries_into_sukun():
    units = rules.units("أَحْ", False, True)
    s = align.mouth_shapes(units)
    assert s[-1] == s[-2] == ("wide" if units[-2][1] == "wide" else "mid"), s   # حْ keeps the fatha's mouth


def test_sukun_after_kasra_stays_small():
    s = align.mouth_shapes(rules.units("إِلْ", False, True))
    assert s[-1] == "small", s


def test_track_every_sound_reaches_its_shape():
    # Every sound, whatever the letter, holds its own full shape in the middle of its time.
    units = rules.units("مَبْروكٌ", True, False) + rules.units("شُفْتَ", False, True)
    shapes_ = align.mouth_shapes(units)
    placed, t = [], 0.1
    for k, u in enumerate(units):
        placed.append((t, t + 0.08, shapes_[k], u, align.next_vowel(units, k)))
        t += 0.08
    tr = align.track(placed, t + 0.1)
    for a, b, shape, u, after in placed:
        mid = int(round(((a + b) / 2 - align.TRACK_LEAD) * tr["rate"]))
        want = align.target(shape, u, after)
        got = (tr["open"][mid], tr["width"][mid], tr["round"][mid])
        assert all(abs(x - y) < 2e-3 for x, y in zip(got, want)), (shape, u[3], got, want)
    assert len(tr["open"]) == len(tr["width"]) == len(tr["round"])


def test_report_counts_every_mouth():
    import lipsync  # noqa: E402
    assert lipsync.expected_mouths("بُصّ", True, True) == ["closed", "round", "small"]


def test_track_is_smooth():
    units = rules.units("وَاضِح", True, True)
    placed, t = [], 0.1
    for k, u in enumerate(units):
        placed.append((t, t + 0.1, align.mouth_shapes(units)[k], u, align.next_vowel(units, k)))
        t += 0.1
    tr = align.track(placed, t + 0.1)
    steps = [abs(b - a) for a, b in zip(tr["open"], tr["open"][1:])]
    # No single 10 ms jump bigger than about a third of the full range (each sound now reaches its
    # full shape, so changes are a little quicker than with the old blur).
    assert max(steps) < 0.03, max(steps)


def test_mms_letters_map_back_to_every_sound():
    import translit  # noqa: E402
    known = set("aienoutsrmkldghybpwcvjzf'qx")   # the MMS_FA tokenizer's letters
    for word in ("بُصّ", "شَفايْفي", "دَأايِء", "وِتُمُنْمِيَّة", "جَرَّبْها", "السْكَل…"):
        units = rules.units(word, True, True)
        lat = translit.latin(units, "egy")
        assert len(lat) == len(units), word            # one entry per sound, in order
        assert all(set(x) <= known for x in lat), (word, lat)
    assert translit.latin(rules.units("بُصّ", True, True)) == ["b", "u", "s", "s"]   # shadda: twice
    assert translit.latin(rules.units("عَلَى", True, True)) == ["'", "a", "l", "a", "aa"]


def test_ellipsis_is_not_a_letter():
    assert [u[3] for u in rules.units("السْكَل…", True, True)] == [u[3] for u in rules.units("السْكَل", True, True)]


def test_marked_alef_before_mim_is_said():
    # only a bare alef is the Jazan article امْ; اِمْبارِح starts with its kasra
    assert [u[1] for u in rules.units("امْيوم", True, False)][0] == "closed"
    assert [u for u in rules.units("اِمْبارِح", True, False) if u[0] == "vowel"][0][1] == "small"
    assert rules.units("اِمْبارِح", True, False)[0][3] == "ا"


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
    print(f"all {len(tests)} tests passed")
