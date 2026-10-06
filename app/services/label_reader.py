"""Local label preparation and independent OCR. No model calls or source edits."""

import re
import time
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageOps

FIBRES = {
    "polyester": "Polyester",
    "spandex": "Spandex",
    "elastane": "Elastane",
    "elastan": "Elastane",
    "nylon": "Nylon",
    "polyamide": "Polyamide",
    "cotton": "Cotton",
    "wool": "Wool",
    "linen": "Linen",
    "laine": "Wool",
    "lana": "Wool",
    "wolle": "Wool",
    "soie": "Silk",
    "seide": "Silk",
    "coton": "Cotton",
    "cotone": "Cotton",
    "baumwolle": "Cotton",
    "angora": "Angora",
    "alpaca": "Alpaca",
    "alpaga": "Alpaca",
    "mohair": "Mohair",
    "lambswool": "Lambswool",
    "elasthanne": "Elastane",
    "cashmire": "Cashmere",
    "kaschmir": "Cashmere",
    "viscose": "Viscose",
    "silk": "Silk",
    "cashmere": "Cashmere",
    "acrylic": "Acrylic",
    "modal": "Modal",
    "lyocell": "Lyocell",
}


def pairs(text):
    result = []
    section = "main"
    text = re.sub(r"(?i)\b(shell|outer|lining|doublure|futter)\b", r"\n\1 ", text)
    for line in text.splitlines():
        if re.search(r"\b(?:lining|doublure|futter)\b", line, re.I):
            section = "lining"
        elif re.search(r"\b(?:shell|outer)\b", line, re.I):
            section = "shell"
        found = list(re.finditer(r"(\d+(?:[.,]\d+)?)\s*%\s*([a-z]+)", line, re.I))
        for match in found:
            fibre = FIBRES.get(match[2].lower())
            if not fibre:
                return []
            value = float(match[1].replace(",", "."))
            if not 0 < value <= 100:
                return []
            record = (section, value, fibre)
            if record not in result:
                result.append(record)
        if "%" in line and not found:
            return []
    if not result:
        return []
    for section in {p[0] for p in result}:
        if abs(sum(p[1] for p in result if p[0] == section) - 100) > 0.1:
            return []
    return result


def canonical(records):
    # Same fibre, printed synonyms. Section assignments must still agree.
    aliases = {"Spandex": "Elastane", "Nylon": "Polyamide"}
    return sorted((s, v, aliases.get(f, f)) for s, v, f in records)


def matches(materials, reading):
    records = pairs("\n".join(materials or []))
    return bool(records) and canonical(records) == canonical(reading.get("pairs") or [])


def crop_label(image):
    """Rectify a well-supported light rectangular tag, otherwise retain original."""
    import cv2
    import numpy as np

    scale = min(1, 900 / max(image.size))
    small = image.resize(
        (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    )
    arr = np.array(small)
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, np.array([0, 0, 105]), np.array([179, 60, 255]))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((17, 17), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    area = small.width * small.height
    for contour in contours:
        size = cv2.contourArea(contour)
        rect = cv2.minAreaRect(contour)
        w, h = rect[1]
        if w < 20 or h < 20 or not 0.025 < size / area < 0.85:
            continue
        if size / (w * h) < 0.75 or max(w, h) / min(w, h) > 5:
            continue
        candidates.append((size, rect))
    if not candidates:
        return image, {"rectified": False}
    _, rect = max(candidates, key=lambda p: p[0])
    points = cv2.boxPoints(rect) / scale
    total = points.sum(axis=1)
    diff = np.diff(points, axis=1).ravel()
    ordered = np.array(
        [
            points[total.argmin()],
            points[diff.argmin()],
            points[total.argmax()],
            points[diff.argmax()],
        ],
        dtype=np.float32,
    )
    width = int(
        max(
            np.linalg.norm(ordered[1] - ordered[0]),
            np.linalg.norm(ordered[2] - ordered[3]),
        )
    )
    height = int(
        max(
            np.linalg.norm(ordered[3] - ordered[0]),
            np.linalg.norm(ordered[2] - ordered[1]),
        )
    )
    if width < 30 or height < 30:
        return image, {"rectified": False}
    destination = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(ordered, destination)
    cropped = cv2.warpPerspective(
        np.array(image), transform, (width, height), borderValue=(255, 255, 255)
    )
    return ImageOps.expand(Image.fromarray(cropped), border=12, fill="white"), {
        "rectified": True,
        "crop_size": [width, height],
    }


@lru_cache(maxsize=1)
def _engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)


