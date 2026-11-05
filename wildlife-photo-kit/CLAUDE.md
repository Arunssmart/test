# Wildlife Photo Kit: instructions for Claude

You are helping a wildlife photographer with a library of about 5,000 photos (mostly JPEG,
from 2017 onward) on their Mac. The job:

1. Sort every photo by the date it was taken.
2. Find the wildlife photos and pick the best ones from each shooting day.
3. Edit the picks so they look professionally processed.
4. Draft social media posts per shooting day, if the user wants them.
5. Build a gallery page of the results.

The user asked for this to run on its own. Ask them things only at the two points marked
**ASK** below. Otherwise keep going and give short progress updates.

## Rules

- **Never change, move, rename or delete anything in the photo folder.** The kit only reads
  it. All output goes to `work/` (inside this folder) and to the output folder.
- Don't add or remove anything in a photo: no cloning things out, no fake background blur,
  no sky swaps. Cropping, straightening, tone and colour are fine. This keeps the photos
  acceptable for wildlife competitions.
- Name a species only when you're confident. Otherwise write "possibly <name>", use a broader
  group ("heron", "eagle", "deer"), and add `?` in picks.csv so the user can check.
- Don't make up places. Use only GPS from the catalog or the folder names.
- Pets and farm animals aren't wildlife. Zoo or captive animals can be picked, but write
  `captive` in the notes column.
- Run everything with `.venv/bin/python kit.py ...` from this folder. Put paths in quotes,
  since they often contain spaces.
- Keep `work/progress.md` up to date with the settings, the step you're on and the last sheet
  done, so the work can resume after a break or a context reset. Read it first when you start.

## Step 0: Set up

1. If `.venv` doesn't exist, run `bash setup.sh`. It installs what's needed and runs a self-test.
2. **ASK** in one message (skip anything the user already told you):
   - the photo folder (tip for them: in Finder, select the folder, hold Option, right-click,
     choose "Copy … as Pathname", then paste);
   - where results should go (suggest `~/Pictures/Wildlife Picks`);
   - where the By Date folders should go. Suggest a folder next to the photos **on the same
     drive**, such as `<photo folder> - By Date`. On the same drive the kit can clone or link
     the files, which takes no extra space.
3. Write these three paths at the top of `work/progress.md` (create `work/` if needed).

Below, SRC is the photo folder, OUT the results folder and BYDATE the By Date folder.

## Step 1: Scan

```
.venv/bin/python kit.py scan --src "SRC" --out "OUT"
```

