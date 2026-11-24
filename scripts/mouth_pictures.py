"""The character's 9 mouth pictures: cut a 3x3 sheet, check a folder for shimmer, fix it.

  python mouth_pictures.py cut <sheet.png> <out folder> [--order rest,closed,f,small,mid,wide,round,aw,sh] [--raw]
  python mouth_pictures.py check <folder> [--fix]

cut:   splits the sheet into 9 equal panels named by --order (default: the order of
       references/mouth_sheet_prompt.md), lines each panel up with "rest", then pastes ONLY the
       mouth area onto "rest", so nothing but the mouth changes between pictures (no shimmering hair
       or fur). --raw keeps whole panels. Writes contact_sheet.png to check by eye, and warns when a
       panel's face differs too much from "rest" (the image tool changed more than the mouth).
check: measures how much each picture differs from "rest" outside the mouth. Above SHIMMER the
       character's hair/edges will flicker as the mouth changes. --fix writes <folder>_fixed with
       the mouth-only pictures; the originals are never touched.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ORDER = ["rest", "closed", "f", "small", "mid", "wide", "round", "aw", "sh"]
MAX_SHIFT = 12       # pixels a panel may be off from "rest" (searched both ways)
DRIFT = 18.0         # mean grey difference above the mouth over this: the face itself changed
SHIMMER = 2.0        # mean grey difference outside the mouth over this: visible flicker
PAD = 0.30           # mouth area padding, share of its size (covers wide lip corners)
FEATHER = 0.04       # soft mask edge, share of the picture width


def grey(im):
    return np.asarray(im.convert("L"), dtype=float)


def best_shift(panel, rest):
    """(dx, dy, error): the shift that best lines the panel's upper half up with rest's."""
    a, r = grey(panel), grey(rest)
    h = a.shape[0] // 2
    m = MAX_SHIFT
    best = None
    for dy in range(-m, m + 1, 2):
        for dx in range(-m, m + 1, 2):
            e = np.abs(np.roll(np.roll(a, dy, 0), dx, 1)[m:h, m:-m] - r[m:h, m:-m]).mean()
            if best is None or e < best[2]:
                best = (dx, dy, e)
    dx0, dy0, _ = best
    for dy in range(dy0 - 1, dy0 + 2):
        for dx in range(dx0 - 1, dx0 + 2):
            e = np.abs(np.roll(np.roll(a, dy, 0), dx, 1)[m:h, m:-m] - r[m:h, m:-m]).mean()
            if e < best[2]:
                best = (dx, dy, e)
    return best


def mouth_box(pictures, rest):
    """Where the mouth is: the area that changes most between the pictures, in the lower middle."""
    r = grey(rest)
    H, W = r.shape
    diff = np.mean([np.abs(grey(p) - r) for p in pictures], axis=0)
    blur = np.asarray(Image.fromarray(np.clip(diff, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(W / 60)), dtype=float)
    y0, y1, x0, x1 = int(0.35 * H), int(0.97 * H), int(0.15 * W), int(0.85 * W)
    zone = blur[y0:y1, x0:x1]
    cy, cx = np.unravel_index(np.argmax(zone), zone.shape)
    cy, cx = cy + y0, cx + x0
    hy, hx = int(0.15 * H), int(0.20 * W)
    wy0, wy1, wx0, wx1 = max(0, cy - hy), min(H, cy + hy), max(0, cx - hx), min(W, cx + hx)
    win = blur[wy0:wy1, wx0:wx1]
    ys, xs = np.where(win > 0.5 * win.max())
    bx0, bx1, by0, by1 = xs.min() + wx0, xs.max() + wx0, ys.min() + wy0, ys.max() + wy0
    px, py = PAD * (bx1 - bx0), PAD * (by1 - by0)
    return (max(0, bx0 - px), max(0, by0 - py), min(W, bx1 + px), min(H, by1 + py))


def mask_for(size, box):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).ellipse(box, fill=255)
    return m.filter(ImageFilter.GaussianBlur(size[0] * FEATHER))


def outside_diff(pic, rest, box):
    """Difference away from the mouth (the box grown by half, so the soft paste edge is not counted)."""
    x0, y0, x1, y1 = box
    gx, gy = (x1 - x0) * 0.5, (y1 - y0) * 0.5
    inside = np.asarray(mask_for(rest.size, (x0 - gx, y0 - gy, x1 + gx, y1 + gy)), dtype=float) / 255
    d = np.abs(grey(pic) - grey(rest)) * (1 - inside)
    return float(d.sum() / max(1.0, (1 - inside).sum()))


def contact_sheet(pictures, names, out):
    w, h = pictures[0].size
    s = Image.new("RGB", (w * 3, (h + 28) * 3), "white")
    d = ImageDraw.Draw(s)
    for i, (p, n) in enumerate(zip(pictures, names)):
        x, y = (i % 3) * w, (i // 3) * (h + 28)
        d.text((x + 8, y + 6), n, fill="black")
        s.paste(p.convert("RGB"), (x, y + 28))
    s.save(out)


CHANGE = 14.0        # grey difference (after a light blur) that counts as a real change, not shimmer


def change_mask(pic, rest, box):
    """Exactly what this picture changes around the mouth: lips, teeth, a dropped jaw and chin
    line, and rest's own lips where the new mouth is smaller. Kept to the lower face (the mouth
    box grown sideways and down), so hair and edges always come from rest."""
    W, H = rest.size
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    zone = Image.new("L", rest.size, 0)
    ImageDraw.Draw(zone).ellipse((x0 - 0.6 * bw, y0 - 0.3 * bh, x1 + 0.6 * bw, y1 + 1.0 * bh), fill=255)
    zone = zone.filter(ImageFilter.GaussianBlur(W / 80))
    d = np.abs(grey(pic) - grey(rest))
    d = np.asarray(Image.fromarray(np.clip(d, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(W / 200)), dtype=float)
    m = Image.fromarray(((d > CHANGE) * 255).astype(np.uint8))
    grow = max(3, int(W / 50) | 1)
    m = m.filter(ImageFilter.MaxFilter(grow)).filter(ImageFilter.GaussianBlur(W / 120))
    return ImageChops.multiply(m, zone)


def mouth_only(pictures, names, rest):
    box = mouth_box([p for p, n in zip(pictures, names) if n != "rest"], rest)
    out = []
    for p, n in zip(pictures, names):
        out.append(rest if n == "rest" else Image.composite(p.convert(rest.mode), rest, change_mask(p, rest, box)))
    return out, box


def cut(sheet, out, order=ORDER, raw=False):
    im = Image.open(sheet).convert("RGB")
    W, H = im.size
    cw, ch = W // 3, H // 3
    panels = [im.crop(((i % 3) * cw, (i // 3) * ch, (i % 3 + 1) * cw, (i // 3 + 1) * ch)) for i in range(9)]
    rest = panels[order.index("rest")]
    warnings, aligned = [], []
    for p, n in zip(panels, order):
        if n == "rest":
            aligned.append(p)
            continue
        dx, dy, err = best_shift(p, rest)
        aligned.append(ImageChops.offset(p, dx, dy))
        if err > DRIFT:
            warnings.append(f"{n}: the face differs a lot from rest (difference {err:.0f}); "
                            "consider regenerating this panel or the sheet")
    final, box = (aligned, None) if raw else mouth_only(aligned, order, rest)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for p, n in zip(final, order):
        p.save(out / f"{n}.png")
    contact_sheet(final, order, out / "contact_sheet.png")
    print(f"9 mouths -> {out} ({cw}x{ch} each)" + ("" if raw else f"; mouth area {tuple(int(v) for v in box)}"))
    print(f"check them: {out / 'contact_sheet.png'}")
    for w in warnings:
        print("WARNING:", w)
    if min(cw, ch) < 400:
        print(f"note: {cw}x{ch} is small for a final video; a larger sheet gives sharper mouths")


def load_folder(folder):
    folder = Path(folder)
    names, pics = [], []
    for n in ORDER:
        for ext in (".png", ".jpg", ".jpeg"):
            p = folder / f"{n}{ext}"
            if p.exists():
                names.append(n)
                pics.append(Image.open(p).convert("RGB"))
                break
    if "rest" not in names:
        sys.exit(f"no rest picture in {folder}")
    return names, pics


def check(folder, fix=False):
    names, pics = load_folder(folder)
    rest = pics[names.index("rest")]
    others = [p for p, n in zip(pics, names) if n != "rest"]
    if not others:
        sys.exit("only a rest picture: nothing to compare")
    box = mouth_box(others, rest)
    scores = {n: round(outside_diff(p, rest, box), 2) for p, n in zip(pics, names) if n != "rest"}
    worst = max(scores.values())
    missing = [n for n in ORDER if n not in names]
    print("difference from rest outside the mouth:", scores)
    if missing:
        print("missing mouths (stand-ins will be used):", ", ".join(missing))
    if worst > SHIMMER:
        print(f"SHIMMER: up to {worst:.1f} (limit {SHIMMER}). Hair/edges will flicker as the mouth changes. "
              "Fix: paste only the mouths onto rest (check --fix; originals are kept).")
    else:
        print("clean: only the mouth changes between pictures")
    if fix:
        fixed, _ = mouth_only(pics, names, rest)
        out = Path(str(Path(folder)).rstrip("/\\") + "_fixed")
        out.mkdir(exist_ok=True)
        for p, n in zip(fixed, names):
            p.save(out / f"{n}.png")
        contact_sheet(fixed, names, out / "contact_sheet.png")
        print(f"mouth-only pictures -> {out} (originals unchanged); check {out / 'contact_sheet.png'}")
    return worst


def main():
    a = sys.argv[1:]
    if not a or a[0] not in ("cut", "check"):
        sys.exit(__doc__)
    if a[0] == "cut":
        order = a[a.index("--order") + 1].split(",") if "--order" in a else ORDER
        if sorted(order) != sorted(ORDER):
            sys.exit("--order must name all 9 mouths once: " + ",".join(ORDER))
        cut(a[1], a[2], order, "--raw" in a)
    else:
        check(a[1], "--fix" in a)


if __name__ == "__main__":
    main()
