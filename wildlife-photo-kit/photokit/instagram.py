"""Instagram-ready posts: for each post file in OUT/Posts, export the photos at Instagram's
size, all in one shape (a carousel uses the first slide's shape for every slide), plus the
caption and alt text as plain text files ready to paste.

A post file (OUT/Posts/2019-05-12.md) looks like this:

    photos: 20190512-014, 20190512-031
    aspect: 4:5
    location: Bandipur National Park
    alt-20190512-014: An Indian peafowl displaying its tail feathers in morning light.
    fit-20190512-031: border
    crop-20190512-014: 0.45,0.5
    ---
    Caption text exactly as it should appear on Instagram, hashtags at the end.

Settings above the `---` line; the caption below it.
  photos      ids in carousel order (cover first), up to 10
  aspect      4:5 (default), 1:1, 3:4 or a landscape shape up to 1.91:1
  location    suggestion for Instagram's location tag (not put in the caption)
  alt-<id>    alt text for that photo
  fit-<id>    crop (default) or border: border keeps the whole frame on a white background
  crop-<id>   centre of the crop as fractions of the edited photo (default 0.5,0.5)
  fit, border post-wide defaults: fit: crop|border, border: white|black
"""

import csv
import glob
import os
import re

import numpy as np
from PIL import Image

from . import common, edit

MAX_PHOTOS = 10
MAX_HASHTAGS = 5
MAX_CAPTION = 2200
PREVIEW_CHARS = 125
ASPECTS = {"4:5": 0.8, "3:4": 0.75, "1:1": 1.0, "1.91:1": 1.91, "16:9": 16 / 9, "3:2": 1.5, "5:4": 1.25}


