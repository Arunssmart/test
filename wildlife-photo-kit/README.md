# Wildlife Photo Kit

This kit sorts a photo library by date, finds the wildlife shots, picks the best ones from
each shooting day, and edits them. Claude runs it on your Mac. Your original photos are only
read, never changed or moved.

## What you get

- **By Date folders**: `2017/2017-03-12/...` for every photo. On the same drive these are
  clones or links, so they take no extra space.
- **Edited**: your best wildlife shots at full size, with exposure, white balance,
  highlights and shadows, contrast, colour, noise and sharpness adjusted, plus crops. The
  original date and camera data are kept.
- **Social**: 2048 px copies of the same edits, for sharing anywhere else (WhatsApp, Facebook,
  a website).
- **Instagram**: a post for each shooting day, ready to upload. You get the photos at
  1080 × 1350 in carousel order, `caption.txt` (with up to 5 hashtags, Instagram's limit) and
  `alt-text.txt`.
- **index.html**: a gallery of everything, by year and date, with each day's Instagram post.
  It opens in any browser.

## Set up on your Mac (about 5 minutes)

1. **Get the kit.** On GitHub, open the `arunssmart/test` repository and switch to the
   `claude/brave-ptolemy-r3bfym` branch. Click **Code → Download ZIP**, unzip it, and move
   the `wildlife-photo-kit` folder somewhere handy, such as Documents.
2. **Open it in Claude.** In the Claude desktop app, go to **Code** and choose the
   `wildlife-photo-kit` folder as the working folder. Claude reads this kit's instructions
   automatically.
3. **Start.** Type something like:
   > Set up the kit and run the full wildlife workflow. My photos are in /Volumes/MyDrive/Photos.

   To get the exact path, select the photos folder in Finder, hold **Option**, right-click,
   and choose **Copy "Photos" as Pathname**.
4. **Avoid constant approvals.** Switch the permission mode to auto, so Claude doesn't stop
   to ask before each command.

Claude checks in with you twice. At the start, it confirms the folders. Later, it shows 5
sample edits and 2 sample captions, so you can approve the editing style and the caption
voice: the tone, emoji, language, a camera settings line, and your handle or signature
hashtag.

## Posting

AirDrop a post's folder from `Instagram/` to your iPhone, or post from instagram.com on the
Mac. Add the photos in their numbered order, then paste `caption.txt`. Add the alt text from
`alt-text.txt` in the post's accessibility settings.

## How long it takes (5,000 photos)

| Step | Time |
|---|---|
| Scan (dates, sharpness, thumbnails) | 5–15 min |
| Claude reviews the photos | the longest part; it looks at every shot |
| Editing | about 10 seconds per picked photo |

## Limits

- The edits are automatic adjustments, like careful Lightroom settings tuned to each photo.
  They're not hand-painted local retouching.
- Photos that are out of focus or blurred by movement can't be rescued.
- Species names marked `?` need checking.
- Photos that went through WhatsApp or were screenshotted have often lost their camera date.
  Those are sorted by file date, in a separate folder.

## Running it yourself (optional)

```bash
bash setup.sh
.venv/bin/python kit.py scan --src "/path/to/photos"
.venv/bin/python kit.py organize --dest "/path/to/photos - By Date"
.venv/bin/python kit.py sheets          # contact sheets in work/sheets
# write work/picks.csv (see CLAUDE.md for the columns)
.venv/bin/python kit.py edit --out ~/Pictures/"Wildlife Picks" --compare
# write Posts/<date>.md files (see CLAUDE.md, Step 7)
.venv/bin/python kit.py instagram --out ~/Pictures/"Wildlife Picks"
.venv/bin/python kit.py report --out ~/Pictures/"Wildlife Picks"
```

`.venv/bin/python kit.py --help` lists every step.