def _ocr(image, rotation):
    import numpy as np

    rotated = image.rotate(rotation, expand=True, fillcolor="white")
    result, _ = _engine()(np.array(rotated), use_cls=True)
    lines = [(str(row[1]), float(row[2])) for row in (result or [])]
    text = "\n".join(line for line, confidence in lines)
    relevant = [confidence for line, confidence in lines if "%" in line]
    parsed = pairs(text)
    good = bool(parsed and relevant) and min(relevant) >= 0.95
    vertical = sum(
        abs(row[0][2][1] - row[0][0][1]) > abs(row[0][2][0] - row[0][0][0])
        for row in (result or [])
        if "%" in str(row[1])
    )
    return {
        "pairs": parsed if good else [],
        "text": text,
        "rotation": rotation,
        "vertical": bool(vertical),
        "min_confidence": min(relevant) if relevant else 0,
    }


@lru_cache(maxsize=8)
def _prepare(filename, modified, size):
    start = time.perf_counter()
    with Image.open(filename) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    image.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
    try:
        image, meta = crop_label(image)
    except ImportError:
        meta = {"rectified": False, "preparation_unavailable": True}
    reading = {"status": "unreadable", "pairs": [], "text": ""}
    # Blank images are common in tests; avoid subprocesses when no text contrast exists.
    grey = image.convert("L")
    extrema = grey.getextrema()
    if extrema[1] - extrema[0] > 35:
        try:
            # Two perpendicular views; the local reader handles 180-degree flips.
            reads = [_ocr(image, rotation) for rotation in (0, 90)]
        except ImportError:
            reads = []
            reading["status"] = "unavailable"
        valid = [r for r in reads if r["pairs"]]
        if valid and len({tuple(canonical(r["pairs"])) for r in valid}) == 1:
            best = max(
                valid, key=lambda r: (not r.get("vertical"), r["min_confidence"])
            )
            reading = dict(best, status="readable")
            image = image.rotate(best["rotation"], expand=True, fillcolor="white")
            meta["rotation"] = best["rotation"]
        elif valid:
            reading["status"] = "conflicting_ocr"
    reading["preparation"] = meta
    reading["local_latency_ms"] = round((time.perf_counter() - start) * 1000)
    return image, reading


def prepare(path):
    path = Path(path)
    info = path.stat()
    image, reading = _prepare(str(path.resolve()), info.st_mtime_ns, info.st_size)
    from copy import deepcopy

    return image.copy(), deepcopy(reading)


def read_folder(folder):
    for extension in (".jpg", ".jpeg", ".png", ".webp"):
        path = Path(folder) / ("material" + extension)
        if path.is_file():
            try:
                return prepare(path)[1]
            except (OSError, ValueError):
                return {"status": "unreadable", "pairs": [], "text": ""}
    return {"status": "not_present", "pairs": [], "text": ""}


def check(item, reading):
    """Require independent agreement on numeric composition from a material photo.

    Preserve candidates for review, never replace seller facts or guess missing digits.
    Missing named photos retain the existing cross-slot extraction behavior.
    """
    item["material_verification"] = reading
    if reading["status"] == "not_present":
        return
    materials = item.get("materials") or []
    numeric = any("%" in str(value) for value in materials)
    if not numeric:
        return
    if reading["status"] == "readable" and matches(materials, reading):
        item["material_confidence"] = "high"
        item["low_confidence_fields"] = [
            f
            for f in item.get("low_confidence_fields", [])
            if f
            not in {
                "materials",
                "material_confidence",
                "material_reason",
                "material_candidates",
            }
        ]
        item["material_reason"] = "Independent local label transcription agrees"
    else:
        item["material_confidence"] = "medium"
        fields = item.setdefault("low_confidence_fields", [])
        if "materials" not in fields:
            fields.append("materials")
        item["material_reason"] = (
            "Material readings disagree; check label"
            if reading["status"] == "readable"
            else "Exact material percentages could not be independently verified; check label"
        )
