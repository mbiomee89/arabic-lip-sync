"""What changed between two mouth-timing versions (step 7, the review loop).

Usage: python compare.py old.json new.json [--min 0.05]
Prints every stretch of time where the mouth differs (old -> new), longer than --min seconds,
so each fix can be checked against what the user asked for.
"""
import json
import sys
from pathlib import Path


def cues(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))["mouthCues"]


def at(cs, t):
    for c in cs:
        if c["start"] <= t < c["end"]:
            return c["mouth"]
    return "-"


def main():
    old, new = cues(sys.argv[1]), cues(sys.argv[2])
    least = float(sys.argv[sys.argv.index("--min") + 1]) if "--min" in sys.argv else 0.05
    end = max(old[-1]["end"], new[-1]["end"])
    runs, cur, step = [], None, 0.01
    for i in range(int(end / step) + 1):
        t = i * step
        m = (at(old, t), at(new, t))
        if m[0] != m[1]:
            if cur and cur[2] == m and abs(cur[1] - t) < step * 1.5:
                cur[1] = t + step
            else:
                cur = [t, t + step, m]
                runs.append(cur)
        else:
            cur = None
    shown = [r for r in runs if r[1] - r[0] >= least]
    if not shown:
        print("no differences longer than", least, "s")
    for a, b, (m0, m1) in shown:
        print(f"{a:6.2f}-{b:6.2f}s  {m0:>6} -> {m1}")
    print(f"{len(shown)} changes")


if __name__ == "__main__":
    main()
