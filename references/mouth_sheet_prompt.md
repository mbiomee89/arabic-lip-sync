# Making the character's 9 mouths (step 0)

Give the user this prompt to use in their image tool (Gemini, ChatGPT, Midjourney…) together with
ONE image of their character: front-facing, mouth visible, plain background, as large as possible.
The panel order is fixed: `scripts/mouth_pictures.py cut` expects it.

## The prompt (copy as is)

> Using the attached character image, create one square image: a 3×3 grid of 9 equal square
> panels showing the **same character, identical in every panel**: same pose, head size and
> position, framing, lighting, hair, clothes and plain background. **Only the mouth changes.**
> No borders, gaps, text or labels. At least 1536×1536 pixels.
>
> Left to right, top to bottom:
> 1. **rest**: lips together, relaxed, neutral
> 2. **closed**: lips pressed firmly together, as for "m" or "b"
> 3. **f**: lower lip tucked under the upper front teeth, as for "f"
> 4. **small**: mouth barely open, lips spread, teeth just showing, as for "ee"
> 5. **mid**: mouth half open, top teeth showing, as for "a" in "cat"
> 6. **wide**: mouth wide open, jaw dropped, as for "aah"
> 7. **round**: lips pushed forward into a small round "o", as for "oo"
> 8. **aw**: mouth open and rounded, as for "aw" or "oh"
> 9. **sh**: lips pushed out and slightly open, teeth together, as for "sh"

## Tips to give the user
- If a panel changes the face, hair, head size or position, regenerate (or ask the tool to fix
  only that panel). The cutter warns when a panel's face drifts too far.
- A tighter crop on the face gives sharper mouths. Animals work too (the test cat had no real `f`;
  teeth together was the closest, which is fine).
- Hair and fur will always differ a little between panels; that is why the cutter pastes only
  the mouth onto `rest`. Nothing to fix by hand.

## When the sheet comes back
```bash
python scripts/mouth_pictures.py cut sheet.png mouths/            # the order above
python scripts/mouth_pictures.py cut sheet.png mouths/ --order rest,closed,small,mid,wide,round,f,aw,sh   # another order
```
Show the user `mouths/contact_sheet.png` and wait for their OK before timing. If they don't like
one mouth, regenerate that panel and cut again.

## A folder that already exists
```bash
python scripts/mouth_pictures.py check mouths/          # shimmer score per picture
python scripts/mouth_pictures.py check mouths/ --fix    # writes mouths_fixed/, originals untouched
```
A score over 2.0 means hair/edges flicker as the mouth changes. Offer `--fix`; show the new
contact sheet; use `mouths_fixed/` only after the user's OK.

## How the paste works (tested 2026-11-23)
Each picture keeps only what really changes around the mouth (lips, teeth, a dropped jaw and its
chin line, and rest's own lips where the new mouth is smaller); everything else is `rest`. A plain
oval left ghost lip corners and a double chin line on a character whose jaw moves.
