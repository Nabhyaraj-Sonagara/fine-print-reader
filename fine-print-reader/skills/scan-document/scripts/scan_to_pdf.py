#!/usr/bin/env python3
"""Turn phone photos of document pages into one clean PDF.

For each image, in the order given:
  1. Load it and apply the phone's EXIF rotation.
  2. Find the page edges (largest four-sided shape).
  3. Flatten the page with a perspective transform.
  4. Straighten any small leftover tilt.
  5. Remove shadows and raise contrast (color, gray, or bw).
  6. Add the page to the PDF.

If the page edges are not found, the full image is kept and a warning is
printed. OCR (--ocr) is optional: if Tesseract is missing or fails, the PDF
is still written.

Usage:
  scan_to_pdf.py page1.jpg page2.jpg -o lease.pdf
  scan_to_pdf.py *.jpg -o out.pdf --mode bw --pages-dir /tmp/pages --ocr
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

try:
    import cv2
    import numpy as np
    from PIL import Image, ImageOps
except ImportError as exc:
    sys.exit(
        f"Missing Python package ({exc.name}). Install with:\n"
        "  python3 -m pip install opencv-python-headless pillow numpy"
    )

DETECT_HEIGHT = 1000      # work size for edge detection
MAX_SIDE = 3300           # cap output pages at ~300 dpi on a letter page
MIN_PAGE_AREA = 0.20      # a page must cover at least 20% of the photo
MAX_DESKEW_DEG = 10.0
LOW_SHARPNESS = 60.0      # variance of Laplacian below this -> warn


def warn(msg):
    print(f"WARNING: {msg}", file=sys.stderr)


# ---------- loading ----------

def load_image(path):
    """Return an RGB PIL image with EXIF rotation applied."""
    try:
        img = Image.open(path)
    except Exception:
        img = _load_heic(path)
        if img is None:
            raise
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")


def _load_heic(path):
    """HEIC/HEIF photos: try pillow-heif, then macOS `sips`."""
    if not path.lower().endswith((".heic", ".heif")):
        return None
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
        return Image.open(path)
    except ImportError:
        pass
    if shutil.which("sips"):
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False).name
        subprocess.run(["sips", "-s", "format", "jpeg", path, "--out", tmp],
                       check=True, capture_output=True)
        img = Image.open(tmp)
        img.load()
        os.unlink(tmp)
        return img
    return None


# ---------- page detection ----------

def order_corners(pts):
    """Order 4 points as top-left, top-right, bottom-right, bottom-left."""
    pts = pts.reshape(4, 2).astype("float32")
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)],
                     pts[np.argmax(s)], pts[np.argmax(d)]], dtype="float32")


def _quads(mask, min_area, hull=False):
    """Yield convex 4-point outlines of the largest shapes in a mask."""
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        if cv2.contourArea(c) < min_area:
            return
        if hull:
            c = cv2.convexHull(c)
        peri = cv2.arcLength(c, True)
        for eps in (0.02, 0.03, 0.05, 0.08):
            approx = cv2.approxPolyDP(c, eps * peri, True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                yield approx
                break


def _paper_mask(small, kernel):
    """Bright, colorless pixels: what paper looks like."""
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    whiteness = cv2.subtract(hsv[:, :, 2], hsv[:, :, 1])
    whiteness = cv2.GaussianBlur(whiteness, (7, 7), 0)
    _, mask = cv2.threshold(whiteness, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=4)  # fill text
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=3)   # cut thin links
    return mask


def _has_edge(lab, quad, band=8):
    """True if the colors just inside and just outside the outline differ.

    Rejects outlines that sit on paper, such as the block of text on a page
    that fills the whole photo.
    """
    inside = np.zeros(lab.shape[:2], np.uint8)
    cv2.fillConvexPoly(inside, quad.reshape(-1, 2).astype(np.int32), 255)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * band + 1, 2 * band + 1))
    ring_in = cv2.subtract(inside, cv2.erode(inside, k))
    ring_out = cv2.subtract(cv2.dilate(inside, k), inside)
    if cv2.countNonZero(ring_out) < 50:
        return False
    a = np.median(lab[ring_in > 0], axis=0)
    b = np.median(lab[ring_out > 0], axis=0)
    return float(np.linalg.norm(a - b)) > 18


def find_page(bgr):
    """Return the 4 page corners in full-size coordinates, or None."""
    h, w = bgr.shape[:2]
    scale = DETECT_HEIGHT / h if h > DETECT_HEIGHT else 1.0
    small = cv2.resize(bgr, None, fx=scale, fy=scale) if scale != 1.0 else bgr
    sh, sw = small.shape[:2]
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype("float32")
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    min_area = MIN_PAGE_AREA * sh * sw
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))

    # Attempt 1: the paper itself. Robust to busy and patterned backgrounds.
    paper = _paper_mask(small, kernel)
    if cv2.countNonZero(paper) > 0.97 * sh * sw:
        return None  # the page fills the photo: nothing to crop
    candidates = list(_quads(paper, min_area, hull=True))

    # Attempt 2: strong edges. Helps when the background is also light.
    edges = cv2.dilate(cv2.Canny(gray, 50, 150), kernel, iterations=2)
    candidates += list(_quads(edges, min_area))

    for quad in candidates:
        corners = order_corners(quad)
        if _covers_frame(corners, sw, sh) or not _has_edge(lab, quad):
            continue
        return corners / scale
    return None


def _covers_frame(corners, w, h, margin=0.01):
    xs, ys = corners[:, 0], corners[:, 1]
    return (xs.min() <= w * margin and ys.min() <= h * margin
            and xs.max() >= w * (1 - margin) and ys.max() >= h * (1 - margin))


def flatten(bgr, corners):
    tl, tr, br, bl = corners
    width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
                   dtype="float32")
    m = cv2.getPerspectiveTransform(corners, dst)
    page = cv2.warpPerspective(bgr, m, (width, height), flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_REPLICATE)
    # Trim a thin margin so no sliver of background shows at the edges.
    dx, dy = max(2, width // 150), max(2, height // 150)
    return page[dy:height - dy, dx:width - dx]


# ---------- straighten ----------

def _line_score(binary, angle):
    h, w = binary.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rotated = cv2.warpAffine(binary, m, (w, h), flags=cv2.INTER_NEAREST)
    return float(np.var(rotated.sum(axis=1)))


def find_skew(bgr):
    """Angle (degrees) that makes text lines horizontal, by projection profile."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    scale = 800 / max(gray.shape)
    if scale < 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    binary = cv2.adaptiveThreshold(gray, 1, cv2.ADAPTIVE_THRESH_MEAN_C,
                                   cv2.THRESH_BINARY_INV, 25, 15)
    if binary.mean() < 0.005:      # almost no ink: nothing to align
        return 0.0
    best = max(np.arange(-MAX_DESKEW_DEG, MAX_DESKEW_DEG + 0.01, 1.0),
               key=lambda a: _line_score(binary, a))
    best = max(np.arange(best - 1, best + 1.01, 0.1),
               key=lambda a: _line_score(binary, a))
    return float(best)


