"""A quick preview video: the character's mouth pictures shown in time with the voice.

Usage: python render_preview.py <mouths.json> <audio or video> <pictures folder> <out.mp4> [--fps 30] [--slow] [--strict]

The pictures folder holds one image per mouth, all the same size, named by mouth:
rest, closed, f, small, mid, wide, round, aw, sh (.png or .jpg). A missing mouth uses the nearest
one the character has (FALLBACK), so a character with only rest/closed/small/wide/round still works.
Every stand-in is listed before anything renders; --strict stops instead, so a missing mouth is
never hidden in a final video. --slow also writes a half-speed copy, which makes closures easy to
check by eye.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

FALLBACK = {
    "f": ["small", "closed"], "aw": ["round", "mid", "wide"], "sh": ["small", "round"], "mid": ["wide", "small"],
    "wide": ["mid", "small"], "round": ["small"], "small": ["rest", "mid"], "closed": ["rest", "small"], "rest": ["small", "closed"],
}


def picture_for(mouth, folder, seen=()):
    for ext in (".png", ".jpg", ".jpeg"):
        p = folder / f"{mouth}{ext}"
        if p.exists():
            return p
    for other in FALLBACK.get(mouth, []):
        if other not in seen:
            found = picture_for(other, folder, seen + (mouth,))
            if found:
                return found
    return None


def check_inputs(cues, folder):
    """Stop early, with a clear reason, on anything that would make a wrong or broken preview."""
    if not cues:
        sys.exit("no mouth cues in the file")
    for k, c in enumerate(cues):
        if not {"start", "end", "mouth"} <= set(c):
            sys.exit(f"cue {k} is missing start, end or mouth: {c}")
        if c["end"] <= c["start"]:
            sys.exit(f"cue {k} ends before it starts: {c}")
        if k and c["start"] < cues[k - 1]["start"]:
            sys.exit(f"cues are out of order at cue {k}")
    if not folder.is_dir():
        sys.exit(f"no pictures folder: {folder}")


def picture_size(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return out.stdout.strip() or None


def main():
    cues_path, audio, folder, out = sys.argv[1:5]
    fps = int(sys.argv[sys.argv.index("--fps") + 1]) if "--fps" in sys.argv else 30
    strict = "--strict" in sys.argv
    folder = Path(folder)
    cues = json.loads(Path(cues_path).read_text(encoding="utf-8")).get("mouthCues", [])
    check_inputs(cues, folder)

    # Which picture each mouth will use, decided and reported before rendering.
    pictures, missing = {}, []
    for mouth in sorted({c["mouth"] for c in cues}):
        pic = picture_for(mouth, folder)
        if pic is None:
            sys.exit(f"no picture for '{mouth}' or any stand-in in {folder}")
        pictures[mouth] = pic
        if pic.stem != mouth:
            missing.append(f"{mouth} -> {pic.stem}")
    if missing:
        print("STAND-INS (these mouths have no picture of their own):", ", ".join(missing))
        if strict:
            sys.exit("--strict: add the missing pictures, or run without --strict for a draft preview")
    sizes = {picture_size(p) for p in pictures.values()}
    if len(sizes) > 1:
        sys.exit(f"the mouth pictures differ in size ({', '.join(str(s) for s in sizes)}); make them all the same size")

    with tempfile.TemporaryDirectory() as tmp:
        lst = Path(tmp) / "list.txt"
        lines, frame = [], 0
        for c in cues:
            end_frame = round(c["end"] * fps)
            n = end_frame - frame
            if n <= 0:
                continue
            lines += [f"file '{pictures[c['mouth']].resolve().as_posix()}'", f"duration {n / fps:.6f}"]
            frame = end_frame
        if not lines:
            sys.exit("the cues are all shorter than one frame")
        lines.append(lines[-2])   # the concat format needs the last picture listed twice
        lst.write_text("\n".join(lines), encoding="utf-8")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(audio),
                        "-map", "0:v", "-map", "1:a", "-r", str(fps), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:a", "aac", "-shortest", str(out)], check=True)
        if "--slow" in sys.argv:
            slow = Path(out).with_name(Path(out).stem + "_slow.mp4")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(out), "-filter:v", "setpts=2*PTS", "-filter:a", "atempo=0.5",
                            "-r", str(fps), str(slow)], check=True)
    print(f"wrote {out}" + (f" (draft: stand-ins used for {', '.join(missing)})" if missing else ""))


if __name__ == "__main__":
    main()
