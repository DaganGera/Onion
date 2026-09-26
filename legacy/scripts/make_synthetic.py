"""Procedural onion-tray generator.

WHY THIS EXISTS
---------------
Public onion datasets are small, single-bulb, and carry no calibration mat
and no size ground truth. They cannot exercise the ArUco sizing path, the
Two-Look protocol, or the lot-percentage metric -- which is most of SAMA.

This generator produces tray scenes that CAN, so every gate runs before the
first real photo exists. Real photos drop into the same YOLO layout later
and replace this entirely.

WHAT MAKES IT HONEST
--------------------
Occlusion is simulated, not assumed. Each bulb carries its defect at a
random angular position; bulbs are drawn in z-order onto an ownership mask.
A defect is OBSERVED only if enough of its patch survives overlap and faces
the camera. So:

    YOLO labels     = what a human labeller could actually see  (observed)
    groundtruth.csv = what hand-sorting the tray would find     (truth)

The gap between them is real under-detection, which is exactly what
measure_occlusion.py is supposed to discover. Shaking the tray re-randomises
rotation and stacking order, so a second look genuinely recovers defects the
first look missed.

    python scripts/make_synthetic.py --trays 120 --holdout 20
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.grading import CLASS_NAMES  # noqa: E402
from app.mat_layout import MAT_H_MM, MAT_W_MM  # noqa: E402

# --- Scene geometry ------------------------------------------------------
PX_PER_MM = 2.0
SCENE_W_MM, SCENE_H_MM = 600.0, 450.0
SCENE_W = int(SCENE_W_MM * PX_PER_MM)   # 1200
SCENE_H = int(SCENE_H_MM * PX_PER_MM)   # 900

# Onions sit ~12 mm above the mat plane, so they are nearer the camera and
# image slightly larger than the marker. calibrate_size.py must recover the
# inverse of this as height_correction (~0.94).
HEIGHT_MAGNIFICATION = 1.06

# A defect patch must keep this much of itself un-overlapped to be labelled.
DEFECT_VISIBILITY_THRESHOLD = 0.45

# Angular radius of each defect as a spherical cap on the bulb surface, in
# degrees. A bulb is a 3D object resting on the mat: a defect can simply be
# on the underside or the far side, where no camera sees it. For a cap centre
# uniform on the sphere, P(visible) = (1 + sin(alpha)) / 2.
#
# This is THE physical reason the Two-Look protocol exists. Modelling it as
# "always visible" would make measure_occlusion.py report a fake 0% and Gate
# T5 would pass on a lie.
DEFECT_CAP_DEGREES = {
    "rotten": 42.0,        # soft patches spread, easier to catch
    "sprouted": 30.0,      # a shoot at the neck can point straight down
    "black_smut": 34.0,    # localised powdery spots, easy to hide
    "damaged_skin": 38.0,
    "doubles": 68.0,       # a shape defect, visible from nearly any angle
}

DEFECT_MIX = {
    "sound": 0.70,
    "rotten": 0.09,
    "sprouted": 0.08,
    "black_smut": 0.05,
    "damaged_skin": 0.06,
    "doubles": 0.02,
}


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


# --------------------------------------------------------------------------
# Background: mat + surface
# --------------------------------------------------------------------------


_MAT_CACHE: dict[int, np.ndarray] = {}


def _mat_image(width_px: int) -> np.ndarray:
    """Render the ACTUAL printed mat, from scripts/make_mat.py.

    Using the real sheet rather than an ad-hoc pair of markers means the
    synthetic scenes exercise the same eight-marker geometry the detector
    expects. A private copy here would drift out of sync and quietly stop
    testing anything.
    """
    if width_px not in _MAT_CACHE:
        from make_mat import build_mat
        mat = np.array(build_mat())
        height_px = int(round(width_px * MAT_H_MM / MAT_W_MM))
        mat = cv2.resize(mat, (width_px, height_px), interpolation=cv2.INTER_AREA)
        _MAT_CACHE[width_px] = cv2.cvtColor(mat, cv2.COLOR_GRAY2BGR)
    return _MAT_CACHE[width_px]


def _make_background(rng: np.random.Generator) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Hessian-sack surface with the printed A4 mat laid on it."""
    # Rotate the surface the mat sits on. A model trained on one background
    # learns the background.
    surface = rng.integers(0, 4)
    base = {0: (168, 172, 178),   # hessian sack
            1: (110, 118, 126),   # concrete
            2: (74, 96, 132),     # blue tarp
            3: (140, 150, 158)}[int(surface)]
    scene = np.full((SCENE_H, SCENE_W, 3), base, np.uint8)

    noise = rng.normal(0, 9, (SCENE_H // 4, SCENE_W // 4, 3))
    noise = cv2.resize(noise, (SCENE_W, SCENE_H), interpolation=cv2.INTER_LINEAR)
    scene = np.clip(scene.astype(np.float32) + noise, 0, 255).astype(np.uint8)

    # The mat lies BESIDE the onions, not underneath them.
    #
    # A4 is 297x210 mm. The area inside the marker ring is 181x94 mm, which
    # holds about five 60 mm bulbs -- so any tray large enough to sample
    # meaningfully would bury the markers by construction. Piling onions onto
    # the mat is not a usable procedure.
    #
    # It does not need to be underneath. The homography maps the whole BENCH
    # PLANE, so a bulb resting anywhere on that plane is sized correctly as
    # long as the mat is somewhere in frame. Putting the mat to one side keeps
    # the markers clear and still measures every onion.
    mat_w = int(MAT_W_MM * PX_PER_MM)
    mat = _mat_image(mat_w)
    mat_h = mat.shape[0]

    edge = int(rng.integers(0, 4))
    if edge == 0:      # mat along the left
        mx, my = int(10 * PX_PER_MM), (SCENE_H - mat_h) // 2
    elif edge == 1:    # right
        mx, my = SCENE_W - mat_w - int(10 * PX_PER_MM), (SCENE_H - mat_h) // 2
    elif edge == 2:    # top
        mx, my = (SCENE_W - mat_w) // 2, int(8 * PX_PER_MM)
    else:              # bottom
        mx, my = (SCENE_W - mat_w) // 2, SCENE_H - mat_h - int(8 * PX_PER_MM)

    mx = int(np.clip(mx, 0, SCENE_W - mat_w))
    my = int(np.clip(my, 0, SCENE_H - mat_h))
    scene[my:my + mat_h, mx:mx + mat_w] = mat

    return scene, (mx, my, mx + mat_w, my + mat_h)


# --------------------------------------------------------------------------
# One onion
# --------------------------------------------------------------------------


def _onion_body(d_px: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Return (bgr tile, alpha mask) for a bare onion of the given size."""
    size = d_px
    tile = np.zeros((size, size, 3), np.uint8)
    mask = np.zeros((size, size), np.uint8)

    cx = cy = size // 2
    rx = int(size * 0.48)
    ry = int(size * 0.42)   # wider than tall, as onions lie in a tray

    # papery skin, warm tan through to russet
    hue = rng.integers(12, 22)
    sat = rng.integers(110, 175)
    val = rng.integers(140, 200)
    skin = cv2.cvtColor(np.uint8([[[hue, sat, val]]]), cv2.COLOR_HSV2BGR)[0][0]

    cv2.ellipse(mask, (cx, cy), (rx, ry), 0, 0, 360, 255, -1)
    tile[:] = skin

    # radial skin streaks
    for _ in range(rng.integers(9, 18)):
        angle = rng.uniform(0, np.pi)
        shade = int(rng.integers(-38, 20))
        p1 = (int(cx - rx * np.cos(angle)), int(cy - ry * np.sin(angle)))
        p2 = (int(cx + rx * np.cos(angle)), int(cy + ry * np.sin(angle)))
        colour = np.clip(skin.astype(int) + shade, 0, 255).astype(np.uint8)
        cv2.line(tile, p1, p2, colour.tolist(), max(1, size // 60))

    # spherical shading: lit from upper-left
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    shade = 1.18 - 0.5 * (((xx - cx * 0.75) ** 2 + (yy - cy * 0.75) ** 2) ** 0.5) / max(rx, 1)
    shade = np.clip(shade, 0.55, 1.25)[:, :, None]
    tile = np.clip(tile.astype(np.float32) * shade, 0, 255).astype(np.uint8)

    return tile, mask


def _defect_patch_mask(size: int, cls: str, angle: float,
                       rng: np.random.Generator,
                       foreshorten: float = 1.0) -> np.ndarray:
    """Where on the bulb the defect sits, as a mask in tile coordinates.

    `foreshorten` shrinks defects sitting near the bulb's horizon, which is
    what a curved surface does to anything not facing the camera squarely.
    """
    patch = np.zeros((size, size), np.uint8)
    cx = cy = size // 2
    size = max(6, int(size * foreshorten))
    r = size * 0.30
    px = int(cx + r * np.cos(angle))
    py = int(cy + r * np.sin(angle))

    if cls == "rotten":
        cv2.ellipse(patch, (px, py),
                    (int(size * 0.20), int(size * 0.16)),
                    float(np.degrees(angle)), 0, 360, 255, -1)
    elif cls == "sprouted":
        # shoot emerges at the neck, drawn as a slim wedge
        cv2.ellipse(patch, (px, py),
                    (int(size * 0.07), int(size * 0.20)),
                    float(np.degrees(angle)), 0, 360, 255, -1)
    elif cls == "black_smut":
        for _ in range(rng.integers(8, 16)):
            sx = int(px + rng.normal(0, size * 0.07))
            sy = int(py + rng.normal(0, size * 0.07))
            cv2.circle(patch, (sx, sy), max(1, int(size * 0.018)), 255, -1)
    elif cls == "damaged_skin":
        cv2.ellipse(patch, (px, py),
                    (int(size * 0.17), int(size * 0.12)),
                    float(np.degrees(angle)), 0, 360, 255, -1)
    elif cls == "doubles":
        cv2.ellipse(patch, (px, py),
                    (int(size * 0.22), int(size * 0.20)),
                    float(np.degrees(angle)), 0, 360, 255, -1)

    return patch


def _paint_defect(tile: np.ndarray, patch: np.ndarray, cls: str,
                  rng: np.random.Generator) -> None:
    """Colour the defect into the onion tile.

    Deliberately NOT a flat fill. The first version painted each defect as a
    uniform colour, which made every class linearly separable and drove
    holdout mAP to 0.99 -- a number that measured the renderer, not the
    detector. Real defects are textured, have soft edges, and shade
    continuously into healthy skin.

    Each defect gets:
      - a random severity, so early-stage cases sit close to the boundary
      - per-pixel texture noise
      - a feathered edge rather than a hard cut
    """
    idx = patch > 0
    if not idx.any():
        return

    # severity: how far the defect has progressed. Low values are the
    # genuinely ambiguous cases a human labeller would argue about.
    severity = float(rng.beta(2.2, 1.8))
    alpha = np.zeros(patch.shape, np.float32)
    alpha[idx] = 1.0

    # feather the boundary so there is no crisp step to latch onto
    blur = max(3, int(patch.shape[0] * 0.06) | 1)
    alpha = cv2.GaussianBlur(alpha, (blur, blur), 0)
    alpha *= 0.35 + 0.65 * severity

    # texture: real rot is mottled, smut is grainy, bruising is uneven
    texture = rng.normal(1.0, 0.16, patch.shape).astype(np.float32)
    texture = cv2.GaussianBlur(texture, (blur, blur), 0)

    if cls == "rotten":
        target = np.array([18, 26, 34], np.float32)      # dark wet brown
    elif cls == "sprouted":
        target = np.array([48, 140, 70], np.float32)     # green shoot
    elif cls == "black_smut":
        target = np.array([12, 14, 16], np.float32)
        alpha *= 0.9
    elif cls == "damaged_skin":
        target = np.array([215, 228, 236], np.float32)   # exposed flesh
    else:  # doubles -- a shape cue, barely a colour one
        target = tile.astype(np.float32).mean(axis=(0, 1)) * 0.82
        alpha *= 0.55

    a = np.clip(alpha * texture, 0.0, 1.0)[:, :, None]
    tile[:] = np.clip(tile.astype(np.float32) * (1 - a) + target * a,
                      0, 255).astype(np.uint8)


def _add_specular(tile: np.ndarray, mask: np.ndarray,
                  rng: np.random.Generator) -> None:
    """Papery onion skin throws a soft highlight. Without it every bulb is
    matte and the model never learns to ignore a bright patch."""
    size = tile.shape[0]
    spot = np.zeros((size, size), np.float32)
    cx = int(size * rng.uniform(0.30, 0.50))
    cy = int(size * rng.uniform(0.28, 0.48))
    cv2.circle(spot, (cx, cy), max(2, int(size * rng.uniform(0.10, 0.20))), 1.0, -1)
    spot = cv2.GaussianBlur(spot, (0, 0), size * 0.09) * rng.uniform(0.15, 0.42)
    spot[mask == 0] = 0
    tile[:] = np.clip(tile.astype(np.float32) + spot[:, :, None] * 255,
                      0, 255).astype(np.uint8)


# --------------------------------------------------------------------------
# Tray assembly
# --------------------------------------------------------------------------


def _sample_diameter(rng: np.random.Generator) -> float:
    """Realistic bulb size spread, in mm, across the ICAR-DOGR bands."""
    return float(np.clip(rng.normal(62.0, 15.0), 26.0, 98.0))


def _sample_class(rng: np.random.Generator, forced: str | None) -> str:
    if forced is not None:
        return forced
    names = list(DEFECT_MIX)
    weights = np.array([DEFECT_MIX[n] for n in names], float)
    return str(rng.choice(names, p=weights / weights.sum()))


def make_roster(seed: int, n_onions: int,
                forced_class: str | None = None) -> list[dict]:
    """The physical onions in a tray: size and true condition.

    Created once per tray and reused for BOTH looks. Shaking a tray re-seats
    the onions that are in it; it does not swap them for different onions.
    Regenerating them per look would make the two looks describe different
    lots, and every two-look metric measured against one ground truth would
    be meaningless.
    """
    rng = _rng(seed)
    return [
        {"d_mm": _sample_diameter(rng), "cls": _sample_class(rng, forced_class)}
        for _ in range(n_onions)
    ]


def render_tray(seed: int, roster: list[dict],
                spill: float = 0.30) -> tuple[np.ndarray, list[dict]]:
    """Photograph a tray of known onions. Returns (image, per-bulb records).

    `seed` controls only the ARRANGEMENT -- position, stacking order, and
    which face of each bulb points at the camera. Same roster + different
    seed = the same tray after a shake.

    `spill` is how far onions scatter from the mat centre, as a fraction of
    the mat's size. Raise it to stress the calibration fallbacks; the default
    reproduces a tray tipped roughly where the operator was told to tip it.

    Each record carries both `true_cls` (what hand-sorting finds) and
    `observed_cls` (what is visible to a camera and therefore labellable).
    """
    rng = _rng(seed)
    scene, mat_rect = _make_background(rng)
    owner = np.full((SCENE_H, SCENE_W), -1, np.int32)

    margin = int(35 * PX_PER_MM)
    records: list[dict] = []
    placed: list[tuple[int, int, int]] = []

    # NO marker keep-out. The first version of this generator forbade onions
    # from ever touching a marker, which made every calibration number
    # optimistic by construction -- the failure the eight-marker mat exists
    # to survive could not occur in the test set. Onions now land where they
    # land, and bury markers exactly as they do on a real procurement bench.

    for i, onion in enumerate(roster):
        d_mm = onion["d_mm"]
        d_px = int(round(d_mm * PX_PER_MM * HEIGHT_MAGNIFICATION))
        cls = onion["cls"]

        # Pack tightly -- crowding is what creates the occlusion the Two-Look
        # protocol exists to beat.
        #
        # Placement is biased toward the mat CENTRE rather than uniform over
        # the frame. An operator tips a tray onto the middle of the mat, and
        # the mat itself prints "keep onions off the marker border". Uniform
        # placement buried 7 of 8 markers on average, which is a worst case,
        # not a working bench -- training on it would teach the model that
        # calibration usually fails. The tails still spill onto the border,
        # so markers are lost often enough to exercise every fallback rung.
        mx0, my0, mx1, my1 = mat_rect
        # Aim the pile at the bench area the mat does NOT occupy, pushed away
        # from the mat's centre. Tails still land on the mat, so markers get
        # buried often enough to keep the fallback rungs honest.
        scene_cx, scene_cy = SCENE_W / 2.0, SCENE_H / 2.0
        mat_cx, mat_cy = (mx0 + mx1) / 2.0, (my0 + my1) / 2.0
        push_x, push_y = scene_cx - mat_cx, scene_cy - mat_cy
        norm = max(1.0, float(np.hypot(push_x, push_y)))
        pile_cx = scene_cx + push_x / norm * (mx1 - mx0) * 0.28
        pile_cy = scene_cy + push_y / norm * (my1 - my0) * 0.28
        mat_cx, mat_cy = pile_cx, pile_cy
        spread_x, spread_y = SCENE_W * spill * 0.55, SCENE_H * spill * 0.55

        for _ in range(80):
            cx = int(np.clip(rng.normal(mat_cx, spread_x), margin, SCENE_W - margin))
            cy = int(np.clip(rng.normal(mat_cy, spread_y), margin, SCENE_H - margin))
            if all((cx - ox) ** 2 + (cy - oy) ** 2 > (0.42 * (d_px + od)) ** 2
                   for ox, oy, od in placed):
                break
        else:
            continue

        tile, mask = _onion_body(d_px, rng)
        angle = rng.uniform(0, 2 * np.pi)

        # --- is the defect even facing the camera? -----------------------
        # Place the defect's cap centre uniformly on the bulb's surface.
        # cos_polar > 0 means it faces the camera; the cap's angular radius
        # lets a defect near the horizon still peek over the edge.
        patch = np.zeros((d_px, d_px), np.uint8)
        faces_camera = True
        if cls != "sound":
            cos_polar = float(rng.uniform(-1.0, 1.0))
            sin_alpha = float(np.sin(np.radians(DEFECT_CAP_DEGREES[cls])))
            faces_camera = cos_polar > -sin_alpha

            if faces_camera:
                # foreshorten defects sitting near the rim
                foreshorten = float(np.clip(abs(cos_polar) ** 0.5, 0.35, 1.0))
                patch = _defect_patch_mask(d_px, cls, angle, rng, foreshorten)
                patch = cv2.bitwise_and(patch, mask)
                _paint_defect(tile, patch, cls, rng)

        x0, y0 = cx - d_px // 2, cy - d_px // 2
        x1, y1 = x0 + d_px, y0 + d_px
        if x0 < 0 or y0 < 0 or x1 > SCENE_W or y1 > SCENE_H:
            continue

        _add_specular(tile, mask, rng)

        # Contact shadow. This is a HARD NEGATIVE on purpose: the dark patch
        # where two bulbs touch looks a great deal like early rot, and a model
        # never shown one will call it rot on a real market bench.
        shadow = cv2.GaussianBlur((mask > 0).astype(np.float32), (0, 0), d_px * 0.10)
        sx0, sy0 = x0 + int(d_px * 0.07), y0 + int(d_px * 0.09)
        sx1, sy1 = min(SCENE_W, sx0 + d_px), min(SCENE_H, sy0 + d_px)
        if sx1 > sx0 and sy1 > sy0:
            region = scene[sy0:sy1, sx0:sx1].astype(np.float32)
            sh = shadow[:sy1 - sy0, :sx1 - sx0][:, :, None] * rng.uniform(0.18, 0.38)
            scene[sy0:sy1, sx0:sx1] = np.clip(region * (1 - sh), 0, 255).astype(np.uint8)

        roi = scene[y0:y1, x0:x1]
        idx = mask > 0
        roi[idx] = tile[idx]
        owner[y0:y1, x0:x1][idx] = i     # later onions overwrite earlier ones

        placed.append((cx, cy, d_px))
        records.append({
            "index": i,
            "true_cls": cls,
            "faces_camera": faces_camera,
            "true_diameter_mm": round(d_mm, 2),
            "bbox": (x0, y0, x1, y1),
            "patch": patch,
            "patch_origin": (x0, y0),
            "d_px": d_px,
        })

    # --- resolve what is actually visible after stacking -------------------
    for rec in records:
        i = rec["index"]
        x0, y0, x1, y1 = rec["bbox"]
        body_visible = float((owner[y0:y1, x0:x1] == i).sum())

        if rec["true_cls"] == "sound":
            rec["observed_cls"] = "sound"
        elif not rec["faces_camera"]:
            # on the underside or far side -- no camera angle recovers it,
            # only shaking the tray does
            rec["observed_cls"] = "sound"
        else:
            patch = rec["patch"]
            total = float(patch.sum() / 255.0)
            if total <= 0:
                rec["observed_cls"] = "sound"
            else:
                own = (owner[y0:y1, x0:x1] == i) & (patch > 0)
                visible_fraction = float(own.sum()) / total
                rec["observed_cls"] = (
                    rec["true_cls"]
                    if visible_fraction >= DEFECT_VISIBILITY_THRESHOLD
                    else "sound"
                )

        rec["visible_px"] = body_visible
        rec.pop("patch")

    # bulbs almost entirely buried are not labellable at all
    records = [r for r in records
               if r["visible_px"] > 0.30 * np.pi * (r["d_px"] / 2) ** 2]

    scene = _apply_capture_effects(scene, _rng(seed + 7717))
    return scene, records


def _apply_capture_effects(scene: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Lighting gradient, white balance drift, blur and sensor noise.

    Without this the model learns a clean synthetic prior and collapses on
    the first real phone photo.
    """
    h, w = scene.shape[:2]

    # directional lighting gradient
    gx = rng.uniform(-0.30, 0.30)
    gy = rng.uniform(-0.30, 0.30)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    grad = 1.0 + gx * (xx / w - 0.5) * 2 + gy * (yy / h - 0.5) * 2
    scene = scene.astype(np.float32) * grad[:, :, None]

    # white balance drift between phones and between sun and shade
    scene *= np.array([rng.uniform(0.90, 1.12),
                       rng.uniform(0.94, 1.06),
                       rng.uniform(0.90, 1.12)], np.float32)

    scene = np.clip(scene, 0, 255).astype(np.uint8)

    if rng.random() < 0.5:
        k = int(rng.choice([3, 5]))
        scene = cv2.GaussianBlur(scene, (k, k), 0)

    noise = rng.normal(0, rng.uniform(2.0, 7.0), scene.shape)
    scene = np.clip(scene.astype(np.float32) + noise, 0, 255).astype(np.uint8)

    # JPEG compression artefacts, as any phone would introduce
    ok, buf = cv2.imencode(".jpg", scene,
                           [int(cv2.IMWRITE_JPEG_QUALITY), int(rng.integers(72, 94))])
    if ok:
        scene = cv2.imdecode(buf, cv2.IMREAD_COLOR)

    return scene


# --------------------------------------------------------------------------
# Dataset writing
# --------------------------------------------------------------------------


def _write_yolo_label(path: Path, records: list[dict]) -> None:
    lines = []
    for rec in records:
        x0, y0, x1, y1 = rec["bbox"]
        cx = (x0 + x1) / 2 / SCENE_W
        cy = (y0 + y1) / 2 / SCENE_H
        bw = (x1 - x0) / SCENE_W
        bh = (y1 - y0) / SCENE_H
        cls_idx = CLASS_NAMES.index(rec["observed_cls"])
        lines.append(f"{cls_idx} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build(out_root: Path, n_trays: int, n_holdout: int, seed: int) -> None:
    dataset = out_root / "dataset"
    holdout = out_root / "holdout"
    for path in (dataset, holdout):
        if path.exists():
            shutil.rmtree(path)

    splits = {"train": 0.70, "valid": 0.20, "test": 0.10}
    for split in splits:
        (dataset / split / "images").mkdir(parents=True, exist_ok=True)
        (dataset / split / "labels").mkdir(parents=True, exist_ok=True)
    (holdout / "images").mkdir(parents=True, exist_ok=True)
    (holdout / "labels").mkdir(parents=True, exist_ok=True)

    rng = _rng(seed)
    gt_rows: list[dict] = []
    caliper_rows: list[dict] = []

    # Single-class trays first, mirroring the real shooting protocol: they
    # give the model clean examples of each defect before it sees mixtures.
    plan: list[tuple[str | None, bool]] = []
    for cls in ("rotten", "sprouted", "black_smut", "damaged_skin"):
        plan += [(cls, False)] * max(1, int(n_trays * 0.06))
    while len(plan) < n_trays:
        plan.append((None, False))

    order = rng.permutation(len(plan))
    plan = [plan[i] for i in order]

    for t, (forced, _) in enumerate(plan):
        n_onions = int(rng.integers(30, 46))
        base_seed = seed * 1000 + t
        roster = make_roster(base_seed, n_onions, forced_class=forced)

        # Same onions, two arrangements. The seed offset changes only how they
        # are stacked and which face is up -- exactly what a shake does.
        # Some operators are tidy, some tip the whole crate on. Vary it.
        spill = float(rng.uniform(0.22, 0.42))
        for look in (0, 1):
            img, records = render_tray(base_seed + look * 500_000, roster, spill)
            if not records:
                continue

            r = rng.random()
            split = "train" if r < 0.70 else ("valid" if r < 0.90 else "test")
            stem = f"tray{t:04d}_look{look}"

            cv2.imwrite(str(dataset / split / "images" / f"{stem}.jpg"), img)
            _write_yolo_label(dataset / split / "labels" / f"{stem}.txt", records)

            if look == 0:
                truth = {c: 0 for c in CLASS_NAMES}
                grades = {"A": 0, "B": 0, "C": 0, "UNDERSIZED": 0}
                for rec in records:
                    truth[rec["true_cls"]] += 1
                    d = rec["true_diameter_mm"]
                    grades["A" if d >= 80 else "B" if d >= 50 else "C" if d >= 30
                           else "UNDERSIZED"] += 1
                gt_rows.append({
                    "tray_id": f"tray{t:04d}",
                    "composition": "single_class" if forced else "mixed",
                    "n_total": len(records),
                    "n_sound": truth["sound"],
                    "n_rotten": truth["rotten"],
                    "n_sprouted": truth["sprouted"],
                    "n_smut": truth["black_smut"],
                    "n_damaged": truth["damaged_skin"],
                    "n_doubles": truth["doubles"],
                    "n_grade_A": grades["A"],
                    "n_grade_B": grades["B"],
                    "n_grade_C": grades["C"],
                    "n_undersized": grades["UNDERSIZED"],
                })
                # stand-in for caliper measurements on a subset of bulbs
                for rec in records[:2]:
                    caliper_rows.append({
                        "onion_id": f"tray{t:04d}_b{rec['index']:02d}",
                        "tray_id": f"tray{t:04d}",
                        "caliper_mm": rec["true_diameter_mm"],
                        "bbox_x0": rec["bbox"][0], "bbox_y0": rec["bbox"][1],
                        "bbox_x1": rec["bbox"][2], "bbox_y1": rec["bbox"][3],
                        "image": f"tray{t:04d}_look0.jpg",
                    })

    # --- holdout: different "day", shot last, never trained on -------------
    for h in range(n_holdout):
        holdout_seed = seed * 77_000 + h
        img, records = render_tray(
            holdout_seed, make_roster(holdout_seed, int(rng.integers(30, 46))))
        if not records:
            continue
        stem = f"holdout{h:03d}"
        cv2.imwrite(str(holdout / "images" / f"{stem}.jpg"), img)
        _write_yolo_label(holdout / "labels" / f"{stem}.txt", records)

    _write_data_yaml(dataset)
    _write_csv(out_root / "groundtruth.csv", gt_rows)
    _write_csv(out_root / "caliper.csv", caliper_rows)

    counts = {s: len(list((dataset / s / "images").glob("*.jpg"))) for s in splits}
    print("Synthetic dataset written")
    print(f"  train/valid/test : {counts['train']} / {counts['valid']} / {counts['test']}")
    print(f"  holdout          : {len(list((holdout / 'images').glob('*.jpg')))}")
    print(f"  groundtruth rows : {len(gt_rows)}")
    print(f"  caliper rows     : {len(caliper_rows)}")
    print(f"  scene            : {SCENE_W}x{SCENE_H} px at {PX_PER_MM} px/mm")
    print(f"  built-in magnification: {HEIGHT_MAGNIFICATION} "
          f"(calibrate_size.py should recover ~{1/HEIGHT_MAGNIFICATION:.3f})")


def _write_data_yaml(dataset: Path) -> None:
    names = "\n".join(f"  {i}: {n}" for i, n in enumerate(CLASS_NAMES))
    (dataset / "data.yaml").write_text(
        f"path: {dataset.resolve().as_posix()}\n"
        "train: train/images\n"
        "val: valid/images\n"
        "test: test/images\n\n"
        f"nc: {len(CLASS_NAMES)}\n"
        f"names:\n{names}\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trays", type=int, default=120)
    ap.add_argument("--holdout", type=int, default=20)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", type=Path, default=Path("data"))
    args = ap.parse_args()

    build(args.out, args.trays, args.holdout, args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
