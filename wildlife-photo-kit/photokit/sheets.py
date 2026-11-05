"""Review images for Claude (and you): contact sheets, close-up previews and
after-edit check sheets."""

import csv
import glob
import os

from PIL import Image, ImageDraw

from . import common
from .scan import GRID

BG = (24, 24, 24)
FG = (235, 235, 235)
DIM = (150, 150, 150)
WARN = (255, 170, 60)


def _fit(im, w, h):
    im = im.copy()
    im.thumbnail((w, h), Image.LANCZOS)
    return im


def _clear(folder, pattern):
    os.makedirs(folder, exist_ok=True)
    for p in glob.glob(os.path.join(folder, pattern)):
        os.remove(p)


def _between(r, date_from, date_to):
    d = r.get("date") or ""
    return (not date_from or d >= date_from) and (not date_to or d <= date_to)


# ------------------------------------------------------------ pass 1: contact sheets

def contact_sheets(work, include_all=False, cols=6, rows=5, tile=300, date_from=None, date_to=None):
    cat = common.load_catalog(work)
    photos = [r for r in cat["photos"] if r.get("status") == "ok" and not r.get("dup_of")
              and (include_all or r.get("group_best")) and _between(r, date_from, date_to)]
    out_dir = os.path.join(work, "sheets")
    _clear(out_dir, "sheet_*.jpg")
    per = cols * rows
    pad, label_h, head_h = 8, 44, 46
    f_id, f_small, f_head = common.font(17, bold=True), common.font(14), common.font(22, bold=True)
    index = []
    n_sheets = (len(photos) + per - 1) // per
    for s in range(n_sheets):
        chunk = photos[s * per:(s + 1) * per]
        W = pad + cols * (tile + pad)
        H = head_h + ((len(chunk) + cols - 1) // cols) * (tile + label_h + pad) + pad
        sheet = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(sheet)
        d.text((pad, 10), f"Sheet {s + 1}/{n_sheets}   {chunk[0]['date']} to {chunk[-1]['date']}   "
               f"({len(chunk)} photos)", fill=FG, font=f_head)
        for i, r in enumerate(chunk):
            x = pad + (i % cols) * (tile + pad)
            y = head_h + (i // cols) * (tile + label_h + pad)
            try:
                th = _fit(Image.open(os.path.join(work, "thumbs", r["thumb"])), tile, tile)
                sheet.paste(th, (x + (tile - th.width) // 2, y + (tile - th.height) // 2))
            except Exception:
                d.text((x + 10, y + 10), "thumbnail missing", fill=WARN, font=f_small)
            d.text((x, y + tile + 3), r["id"], fill=FG, font=f_id)
            extra = []
            if r.get("group_size", 1) > 1:
                extra.append(f"x{r['group_size']}")
            extra += r.get("flags", [])
            d.text((x, y + tile + 24), " ".join(extra), fill=WARN if r.get("flags") else DIM, font=f_small)
            index.append({"sheet": s + 1, "id": r["id"], "date": r["date"], "rel": r["rel"]})
        sheet.save(os.path.join(out_dir, f"sheet_{s + 1:03d}.jpg"), quality=88)
    with open(os.path.join(out_dir, "index.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["sheet", "id", "date", "rel"])
        w.writeheader()
        w.writerows(index)
    print(f"{n_sheets} contact sheets ({len(photos)} photos) in {out_dir}")


# ------------------------------------------------------------ pass 2: close-up previews

def _ticks(d, x, y, w, h, font):
    """Tenth marks on all four edges so crop centres can be read off as 0-1 fractions."""
    for k in range(1, 10):
        fx, fy = x + w * k / 10, y + h * k / 10
        ln = 10 if k == 5 else 6
        for (a, b) in (((fx, y), (fx, y + ln)), ((fx, y + h - ln), (fx, y + h)),
                       ((x, fy), (x + ln, fy)), ((x + w - ln, fy), (x + w, fy))):
            d.line([a, b], fill=(255, 255, 0), width=2)
    d.text((x + w / 2 - 12, y + 10), ".5", fill=(255, 255, 0), font=font)


def _to_pil(arr):
    return Image.fromarray(common.to_uint8(arr))


def _crop_at(img, fx, fy, size):
    """size x size pixels at 100%, centred on (fx, fy) given as 0-1 fractions."""
    H, W = img.shape[:2]
    size = min(size, W, H)
    cx, cy = int(fx * W), int(fy * H)
    x0 = max(0, min(W - size, cx - size // 2))
    y0 = max(0, min(H - size, cy - size // 2))
    return _to_pil(img[y0:y0 + size, x0:x0 + size])


def _shot_line(r):
    exp = r.get("exposure_s")
    return " ".join(p for p in [
        r.get("camera") or "",
        f"{r['focal_mm']:.0f}mm" if r.get("focal_mm") else "",
        f"f/{r['fnumber']:.1f}" if r.get("fnumber") else "",
        (f"1/{round(1 / exp)}s" if exp < 1 else f"{exp:g}s") if exp else "",
        f"ISO {r['iso']:.0f}" if r.get("iso") else "",
    ] if p)


def previews(work, ids, cols=2, rows=3, tile_w=560, tile_h=420, inset=220, name="preview"):
    """Bigger views of chosen photos. Beside each one: a 100% crop of its sharpest area
    (cyan circle marks where it is), which shows whether anything is truly in focus."""
    cat = common.load_catalog(work)
    recs = common.by_id(cat)
    missing = [i for i in ids if i not in recs]
    if missing:
        print("Unknown ids (skipped):", " ".join(missing))
    items = [recs[i] for i in ids if i in recs]
    out_dir = os.path.join(work, "previews")
    _clear(out_dir, f"{name}_*.jpg")
    per = cols * rows
    pad, gap, label_h, head_h = 10, 8, 62, 40
    cell_w = tile_w + gap + inset
    f_id, f_small, f_head = common.font(18, bold=True), common.font(14), common.font(19, bold=True)
    n = (len(items) + per - 1) // per
    for s in range(n):
        chunk = items[s * per:(s + 1) * per]
        W = pad + cols * (cell_w + pad)
        H = head_h + ((len(chunk) + cols - 1) // cols) * (tile_h + label_h + pad) + pad
        sheet = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(sheet)
        d.text((pad, 9), f"Close-up review {s + 1}/{n}   yellow ticks = tenths   right = 100% of sharpest "
               f"area (cyan circle)", fill=FG, font=f_head)
        for i, r in enumerate(chunk):
            x = pad + (i % cols) * (cell_w + pad)
            y = head_h + (i // cols) * (tile_h + label_h + pad)
            full = None
            try:
                full, _, _ = common.open_full(r["path"], r["kind"])
                im = _fit(_to_pil(full), tile_w, tile_h)
            except Exception:
                im = Image.new("RGB", (tile_w, tile_h // 2), (60, 0, 0))
            ox, oy = x + (tile_w - im.width) // 2, y + (tile_h - im.height) // 2
            sheet.paste(im, (ox, oy))
            _ticks(d, ox, oy, im.width, im.height, f_small)
            if full is not None:
                rr, cc = r.get("sharp_tile", [GRID // 2, GRID // 2])
                fx, fy = (cc + 0.5) / GRID, (rr + 0.5) / GRID
                ix, iy = x + tile_w + gap, y + (tile_h - inset) // 2
                sheet.paste(_crop_at(full, fx, fy, inset), (ix, iy))
                d.rectangle([ix - 1, iy - 1, ix + inset, iy + inset], outline=(0, 255, 255), width=1)
                mx, my = ox + fx * im.width, oy + fy * im.height
                d.ellipse([mx - 7, my - 7, mx + 7, my + 7], outline=(0, 255, 255), width=2)
            d.text((x, y + tile_h + 4), f"{r['id']}  ({r['width']}x{r['height']})", fill=FG, font=f_id)
            d.text((x, y + tile_h + 26), _shot_line(r)[:80], fill=DIM, font=f_small)
            info = f"sharpness {r['sharp_max']:.0f}"
            if r.get("group_size", 1) > 1:
                info += f"  best of {r['group_size']} similar"
            if r.get("flags"):
                info += "  " + " ".join(r["flags"])
            d.text((x, y + tile_h + 43), info, fill=WARN if r.get("flags") else DIM, font=f_small)
        sheet.save(os.path.join(out_dir, f"{name}_{s + 1:03d}.jpg"), quality=88)
    print(f"{n} close-up sheets ({len(items)} photos) in {out_dir}")


def zoom(work, photo_id, points, size=500):
    """100% crops at chosen points (e.g. the animal's eye) to check focus there."""
    recs = common.by_id(common.load_catalog(work))
    if photo_id not in recs:
        raise SystemExit(f"Unknown id {photo_id}")
    r = recs[photo_id]
    full, _, _ = common.open_full(r["path"], r["kind"])
    pad, head_h = 10, 36
    crops = [(_crop_at(full, fx, fy, size), fx, fy) for fx, fy in points]
    W = pad + len(crops) * (size + pad)
    sheet = Image.new("RGB", (W, size + head_h + pad), BG)
    d = ImageDraw.Draw(sheet)
    f = common.font(16, bold=True)
    for i, (c, fx, fy) in enumerate(crops):
        x = pad + i * (size + pad)
        sheet.paste(c, (x, head_h))
        d.text((x, 10), f"{photo_id} at {fx:.2f},{fy:.2f} (100%)", fill=FG, font=f)
    out_dir = os.path.join(work, "previews")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"zoom_{photo_id}.jpg")
    sheet.save(path, quality=90)
    print(f"Saved {path}")


def group_sheet(work, group_or_id):
    """All frames of one burst/group, so a better pose can be chosen over the sharpest frame."""
    cat = common.load_catalog(work)
    recs = common.by_id(cat)
    gid = recs[group_or_id]["group"] if group_or_id in recs else group_or_id
    ids = [r["id"] for r in cat["photos"] if r.get("group") == gid]
    if not ids:
        raise SystemExit(f"No group found for {group_or_id}")
    previews(work, ids, cols=3, rows=3, tile_w=400, tile_h=300, inset=160, name=f"group_{gid}")


# ------------------------------------------------------------ after editing

def qa_sheets(work, out, cols=4, rows=3, tile=420):
    log_path = os.path.join(out, "edit_log.csv")
    if not os.path.exists(log_path):
        raise SystemExit("No edit_log.csv yet. Run the edit step first.")
    with open(log_path, newline="") as f:
        rows_ = [r for r in csv.DictReader(f) if r.get("status") == "ok"]
    out_dir = os.path.join(work, "review", "qa")
    _clear(out_dir, "qa_*.jpg")
    per = cols * rows
    pad, label_h, head_h = 8, 44, 40
    f_id, f_small, f_head = common.font(16, bold=True), common.font(13), common.font(20, bold=True)
    n = (len(rows_) + per - 1) // per
    for s in range(n):
        chunk = rows_[s * per:(s + 1) * per]
        W = pad + cols * (tile + pad)
        H = head_h + ((len(chunk) + cols - 1) // cols) * (tile + label_h + pad) + pad
        sheet = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(sheet)
        d.text((pad, 9), f"Edited photos {s + 1}/{n}", fill=FG, font=f_head)
        for i, r in enumerate(chunk):
            x = pad + (i % cols) * (tile + pad)
            y = head_h + (i // cols) * (tile + label_h + pad)
            try:
                im = _fit(Image.open(os.path.join(out, r["social"])), tile, tile)
                sheet.paste(im, (x + (tile - im.width) // 2, y + (tile - im.height) // 2))
            except Exception:
                d.text((x + 10, y + 10), "missing", fill=WARN, font=f_small)
            d.text((x, y + tile + 3), f"{r['id']}  {r.get('species', '')}"[:40], fill=FG, font=f_id)
            d.text((x, y + tile + 23), r.get("warnings", "")[:60], fill=WARN, font=f_small)
        sheet.save(os.path.join(out_dir, f"qa_{s + 1:03d}.jpg"), quality=88)
    print(f"{n} check sheets ({len(rows_)} edited photos) in {out_dir}")
