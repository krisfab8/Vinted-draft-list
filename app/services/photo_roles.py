"""
Local photo role scorer.

Classifies uploaded clothing photos into extraction roles using Pillow image
statistics + upload order as a weak prior.  No extra AI/API calls.

Role names match what _load_photos() and draft_creator expect:
    front, brand, model_size, material, back, extra_01, extra_02, ...

Scoring signals:
    - aspect_ratio  : portrait (< 0.75) → likely garment overview
    - brightness    : high (> 150) → likely bright label background
    - edge_density  : high (FIND_EDGES mean) → text-heavy label
    - color_richness: max(R,G,B) - min(R,G,B) means; high → colourful garment
    - order_prior   : index 0→front, 1→brand, 2→model_size, 3→material, 4→back
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFilter, ImageStat

# Ordered role names used by _load_photos() / extractor pipeline
PIPELINE_ROLES: tuple[str, ...] = ("front", "brand", "model_size", "material", "back")

# Order prior: which role is most likely at each upload index position
_ORDER_PRIOR: dict[int, str] = {
    0: "front",
    1: "brand",
    2: "model_size",
    3: "material",
    4: "back",
}

# Low-confidence threshold for warnings
LOW_CONFIDENCE_THRESHOLD = 0.45


def _image_stats(path: Path) -> dict[str, float]:
    """Compute lightweight image features using Pillow only."""
    img = Image.open(path).convert("RGB")
    w, h = img.size

    gray = img.convert("L")
    brightness = ImageStat.Stat(gray).mean[0]
    contrast = ImageStat.Stat(gray).stddev[0]

    # Edge density: proxy for text / fine detail richness
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_density = ImageStat.Stat(edges).mean[0]

    # Color richness: rough saturation proxy (no HSV needed)
    r_ch, g_ch, b_ch = img.split()
    r_m = ImageStat.Stat(r_ch).mean[0]
    g_m = ImageStat.Stat(g_ch).mean[0]
    b_m = ImageStat.Stat(b_ch).mean[0]
    color_richness = max(r_m, g_m, b_m) - min(r_m, g_m, b_m)

    return {
        "aspect": w / h,          # > 1 landscape, < 1 portrait
        "brightness": brightness,  # 0–255
        "contrast": contrast,      # std dev of grey
        "edge_density": edge_density,
        "color_richness": color_richness,
    }


def _score_roles(stats: dict[str, float], order: int) -> dict[str, float]:
    """Return a confidence score per role for a single photo.

    Scores are additive; they are NOT probabilities.
    The order prior is the dominant signal for well-ordered uploads.
    Feature scores act as a tie-breaker / sanity check.
    """
    a  = stats["aspect"]
    br = stats["brightness"]
    ed = stats["edge_density"]
    cr = stats["color_richness"]

    # ── Feature scores ────────────────────────────────────────────────────────

    # Garment overview (front / back): tall portrait, colourful, not washed-out
    garment = 0.25
    if a < 0.75:   garment += 0.30   # portrait orientation
    if cr > 20:    garment += 0.20   # colourful garment
    if br < 210:   garment += 0.10   # not over-exposed white

    # Label / OCR photo (brand / size tag / material): bright bg, text edges
    label = 0.20
    if br > 140:   label += 0.25    # bright / white background
    if ed > 10:    label += 0.25    # text creates many edges
    if cr < 35:    label += 0.15    # low colour variance = neutral label bg

    scores: dict[str, float] = {
        "front":      garment,
        "back":       garment * 0.75,    # back less likely than front
        "brand":      label + (0.05 if ed > 14 else 0),   # brand label often sharpest
        "model_size": label,
        "material":   label,
    }

    # ── Order prior (dominant signal) ─────────────────────────────────────────
    prior_role = _ORDER_PRIOR.get(order)
    if prior_role and prior_role in scores:
        scores[prior_role] += 0.50   # strong positional prior

    return scores


def assign_roles(
    paths: list[Path],
) -> tuple[dict[str, Path | None], dict[str, float]]:
    """Assign pipeline role names to uploaded photos.

    Uses greedy assignment: for each pipeline role (in order), picks the
    highest-scoring unassigned photo.  Leftover photos become extra_01, extra_02…

    Returns:
        role_map   : {"front": Path, "brand": Path, …, "extra_01": Path, …}
        confidence : {"front": 0.85, "brand": 0.60, …}

    Missing roles are NOT included in role_map (caller should fall back to
    positional behaviour for robustness).
    """
    if not paths:
        return {}, {}

    stats_list = [_image_stats(p) for p in paths]
    score_matrix = [_score_roles(st, i) for i, st in enumerate(stats_list)]

    role_map: dict[str, Path | None] = {}
    confidence: dict[str, float] = {}
    assigned: set[int] = set()

    # Greedy: assign each pipeline role to its best unassigned candidate
    for role in PIPELINE_ROLES:
        best_idx, best_score = -1, -1.0
        for i, scores in enumerate(score_matrix):
            if i not in assigned and scores.get(role, 0.0) > best_score:
                best_score = scores[role]
                best_idx = i
        if best_idx >= 0:
            role_map[role] = paths[best_idx]
            confidence[role] = min(best_score, 1.0)
            assigned.add(best_idx)

    # Remaining photos → extras
    for j, (i, p) in enumerate(
        [(i, p) for i, p in enumerate(paths) if i not in assigned], start=1
    ):
        key = f"extra_{j:02d}"
        role_map[key] = p
        confidence[key] = 0.50

    return role_map, confidence


def low_confidence_roles(confidence: dict[str, float]) -> list[str]:
    """Return role names whose confidence is below LOW_CONFIDENCE_THRESHOLD."""
    return [
        role for role, score in confidence.items()
        if score < LOW_CONFIDENCE_THRESHOLD and not role.startswith("extra")
    ]