def rotate(bgr, angle):
    h, w = bgr.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(bgr, m, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)


# ---------- clean up ----------

def _flatten_light(channel, white_margin):
    """Divide out the background (shadows, uneven light), then stretch contrast.

    Most of a page is bare paper, so the median is the paper's brightness.
    Anything within white_margin of it becomes pure white, which wipes out
    leftover grain and faint shadow edges.
    """
    k = max(15, (min(channel.shape) // 40) | 1)
    background = cv2.morphologyEx(channel, cv2.MORPH_CLOSE,
                                  cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    background = cv2.medianBlur(background, 21)
    norm = cv2.divide(channel, background, scale=255)
    lo = np.percentile(norm, 1)
    hi = np.median(norm) - white_margin
    if hi - lo < 1:
        return norm
    out = np.clip((norm.astype("float32") - lo) * 255.0 / (hi - lo), 0, 255)
    return out.astype("uint8")


def clean(bgr, mode):
    if mode == "color":
        # Gentler, so stamps, logos and highlighter keep their color.
        return cv2.merge([_flatten_light(c, 4) for c in cv2.split(bgr)])
    gray = _flatten_light(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), 12)
    if mode == "gray":
        return gray
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY, 31, 12)


def sharpness(bgr):
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    scale = 1500 / max(gray.shape)
    if scale < 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def cap_size(img):
    h, w = img.shape[:2]
    s = MAX_SIDE / max(h, w)
    if s < 1:
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    return img


# ---------- OCR ----------

def ocr_page(pil_img):
    """Return text, or None if Tesseract is unavailable or fails."""
    try:
        import pytesseract
        return pytesseract.image_to_string(pil_img)
    except ImportError:
        pass
    except Exception as exc:
        warn(f"OCR failed: {exc}")
        return None
    if not shutil.which("tesseract"):
        return None
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp = f.name
    try:
        pil_img.save(tmp)
        r = subprocess.run(["tesseract", tmp, "-", "--psm", "3"],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            warn(f"OCR failed: {r.stderr.strip()[:200]}")
            return None
        return r.stdout
    except Exception as exc:
        warn(f"OCR failed: {exc}")
        return None
    finally:
        os.unlink(tmp)


# ---------- main ----------

def process(path, mode, crop):
    info = {"source": os.path.basename(path), "cropped": False, "deskew_deg": 0.0}
    bgr = cv2.cvtColor(np.array(load_image(path)), cv2.COLOR_RGB2BGR)
    info["sharpness"] = round(sharpness(bgr), 1)

    if crop:
        corners = find_page(bgr)
        if corners is None:
            warn(f"{info['source']}: page edges not found; kept the full image.")
        else:
            bgr = flatten(bgr, corners)
            info["cropped"] = True

    angle = find_skew(bgr)
    if abs(angle) >= 0.3:
        bgr = rotate(bgr, angle)
        info["deskew_deg"] = round(angle, 1)

    out = clean(cap_size(bgr), mode)
    if out.ndim == 3:
        pil = Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
    else:
        pil = Image.fromarray(out)
        if mode == "bw":
            pil = pil.convert("1")
    if info["sharpness"] < LOW_SHARPNESS:
        warn(f"{info['source']}: low sharpness ({info['sharpness']}); check that text is readable.")
    return pil, info


def main():
    ap = argparse.ArgumentParser(description="Turn photos of document pages into one clean PDF.")
    ap.add_argument("images", nargs="+", help="page images, in page order")
    ap.add_argument("-o", "--output", required=True, help="output PDF path")
    ap.add_argument("--mode", choices=["color", "gray", "bw"], default="gray",
                    help="clean-up mode (default: gray)")
    ap.add_argument("--no-crop", action="store_true",
                    help="skip edge detection, for photos that are already cropped")
    ap.add_argument("--ocr", action="store_true",
                    help="also write OCR text next to the PDF (needs Tesseract)")
    ap.add_argument("--pages-dir", help="also save each cleaned page as a PNG here")
    args = ap.parse_args()

    pages, report = [], []
    for i, path in enumerate(args.images, 1):
        try:
            pil, info = process(path, args.mode, not args.no_crop)
        except Exception as exc:
            sys.exit(f"ERROR: could not process {path}: {exc}")
        info["page"] = i
        pages.append(pil)
        report.append(info)
        if args.pages_dir:
            os.makedirs(args.pages_dir, exist_ok=True)
            info["png"] = os.path.join(args.pages_dir, f"page-{i:02d}.png")
            pil.save(info["png"])

    # Size each PDF page so the long side is 11 inches (letter/A4 scale).
    first, rest = pages[0], pages[1:]
    dpi = max(first.size) / 11.0
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    # bw pages are stored with lossless fax compression, which takes no quality.
    extra = {} if args.mode == "bw" else {"quality": 85}
    first.save(args.output, "PDF", save_all=True, append_images=rest,
               resolution=dpi, **extra)

    result = {"pdf": os.path.abspath(args.output), "mode": args.mode, "pages": report}

    if args.ocr:
        texts = [ocr_page(p.convert("L")) for p in pages]
        if any(t is None for t in texts):
            warn("OCR unavailable or failed; continuing without OCR text.")
        else:
            txt_path = os.path.splitext(args.output)[0] + ".txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                for i, t in enumerate(texts, 1):
                    f.write(f"===== Page {i} =====\n{t.strip()}\n\n")
            result["ocr_text"] = os.path.abspath(txt_path)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
