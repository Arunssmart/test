"""Builds a small made-up photo library and runs every step on it."""

import csv
import json
import os
import shutil
import tempfile

import cv2
import numpy as np
from PIL import Image

from . import edit, organize, report, scan, sheets


def _fake_photo(seed, w=1800, h=1200, blur=0.0, dark=1.0):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    bg = np.stack([0.25 + 0.2 * xx / w, 0.35 + 0.15 * yy / h, np.full_like(xx, 0.2 + 0.1 * rng.random())], axis=2)
    bg = cv2.GaussianBlur(bg.astype(np.float32), (0, 0), 25)
    cx, cy = w * (0.3 + 0.4 * rng.random()), h * (0.35 + 0.3 * rng.random())
    body = ((xx - cx) / (w * 0.12)) ** 2 + ((yy - cy) / (h * 0.15)) ** 2 < 1
    img = bg.copy()
    img[body] = [0.55, 0.38, 0.2]
    stripes = (np.sin(xx / 6.0) > 0.6) & body
    img[stripes] = [0.1, 0.08, 0.05]
    img += rng.normal(0, 0.01, img.shape).astype(np.float32)
    if blur:
        img = cv2.GaussianBlur(img, (0, 0), blur)
    return Image.fromarray((np.clip(img * dark, 0, 1) * 255).astype(np.uint8))


def _save(im, path, when=None, iso=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ex = Image.Exif()
    ex[271], ex[272] = "TestMaker", "TestCam 1"
    if when:
        sub = ex.get_ifd(0x8769)
        sub[36867] = when
        if iso:
            sub[34855] = iso
    im.save(path, quality=92, exif=ex.tobytes())


def run():
    tmp = tempfile.mkdtemp(prefix="wpk-selftest-")
    src, work, out = (os.path.join(tmp, x) for x in ("photos", "work", "out"))
    try:
        # a burst of three on one day (one blurry), a dark photo, a copy, an undated file
        _save(_fake_photo(1), f"{src}/2017 trip/IMG_0001.JPG", "2017:03:12 07:15:00")
        _save(_fake_photo(1, blur=0.6), f"{src}/2017 trip/IMG_0002.JPG", "2017:03:12 07:15:01")
        _save(_fake_photo(1, blur=4), f"{src}/2017 trip/IMG_0003.JPG", "2017:03:12 07:15:02")
        _save(_fake_photo(2, dark=0.35), f"{src}/2017 trip/IMG_0010.JPG", "2017:03:12 09:40:00", iso=6400)
        _save(_fake_photo(3), f"{src}/2021/DSC_5001.jpg", "2021:11:02 16:05:00")
        shutil.copy2(f"{src}/2021/DSC_5001.jpg", f"{src}/2021/DSC_5001 copy.jpg")
        _fake_photo(4).save(f"{src}/2021/IMG-20210105-WA0003.jpg", quality=90)  # date only in the name
        _fake_photo(5).save(f"{src}/2021/nodate.jpg", quality=90)
        with open(f"{src}/2021/notes.txt", "w") as f:
            f.write("not a photo")
        with open(f"{src}/2021/broken.jpg", "wb") as f:
            f.write(b"not really a jpeg")

        scan.run(src, work, workers=2)
        with open(os.path.join(work, "catalog.json")) as f:
            cat = json.load(f)
        ok = {os.path.basename(r["rel"]): r for r in cat["photos"] if r["status"] == "ok"}
        assert len(ok) == 8, ok.keys()
        assert any(r["status"] == "error" for r in cat["photos"]), "broken file should be reported"
        assert ok["IMG_0001.JPG"]["group"] == ok["IMG_0003.JPG"]["group"], "burst not grouped"
        assert ok["IMG_0003.JPG"]["group_best"] is False, "blurry frame picked as best"
        assert ok["DSC_5001 copy.jpg"]["dup_of"] or ok["DSC_5001.jpg"]["dup_of"], "copy not found"
        assert ok["IMG-20210105-WA0003.jpg"]["date"] == "2021-01-05"
        assert ok["IMG-20210105-WA0003.jpg"]["date_source"] == "filename"
        assert ok["nodate.jpg"]["date_source"] == "file-modified"

        organize.run(work, os.path.join(out, "By Date"), mode="auto")
        assert os.path.exists(os.path.join(out, "By Date", "2017", "2017-03-12", "IMG_0001.JPG"))
        # a By Date folder inside the photo folder is skipped by later scans
        organize.run(work, os.path.join(src, "By Date"), mode="auto")
        scan.run(src, work, workers=2)
        with open(os.path.join(work, "catalog.json")) as f:
            assert len([r for r in json.load(f)["photos"] if r["status"] == "ok"]) == 8, "By Date rescanned"

        sheets.contact_sheets(work)
        assert os.path.exists(os.path.join(work, "sheets", "sheet_001.jpg"))
        ids = [ok["IMG_0001.JPG"]["id"], ok["IMG_0010.JPG"]["id"], ok["DSC_5001.jpg"]["id"]]
        sheets.previews(work, ids)
        assert os.path.exists(os.path.join(work, "previews", "preview_001.jpg"))

        picks = os.path.join(work, "picks.csv")
        with open(picks, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(edit.PICK_COLUMNS)
            w.writerow([ids[0], "Test tiger", "Morning light", "4:5", "0.5", "0.5", "0.9", "1.5", "", "", "", ""])
            w.writerow([ids[1], "Dark test", "", "", "", "", "", "", "", "0.5", "", ""])
            w.writerow([ids[2], "BW test", "", "1:1", "", "", "", "", "", "", "bw", ""])
        edit.run(work, picks, out, compare=True)
        for i in ids:
            assert os.path.exists(os.path.join(work, "review", "compare", f"{i}.jpg"))
        e = Image.open(os.path.join(out, "Edited", "2017", "2017-03-12", f"{ids[0]}_IMG_0001.jpg"))
        assert abs(e.width / e.height - 0.8) < 0.01, e.size
        assert e.getexif().get_ifd(0x8769).get(36867) == "2017:03:12 07:15:00", "date lost in edit"
        sheets.qa_sheets(work, out)
        os.makedirs(os.path.join(out, "Posts"), exist_ok=True)
        with open(os.path.join(out, "Posts", "2017-03-12.md"), "w") as f:
            f.write("Test post\n#wildlife")
        report.run(work, out)
        with open(os.path.join(out, "index.html")) as f:
            assert "Test post" in f.read()
        print("\nSELFTEST PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