This reads every photo once. For 5,000 photos expect 5–15 minutes; run it in the background
if you can. If it's interrupted, run it again and it picks up where it stopped. Then read
`work/summary.md` and tell the user the headline numbers (photos, years, shooting days, how
many had no camera date, any files it couldn't read). Don't ask anything here.

## Step 2: Sort by date

```
.venv/bin/python kit.py organize --dest "BYDATE"
```

This makes `BYDATE/<year>/<year-month-day>/`. Photos with no camera date go under
"No camera date (sorted by file date)", because those dates are often wrong. If the kit
reports there isn't enough room for copies, tell the user and carry on with the other steps.

## Step 3: First pass, finding wildlife candidates

```
.venv/bin/python kit.py sheets
```

This writes `work/sheets/sheet_001.jpg` and so on: 30 photos per sheet in date order, each
labelled with its id (`YYYYMMDD-NNN`). Bursts and near-identical shots are folded into their
sharpest frame, marked `xN`. Flags: `soft` (probably not sharp), `dark`, `bright`,
`no-date`.

Look at every sheet with the Read tool. For each photo, decide:
- not wildlife, or clearly weak (subject tiny, blurred, cut off, facing away, very poor
  light): skip it;
- worth a closer look: add a line to `work/candidates.csv` with the columns
  `id,date,subject,note`.

Expect to keep roughly 10–25%. Write `pass1: sheet N done` to progress.md after each sheet.
To review a date range only, use `--from YYYY-MM-DD --to YYYY-MM-DD`.

## Step 4: Second pass, choosing the finals and their crops

```
.venv/bin/python kit.py preview work/candidates.csv
```

This writes `work/previews/preview_NNN.jpg` with six photos per sheet. Each has yellow tick
marks in tenths along the edges, plus a 100% crop of its sharpest area (the cyan circle
shows where that is). If the sharpest area is grass instead of the animal, check the animal
yourself:

```
.venv/bin/python kit.py zoom ID --at 0.62,0.35
```

The point is a fraction of width and height, read off the tick marks. Aim at the eye. For a
burst (`best of N similar`), `kit.py group ID` shows every frame, in case another frame has a
better pose.

How to choose:
- For each shooting day, pick the best 1–5 photos (up to about 8 for a big day with many
  species). Pick none if nothing is good.
- Look for, in order: a sharp eye, behaviour or action, good light, a clean background, the
  animal not cut off at a joint, and some room in front of the animal's face.
- Aim for variety. Don't pick two near-identical frames.
- For the whole library, aim for roughly 3–8% of the photos (150–400 for 5,000).

Write the finals to `work/picks.csv`:

```
id,species,caption,aspect,cx,cy,zoom,rotate,ev,warmth,style,notes
20190512-014,Indian peafowl,Displaying in morning light,4:5,0.58,0.45,0.9,,,,,
20190512-031,Spotted deer?,,3:2,,,,1.5,,-1,,captive
```

Leave a column blank to use the automatic setting.
- `aspect`: `orig` (default), `3:2`, `4:5`, `1:1`, `16:9` and so on. Use `4:5` or `1:1` for
  photos likely to go on Instagram.
- `cx,cy`: centre of the crop, as fractions read off the ticks. Put the animal off-centre,
  roughly on a third, with room in the direction it faces.
- `zoom`: 1.0 is the largest crop of that shape; 0.7 is tighter. Keep at least about 6 MP
  unless the animal is tiny in the frame. The edit warns below 3 MP.
- `rotate`: degrees to level a horizon or waterline (positive turns counter-clockwise). Only
  use it if the tilt is visible.
- `ev` (-1 to +1) and `warmth` (-3 cooler to +3 warmer): only when the preview clearly needs
  it. The automatic white balance is deliberately cautious, so a strong colour cast needs
  `warmth`.
- `style`: blank (uses the run default), or `natural`, `vivid`, `soft`, `bw`.

## Step 5: Sample edits

Pick 5 finals with different light and subjects, then run:

```
.venv/bin/python kit.py edit --out "OUT" --only ID1,ID2,ID3,ID4,ID5 --compare
```

Look at `work/review/compare/<id>.jpg` (before and after side by side). Fix anything that's
off, then **ASK** the user. Give them the full paths of the 5 edited files in
`OUT/Edited/...` so they can open them in Preview, and ask:
- Is this look right? Options: natural (the default), vivid, soft, bw; warmer or cooler;
  brighter or darker; more or less contrast.
- Do they want post drafts, and for which platform?

This is the last question. Apply the answer with `--style` for everything, or per photo in
picks.csv.

## Step 6: Edit everything and check

```
.venv/bin/python kit.py edit --out "OUT" --style natural
```

Use the style the user chose. It takes about 10 seconds per photo and skips photos already
done, so it can be rerun safely. Then:

```
.venv/bin/python kit.py qa --out "OUT"
```

Look at every `work/review/qa/qa_NNN.jpg`. For a photo that looks wrong (too bright or dark,
a colour cast, a bad crop), change its row in picks.csv and redo just that photo:
`kit.py edit --out "OUT" --only ID --compare`. Then check its compare image.

Each photo gets two outputs:
- `OUT/Edited/<year>/<date>/<id>_<original name>.jpg`: full size, quality 95, original date
  and camera data kept;
- `OUT/Social/...`: a 2048 px copy, sharpened for screens.

## Step 7: Post drafts (only if wanted)

For each shooting day with picks, write `OUT/Posts/YYYY-MM-DD.md` containing:
- a caption of 2–4 sentences, first person, saying only what the photos and data show;
- the photo order (file names in `OUT/Social/...`, at most 10 for Instagram, strongest
  first);
- the species list;
- 10–20 relevant hashtags.

## Step 8: Gallery and wrap-up

```
.venv/bin/python kit.py report --out "OUT" --title "Wildlife picks"
```

Tell the user what was done: photos sorted, days covered, how many picked and edited, and
where everything is (BYDATE, `OUT/Edited`, `OUT/Social`, `OUT/Posts`). Tell them to open
`OUT/index.html` to browse.
