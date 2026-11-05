"""Shared helpers: finding photos, reading dates and camera data, loading pixels."""

import datetime as dt
import io
import json
import os
import re
import shutil
import subprocess

import numpy as np
from PIL import Image, ImageFont, ImageOps

Image.MAX_IMAGE_PIXELS = 400_000_000  # allow large panoramas

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    HAVE_HEIF = True
except Exception:
    HAVE_HEIF = False

try:
    import rawpy

    HAVE_RAW = True
except Exception:
    HAVE_RAW = False

STD_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
HEIF_EXT = {".heic", ".heif"}
RAW_EXT = {
    ".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".raf", ".orf",
    ".rw2", ".pef", ".dng", ".srw", ".3fr", ".iiq", ".erf", ".kdc", ".mrw",
}
SKIP_DIRS = {"@eaDir", "$RECYCLE.BIN", "System Volume Information", "__MACOSX", ".Trashes"}
# Folders the kit creates carry one of these marker files, so later scans skip them.
MARKERS = {".wildlife-kit-bydate", ".wildlife-kit-output", ".wildlife-kit-work"}


def mark_folder(folder, marker, note):
    os.makedirs(folder, exist_ok=True)
    p = os.path.join(folder, marker)
    if not os.path.exists(p):
        with open(p, "w") as f:
            f.write(note + "\n")

LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def kind_of(path):
    """Return 'std', 'heif', 'raw' or None for files we don't handle."""
    ext = os.path.splitext(path)[1].lower()
    if ext in STD_EXT:
        return "std"
    if ext in HEIF_EXT:
        return "heif"
    if ext in RAW_EXT:
        return "raw"
    return None


def find_photos(src, exclude=()):
    """Yield (abs_path, rel_path, kind) for every photo under src.

    Skips hidden files, macOS '._' files, Photos/Lightroom library packages
    and any folder listed in `exclude` (our own work/output folders).
    """
    src = os.path.abspath(src)
    exclude = [os.path.abspath(e) for e in exclude if e]
    skipped = {"unsupported": 0, "library_packages": [], "raw_no_decoder": 0, "heif_no_decoder": 0}
    out = []
    for root, dirs, files in os.walk(src):
        if root != src and MARKERS.intersection(files):
            dirs[:] = []
            continue
        keep = []
        for d in dirs:
            full = os.path.join(root, d)
            if d.startswith(".") or d in SKIP_DIRS:
                continue
            if d.endswith((".photoslibrary", ".lrdata", ".aplibrary", ".migratedphotolibrary")):
                skipped["library_packages"].append(full)
                continue
            if any(full == e or full.startswith(e + os.sep) for e in exclude):
                continue
            keep.append(d)
        dirs[:] = sorted(keep)
        for f in sorted(files):
            if f.startswith("."):
                continue
            full = os.path.join(root, f)
            k = kind_of(f)
            if k is None:
                skipped["unsupported"] += 1
                continue
            if k == "raw" and not HAVE_RAW:
                skipped["raw_no_decoder"] += 1
                continue
            if k == "heif" and not HAVE_HEIF:
                skipped["heif_no_decoder"] += 1
                continue
            out.append((full, os.path.relpath(full, src), k))
    return out, skipped


# ---------------------------------------------------------------- dates

_EXIF_DT = re.compile(r"(\d{4})[:\-](\d{2})[:\-](\d{2})[ T](\d{2}):(\d{2}):(\d{2})")
_NAME_DT = re.compile(
    r"(?<!\d)((?:19|20)\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])"
    r"(?:[ _T\-.]?([01]\d|2[0-3])[-_.:h]?([0-5]\d)[-_.:m]?([0-5]\d))?(?!\d)"
)


def _valid(d):
    return d is not None and 1990 <= d.year <= dt.date.today().year + 1


def parse_exif_datetime(s):
    if not s:
        return None
    if isinstance(s, bytes):
        s = s.decode("ascii", "ignore")
    m = _EXIF_DT.search(str(s))
    if not m:
        return None
    try:
        d = dt.datetime(*[int(x) for x in m.groups()])
    except ValueError:
        return None
    return d if _valid(d) else None


def date_from_name(name):
    m = _NAME_DT.search(name)
    if not m:
        return None
    y, mo, da, h, mi, se = m.groups()
    try:
        d = dt.datetime(int(y), int(mo), int(da), int(h or 12), int(mi or 0), int(se or 0))
    except ValueError:
        return None
    return d if _valid(d) else None


def _num(v):
    try:
        if isinstance(v, tuple):
            v = v[0]
        return float(v)
    except Exception:
        return None


def _gps(g):
    try:
        def dms(t):
            return float(t[0]) + float(t[1]) / 60 + float(t[2]) / 3600

        lat, lon = dms(g[2]), dms(g[4])
        if str(g.get(1, "N")).upper().startswith("S"):
            lat = -lat
        if str(g.get(3, "E")).upper().startswith("W"):
            lon = -lon
        if lat == 0 and lon == 0:
            return None
        return round(lat, 6), round(lon, 6)
    except Exception:
        return None