def parse_post(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines()
    if "---" not in [l.strip() for l in lines]:
        return {"settings": {}, "body": text.strip(), "error": "no '---' line separating settings from caption"}
    cut = [l.strip() for l in lines].index("---")
    settings = {}
    for l in lines[:cut]:
        if ":" in l and l.strip():
            k, v = l.split(":", 1)
            settings[k.strip().lower()] = v.strip()
    return {"settings": settings, "body": "\n".join(lines[cut + 1:]).strip(), "error": None}


def post_photos(settings):
    return [x for x in re.split(r"[,\s]+", settings.get("photos", "")) if x]


def _ratio(aspect):
    a = (aspect or "4:5").strip()
    if a in ASPECTS:
        return ASPECTS[a]
    try:
        w, h = a.split(":")
        return float(w) / float(h)
    except Exception:
        raise ValueError(f"unknown aspect '{aspect}'")


def render(src_path, ratio, width, fit, centre, border_rgb):
    im = Image.open(src_path)
    icc = im.info.get("icc_profile")
    im = im.convert("RGB")
    W, H = im.size
    height = int(round(width / ratio))
    if fit == "border":
        pad = int(round(width * 0.04))
        box_w, box_h = width - 2 * pad, height - 2 * pad
        s = min(box_w / W, box_h / H)
        small = im.resize((max(1, int(round(W * s))), max(1, int(round(H * s)))), Image.LANCZOS)
        out = Image.new("RGB", (width, height), border_rgb)
        out.paste(small, ((width - small.width) // 2, (height - small.height) // 2))
        arr = np.asarray(out)
    else:
        x0, y0, x1, y1 = edit.crop_box(W, H, f"{ratio}:1", centre[0], centre[1], 1.0)
        im = im.crop((x0, y0, x1, y1)).resize((width, height), Image.LANCZOS)
        arr = np.asarray(im)
    # light sharpening for phone screens
    arr = edit.sharpen(common.to_float(arr), amount=0.35, radius=0.5)
    return Image.fromarray(common.to_uint8(arr)), icc


def _review_strip(work, name, dest, ratio, h=420):
    """All slides of one post side by side, for checking crops."""
    from PIL import ImageDraw

    slides = sorted(glob.glob(os.path.join(dest, "*.jpg")))
    if not slides:
        return
    w, pad = int(round(h * ratio)), 10
    strip = Image.new("RGB", (pad + len(slides) * (w + pad), h + 2 * pad + 26), (24, 24, 24))
    d = ImageDraw.Draw(strip)
    f = common.font(15, bold=True)
    for i, sl in enumerate(slides):
        x = pad + i * (w + pad)
        strip.paste(Image.open(sl).resize((w, h), Image.LANCZOS), (x, pad))
        d.text((x, h + pad + 4), os.path.basename(sl)[:-4], fill=(230, 230, 230), font=f)
    folder = os.path.join(work, "review", "instagram")
    os.makedirs(folder, exist_ok=True)
    strip.save(os.path.join(folder, f"{name}.jpg"), quality=85)


def run(work, out, width=1080):
    out = os.path.abspath(os.path.expanduser(out))
    log_path = os.path.join(out, "edit_log.csv")
    if not os.path.exists(log_path):
        raise SystemExit("No edit_log.csv yet. Run the edit step first.")
    with open(log_path, newline="") as f:
        edited = {r["id"]: r for r in csv.DictReader(f) if r.get("status") == "ok"}
    posts = sorted(glob.glob(os.path.join(out, "Posts", "*.md")))
    if not posts:
        raise SystemExit(f"No post files in {os.path.join(out, 'Posts')}.")
    total_warn = 0
    for path in posts:
        name = os.path.splitext(os.path.basename(path))[0]
        p = parse_post(path)
        warn = []
        if p["error"]:
            print(f"{name}: SKIPPED, {p['error']}")
            total_warn += 1
            continue
        st, body = p["settings"], p["body"]
        ids = post_photos(st)
        if not ids:
            print(f"{name}: SKIPPED, no 'photos:' line")
            total_warn += 1
            continue
        if len(ids) > MAX_PHOTOS:
            warn.append(f"{len(ids)} photos; Instagram allows {MAX_PHOTOS}, only the first {MAX_PHOTOS} exported")
            ids = ids[:MAX_PHOTOS]
        tags = re.findall(r"(?<![\w&])#\w+", body)
        if len(tags) > MAX_HASHTAGS:
            warn.append(f"{len(tags)} hashtags; Instagram allows {MAX_HASHTAGS}")
        if len(body) > MAX_CAPTION:
            warn.append(f"caption is {len(body)} characters; the limit is {MAX_CAPTION}")
        first = body.splitlines()[0] if body else ""
        if len(first) > PREVIEW_CHARS:
            warn.append(f"first line is {len(first)} characters; only about {PREVIEW_CHARS} show before 'more'")
        try:
            ratio = _ratio(st.get("aspect"))
        except ValueError as e:
            print(f"{name}: SKIPPED, {e}")
            total_warn += 1
            continue
        if not 0.75 <= ratio <= 1.91:
            warn.append("aspect outside Instagram's range (3:4 to 1.91:1); using 4:5")
            ratio = 0.8
        border_rgb = (0, 0, 0) if st.get("border", "white").lower() == "black" else (255, 255, 255)
        dest = os.path.join(out, "Instagram", name)
        os.makedirs(dest, exist_ok=True)
        for old in glob.glob(os.path.join(dest, "*.jpg")):
            os.remove(old)
        alts = []
        n = 0
        for i, pid in enumerate(ids, 1):
            row = edited.get(pid)
            if not row:
                warn.append(f"{pid} has no edited photo (not in picks, or the edit failed); left out")
                continue
            fit = st.get(f"fit-{pid.lower()}", st.get("fit", "crop")).lower()
            try:
                cx, cy = (float(v) for v in st.get(f"crop-{pid.lower()}", "0.5,0.5").split(","))
            except ValueError:
                cx, cy = 0.5, 0.5
            img, icc = render(os.path.join(out, row["edited"]), ratio, width, fit, (cx, cy), border_rgb)
            n += 1
            kw = {"quality": 92, "subsampling": 0}
            if icc:
                kw["icc_profile"] = icc
            img.save(os.path.join(dest, f"{n:02d}_{pid}.jpg"), **kw)
            alt = st.get(f"alt-{pid.lower()}", "")
            if not alt:
                warn.append(f"{pid} has no alt text")
            alts.append(f"Photo {n} ({pid}): {alt}")
        _review_strip(work, name, dest, ratio)
        with open(os.path.join(dest, "caption.txt"), "w", encoding="utf-8") as f:
            f.write(body + "\n")
        with open(os.path.join(dest, "alt-text.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(alts) + "\n")
            if st.get("location"):
                f.write(f"\nLocation tag: {st['location']}\n")
        total_warn += len(warn)
        size = f"{width}x{int(round(width / ratio))}"
        print(f"{name}: {n} photo{'s' if n != 1 else ''} at {size}, {len(tags)} hashtags, "
              f"{len(body)} characters" + ("".join(f"\n   ! {w}" for w in warn)))
    print(f"Check sheets: {os.path.join(work, 'review', 'instagram')}")
    print(f"\nInstagram posts are in {os.path.join(out, 'Instagram')}"
          + (f" ({total_warn} thing{'s' if total_warn != 1 else ''} to check, marked !)" if total_warn else ""))
