# Wildlife Photo Kit: instructions for Claude

You are helping a wildlife photographer with a library of about 5,000 photos (mostly JPEG,
from 2017 onward) on their Mac. The job:

1. Sort every photo by the date it was taken.
2. Find the wildlife photos and pick the best ones from each shooting day.
3. Edit the picks so they look professionally processed.
4. Write an Instagram post for each shooting day: photos at Instagram's size, a caption,
   hashtags and alt text.
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
- `aspect`: `orig` (default), `3:2`, `4:5`, `1:1`, `16:9` and so on. Choose the best
  composition for the full-size photo. The Instagram shape is handled separately in Step 7.
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

Look at `work/review/compare/<id>.jpg` (before and after side by side) and fix anything
that's off. Then write the Instagram posts for two of these photos' days as samples (format
in Step 7).

**ASK** the user, in one message:
- **The look.** Give the full paths of the 5 edited files in `OUT/Edited/...` so they can
  open them in Preview. Is the look right? Options: natural (the default), vivid, soft, bw;
  warmer or cooler; brighter or darker; more or less contrast.
- **The captions.** Paste the two sample captions. Is the voice right? Ask about the tone
  (storytelling, short and factual, or educational), emoji (the default is just 📷),
  language, whether to include a camera settings line, their Instagram handle or signature
  hashtag, and anything they never want in captions.

This is the last question. Apply the look with `--style` for everything, or per photo in
picks.csv. Save the caption preferences in `work/progress.md` so every post follows them.

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

## Step 7: Instagram posts

Write one post for each shooting day that has picks, as `OUT/Posts/YYYY-MM-DD.md`. For a
trip where several days have only one or two picks each, one post can cover the whole trip.
Name it after the first day, for example `2019-05-12-bandipur.md`. The format:

```
photos: 20190512-014, 20190512-031, 20190512-002
aspect: 4:5
location: Bandipur National Park
alt-20190512-014: An Indian peafowl displays its raised tail feathers in soft morning light.
alt-20190512-031: A spotted deer stag looks up from grazing at the edge of a forest clearing.
alt-20190512-002: A wide view of a dry riverbed with a herd of elephants crossing.
fit-20190512-002: border
crop-20190512-031: 0.4,0.5
---
The caption, exactly as it should appear on Instagram.
```

**Photos**
- Up to 10, strongest first. The first photo is the cover in the feed and on the profile
  grid. After that, mix close-ups, behaviour and the animal in its habitat.
- Every slide takes the cover's shape. Use `aspect: 4:5` (the default), which fills the
  most screen.
- If the 4:5 crop cuts off part of the animal (a tail, a wingtip, feet), move the centre with
  `crop-<id>: x,y` (fractions of the edited photo), or use `fit-<id>: border`. A border keeps
  the whole frame on white, which suits wide habitat shots. Add `border: black` for a black
  border instead.
- `location` is a suggestion for Instagram's location tag. Fill it in only from folder names
  or clear GPS; otherwise leave it out.

**The caption**
- **The first line is the hook.** Keep it under 125 characters, because only that much shows
  before "more". Say what's special about this moment, specifically. "Nature is beautiful"
  is not a hook.
- **Then 1–3 short paragraphs:** what the animal is doing, the light, a field note. Write in
  the first person, in the user's voice. State only what the photos and data show. The
  timestamps tell you how long the user was with an animal (first frame to last). One
  natural-history fact is fine if it's well established. Never invent numbers, behaviour you
  can't see, or details of where or how the photo was taken.
- **A species line:** the common name, plus the scientific name when you're sure, for
  example `Indian peafowl (Pavo cristatus)`. If you're unsure, leave the scientific name out.
- **A camera settings line,** if the user wants one, from the cover photo's data, for
  example `📷 Nikon D7500 · 300mm · f/5.6 · 1/1000s · ISO 400`.
- **Captive animals:** say so (for example "at the rescue centre"). Never present a captive
  animal as wild.
- **Hashtags: 5 at most** (Instagram's limit since December 2025), on their own line at the
  end. Use the species, the animal group, the place if known, and one or two photography tags
  such as #wildlifephotography. The user's own signature tag counts toward the 5. Skip spam
  tags like #like4like or #instagood.
- Aim for 300–900 characters in total. Instagram's limit is 2,200.
- **Alt text** for every photo: one plain sentence describing what's visible, for people who
  use screen readers.
- Follow the voice the user chose in Step 5.

An example:

```
photos: 20170312-001
aspect: 4:5
alt-20170312-001: A young bald eagle with mottled brown and white feathers stands side-on at the water's edge, looking right.
---
Still a few years away from that famous white head.

Bald eagles wear this mottled brown-and-white plumage for their first four to five years. This one stood side-on at the water's edge, which made for a clean full-body portrait.

Bald eagle (Haliaeetus leucocephalus), juvenile
📷 Nikon D7500 · 300mm · f/5.6 · 1/1000s · ISO 400

#baldeagle #birdsofprey #birdphotography #wildlifephotography #naturephotography
```

Then export the posts:

```
.venv/bin/python kit.py instagram --out "OUT"
```

This writes `OUT/Instagram/<post>/`, containing the numbered 1080×1350 photos, `caption.txt`
and `alt-text.txt`. It flags problems: too many hashtags or photos, a long first line,
missing alt text. Fix every flag. Then look at each `work/review/instagram/<post>.jpg`, fix
any crop that cuts off the animal, and run it again.

## Step 8: Gallery and wrap-up

```
.venv/bin/python kit.py report --out "OUT" --title "Wildlife picks"
```

Tell the user what was done: photos sorted, days covered, how many photos were picked and
edited, and how many posts are ready. Say where everything is: BYDATE, `OUT/Edited`,
`OUT/Social` and `OUT/Instagram`. Tell them to open `OUT/index.html` to browse it all with
the captions.

Also tell them how to post. AirDrop a post's folder from `OUT/Instagram` to their iPhone,
or post from instagram.com on the Mac. Add the photos in their numbered order and paste
`caption.txt`. Add each photo's alt text from `alt-text.txt` in the post's accessibility
settings, and the location tag if one is suggested there.