def exif_meta(im):
    """Camera data from a Pillow image's EXIF. Missing values are None."""
    try:
        ex = im.getexif()
    except Exception:
        return {}
    return meta_from_exif(ex)


def raw_exif(path):
    """EXIF straight from a TIFF-based RAW file (NEF, CR2, ARW, DNG, ORF, PEF, ...)."""
    try:
        with open(path, "rb") as f:
            data = f.read(4_000_000)
        if data[:4] not in (b"II*\x00", b"MM\x00*"):
            return {}
        ex = Image.Exif()
        ex.load(data)
        return meta_from_exif(ex)
    except Exception:
        return {}


def meta_from_exif(ex):
    meta = {}
    sub = ex.get_ifd(0x8769) if ex else {}
    gps = ex.get_ifd(0x8825) if ex else {}
    taken = None
    for tag, src in ((36867, "camera"), (36868, "camera"), (306, "camera-modified")):
        taken = parse_exif_datetime(sub.get(tag) if tag != 306 else ex.get(tag))
        if taken:
            meta["date_source"] = src
            break
    if taken:
        sub_s = str(sub.get(37521) or "").strip()
        if sub_s.isdigit():
            taken = taken + dt.timedelta(seconds=float("0." + sub_s))
        meta["taken"] = taken
    make = str(ex.get(271) or "").strip().strip("\x00")
    model = str(ex.get(272) or "").strip().strip("\x00")
    if model and make and not model.lower().startswith(make.split()[0].lower()):
        model = f"{make} {model}"
    meta["camera"] = model or make or None
    lens = sub.get(42036)
    meta["lens"] = str(lens).strip().strip("\x00") if lens else None
    meta["focal_mm"] = _num(sub.get(37386))
    meta["fnumber"] = _num(sub.get(33437))
    meta["exposure_s"] = _num(sub.get(33434))
    meta["iso"] = _num(sub.get(34855))
    meta["orientation"] = ex.get(274)
    g = _gps(gps) if gps else None
    meta["gps"] = list(g) if g else None
    return meta


def external_date(path):
    """Capture date for files Pillow can't read EXIF from (RAW). Uses exiftool or macOS mdls."""
    if shutil.which("exiftool"):
        try:
            r = subprocess.run(
                ["exiftool", "-s3", "-DateTimeOriginal", "-CreateDate", path],
                capture_output=True, text=True, timeout=30,
            )
            for line in r.stdout.splitlines():
                d = parse_exif_datetime(line)
                if d:
                    return d
        except Exception:
            pass
    if shutil.which("mdls"):
        try:
            r = subprocess.run(
                ["mdls", "-raw", "-name", "kMDItemContentCreationDate", path],
                capture_output=True, text=True, timeout=30,
            )
            s = r.stdout.strip()
            # e.g. "2019-05-12 09:14:03 +0000" (UTC); convert to local time
            d = dt.datetime.strptime(s[:25], "%Y-%m-%d %H:%M:%S %z").astimezone().replace(tzinfo=None)
            if _valid(d):
                return d
        except Exception:
            pass
    return None


# ---------------------------------------------------------------- pixels

def _to_rgb(im):
    if im.mode == "RGB":
        return im
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        return bg
    if im.mode.startswith("I;16") or im.mode == "I":
        a = np.asarray(im).astype(np.float32)
        a = a / (65535.0 if a.max() > 255 else 255.0)
        return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)).convert("RGB")
    return im.convert("RGB")


def _raw_thumb(path):
    with rawpy.imread(path) as r:
        try:
            t = r.extract_thumb()
            if t.format == rawpy.ThumbFormat.JPEG:
                im = Image.open(io.BytesIO(t.data))
                im.load()
                return ImageOps.exif_transpose(im).convert("RGB"), (r.sizes.width, r.sizes.height)
            return Image.fromarray(t.data).convert("RGB"), (r.sizes.width, r.sizes.height)
        except Exception:
            rgb = r.postprocess(half_size=True, use_camera_wb=True)
            return Image.fromarray(rgb), (r.sizes.width, r.sizes.height)


def open_preview(path, kind, max_side=1600):
    """Fast, reduced-size RGB image plus original (oriented) size and camera data."""
    if kind == "raw":
        im, size = _raw_thumb(path)
        meta = raw_exif(path)
        if not meta.get("taken"):
            d = external_date(path)
            if d:
                meta.update(taken=d, date_source="camera")
        meta["orientation"] = None
        if im.width < im.height and size[0] > size[1]:
            size = (size[1], size[0])
        im.thumbnail((max_side, max_side), Image.LANCZOS)
        return im, size, meta
    im = Image.open(path)
    meta = exif_meta(im)
    w, h = im.size
    if meta.get("orientation") in (5, 6, 7, 8):
        w, h = h, w
    if im.format == "JPEG":
        im.draft("RGB", (max_side, max_side))
    im = ImageOps.exif_transpose(im)
    im = _to_rgb(im)
    im.thumbnail((max_side, max_side), Image.LANCZOS)
    return im, (w, h), meta


def to_float(a):
    """uint8 / uint16 / float image to float32 in 0..1."""
    if a.dtype == np.uint8:
        return a.astype(np.float32) * np.float32(1 / 255)
    if a.dtype == np.uint16:
        return a.astype(np.float32) * np.float32(1 / 65535)
    return a.astype(np.float32, copy=False)


def to_uint8(a):
    if a.dtype == np.uint8:
        return a
    if a.dtype == np.uint16:
        return (a >> 8).astype(np.uint8)
    return (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)


_KEEP_IFD0 = (271, 272, 305, 306, 315, 33432)
_KEEP_EXIF = (33434, 33437, 34850, 34855, 36867, 36868, 36880, 36881, 37377, 37378, 37380,
              37383, 37385, 37386, 37521, 37522, 41989, 42033, 42034, 42035, 42036)


def minimal_exif(ex):
    """The useful EXIF tags (camera, lens, settings, date, GPS) without maker notes."""
    try:
        out = Image.Exif()
        for t in _KEEP_IFD0:
            if t in ex:
                out[t] = ex[t]
        sub, dst = ex.get_ifd(0x8769), out.get_ifd(0x8769)
        for t in _KEEP_EXIF:
            if t in sub:
                dst[t] = sub[t]
        gps = ex.get_ifd(0x8825)
        if gps:
            out.get_ifd(0x8825).update(gps)
        out[274] = 1
        out[305] = "Wildlife Photo Kit"
        return out.tobytes()
    except Exception:
        return None


def open_full(path, kind):
    """Full-size image (uint8 or uint16 RGB, sRGB), plus EXIF bytes and ICC profile to carry over."""
    if kind == "raw":
        with rawpy.imread(path) as r:
            rgb = r.postprocess(use_camera_wb=True, output_bps=16, bright=1.0)
        exif = None
        try:
            with open(path, "rb") as f:
                data = f.read(4_000_000)
            if data[:4] in (b"II*\x00", b"MM\x00*"):
                ex = Image.Exif()
                ex.load(data)
                exif = minimal_exif(ex)
        except Exception:
            exif = None
        return rgb, exif, None
    im = Image.open(path)
    exif = None
    try:
        ex = im.getexif()
        if ex:
            ex[274] = 1  # pixels get rotated upright below
            ex[305] = "Wildlife Photo Kit"
            exif = ex.tobytes()
            if len(exif) > 65000:  # too big for a JPEG header (huge maker notes)
                exif = minimal_exif(ex)
    except Exception:
        exif = None
    icc = im.info.get("icc_profile")
    im = ImageOps.exif_transpose(im)
    if im.mode in ("I;16", "I;16B", "I;16L", "I"):
        a = np.asarray(im)
        a = (a.astype(np.uint16) if a.max() > 255 else (a.astype(np.uint16) * 257))
        return np.repeat(a[..., None], 3, axis=2), exif, icc
    im = _to_rgb(im)
    return np.asarray(im), exif, icc


# ---------------------------------------------------------------- misc

def font(size, bold=False):
    names = (
        ["DejaVuSans-Bold.ttf", "Arial Bold.ttf", "Helvetica.ttc"]
        if bold
        else ["DejaVuSans.ttf", "Arial.ttf", "Helvetica.ttc"]
    )
    dirs = [
        "/usr/share/fonts/truetype/dejavu",
        "/System/Library/Fonts/Supplemental",
        "/System/Library/Fonts",
        "/Library/Fonts",
        "C:/Windows/Fonts",
    ]
    for d in dirs:
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def load_catalog(work):
    p = os.path.join(work, "catalog.json")
    if not os.path.exists(p):
        raise SystemExit(f"No catalog found in {work}. Run the scan step first.")
    with open(p) as f:
        return json.load(f)


def by_id(catalog):
    return {r["id"]: r for r in catalog["photos"] if r.get("id")}


def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1, default=str)
    os.replace(tmp, path)


def read_id_list(path_or_ids):
    """Accept a file (one id per line, or a CSV with an 'id' column) or a comma/space separated string."""
    if path_or_ids and os.path.exists(path_or_ids):
        import csv

        with open(path_or_ids, newline="") as f:
            text = f.read()
        lines = [l for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]
        if lines and "id" in [c.strip().lower() for c in lines[0].split(",")]:
            rows = csv.DictReader(io.StringIO("\n".join(lines)))
            return [r.get("id", "").strip() for r in rows if r.get("id", "").strip()]
        return [l.split(",")[0].strip() for l in lines]
    return [x for x in re.split(r"[,\s]+", path_or_ids or "") if x]
