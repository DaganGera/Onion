"""SAMA server. Serves the UI and the inference API from one process.

    uvicorn app.main:app --host 0.0.0.0 --port 8000

One process on purpose: one thing to start, one thing to restart, one log to
read when it breaks on demo day in front of judges.
"""

from __future__ import annotations

import base64
import html as html_mod
import io
import json
import sqlite3
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, Form, UploadFile, File, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import db, grading
from app import arbitration
from app import capture_quality
from app import evidence as evidence_mod
from app import twin
# Aliased, not bare: /analyze has a local variable named `scale`, and a bare
# `from app import scale` would shadow-trap it (UnboundLocalError waiting to
# happen on the next edit).
from app import scale as scale_mod

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).parent / "static"
CACHE = Path(__file__).parent / "cache"
WEIGHTS = ROOT / "weights" / "best.pt"
# Detector-calibration measurement written by scripts/eval_calibration.py.
# Read-only here: the app reports calibration, it never runs inference for it.
CALIBRATION_REPORT = ROOT / "runs" / "report" / "calibration.json"

app = FastAPI(title="SAMA")

# Mount at /static, never at "/". Mounting at root shadows every API route.
STATIC.mkdir(parents=True, exist_ok=True)
CACHE.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

# --- model, loaded ONCE ---------------------------------------------------
MODEL = None
MODEL_ERROR: str | None = None
E2E_MODE = bool(grading.CONSTANTS.get("e2e_mode", False))

# Last successful scale per lot reference, for the carried-scale fallback.
# Deliberately tiny and in-process: it is a within-lot convenience, not state
# worth persisting, and it must not grow without bound on demo day.
# QA LOOP-Q2260: every request thread touches this dict, so all access is
# serialised. Without the lock, two concurrent /analyze uploads could both
# pick the same eviction victim via next(iter(...)) -- the loser's pop()
# raised KeyError and the officer's photo came back as a 500.
_LAST_GOOD_SCALE: dict[str, grading.ScaleResult] = {}
_MAX_REMEMBERED_LOTS = 32
_SCALE_CACHE_LOCK = threading.Lock()


def _remember_scale(lot_ref: str, scale) -> None:
    with _SCALE_CACHE_LOCK:
        # Updating an entry we already hold must not evict a neighbour to
        # make room we already have (Q2260): that would drop a good carried
        # scale for an unrelated lot mid-session.
        if (len(_LAST_GOOD_SCALE) >= _MAX_REMEMBERED_LOTS
                and lot_ref not in _LAST_GOOD_SCALE):
            _LAST_GOOD_SCALE.pop(next(iter(_LAST_GOOD_SCALE)))
        _LAST_GOOD_SCALE[lot_ref] = scale


def _carried_scale(lot_ref: str):
    """Snapshot read of the carried-scale cache under the same lock."""
    with _SCALE_CACHE_LOCK:
        return _LAST_GOOD_SCALE.get(lot_ref)


BOX_COLOURS = {
    "accept_sound": (72, 160, 72),
    "accept_defect": (48, 48, 210),
    "refer": (16, 165, 216),
}


def _load_model():
    """Load weights at import. A missing model must not crash the server --
    replay mode still has to work when the venue laptop has no weights."""
    global MODEL, MODEL_ERROR
    if not WEIGHTS.exists():
        MODEL_ERROR = f"weights not found at {WEIGHTS}"
        print(f"WARNING: {MODEL_ERROR} -- /analyze will fail, replay still works.")
        return
    try:
        from ultralytics import YOLO
        MODEL = YOLO(str(WEIGHTS))
        print(f"Loaded {WEIGHTS} (end2end={E2E_MODE})")
    except Exception as exc:  # noqa: BLE001
        MODEL_ERROR = f"{type(exc).__name__}: {exc}"
        print(f"WARNING: could not load model -- {MODEL_ERROR}")


_load_model()
db.init_db()


def _error(message: str, status: int = 400) -> JSONResponse:
    """Every failure leaves as JSON. Never a raw stack trace to a phone."""
    return JSONResponse({"error": message}, status_code=status)


# --- global catch-alls ------------------------------------------------------
# Belt and braces under the per-endpoint try/excepts. If anything slips past
# them, these guarantee a JSON body in the _error() shape instead of a raw
# 500 or Starlette's plain-text default. Details go to the console log, not
# to the client.


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    return _error("Internal server error. Please retry.", 500)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Unmatched routes and abort()s arrive here, not as plain text."""
    return _error(str(exc.detail), status=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """FastAPI's default 422 uses a 'detail' key the frontend never reads."""
    try:
        first = exc.errors()[0]
        where = ".".join(str(v) for v in first.get("loc", []))
        message = f"Invalid request: {first.get('msg', 'bad input')}"
        if where:
            message += f" ({where})"
    except Exception:  # noqa: BLE001 -- never let the error path itself fail
        message = "Invalid request."
    return _error(message, 422)


def _error_page(message: str, status: int = 500) -> HTMLResponse:
    """Last-resort page for browser-facing routes. Readable on a phone,
    never a traceback."""
    return HTMLResponse(
        "<h1>SAMA</h1>"
        f"<p>{html_mod.escape(message)}</p>"
        '<p><a href="/">Back to home</a></p>',
        status_code=status,
    )


def _json_for_script(obj) -> str:
    """JSON that is safe to inline inside a <script> block.

    QA LOOP-Q2216: certificate payloads reached the report/verify pages as
    raw json.dumps output inside a <script> element. A farmer_name holding
    '</script>' closed that element early and let arbitrary markup run on
    the PUBLIC trust surface. Escaping < > & makes breakout impossible while
    staying byte-equivalent for every JSON/JS parser (they read \\u003c as
    '<' inside string literals). U+2028/U+2029 are escaped for pre-ES2019
    WebViews -- cheap Androids are exactly this product's audience.
    ensure_ascii=False keeps real names human-readable in page source.
    """
    text = json.dumps(obj, default=str, ensure_ascii=False)
    return (text.replace("&", "\\u0026")
                .replace("<", "\\u003c")
                .replace(">", "\\u003e")
                .replace("\u2028", "\\u2028")
                .replace("\u2029", "\\u2029"))


def _serve(name: str) -> HTMLResponse:
    path = STATIC / name
    if not path.exists():
        return _error_page(f"Page {name} is missing on this machine.", 404)
    try:
        return HTMLResponse(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- unreadable file must still answer
        traceback.print_exc()
        return _error_page(f"Could not load {name}. Try refreshing; if it "
                           "persists, restart the server.", 503)


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return _serve("index.html")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return _serve("dashboard.html")


def _qr_data_uri(text: str) -> str:
    """QR code as a base64 PNG the certificate can embed directly.

    Optional dependency: if qrcode is not installed the certificate simply
    ships without one rather than failing the request.
    """
    try:
        import qrcode
        img = qrcode.make(text, box_size=6, border=2)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: QR generation failed -- {type(exc).__name__}: {exc}")
        return ""


@app.get("/report/{lot_id}", response_class=HTMLResponse)
def report(lot_id: int, request: Request) -> HTMLResponse:
    lot = db.get_lot(lot_id)
    if lot is None:
        return HTMLResponse("<h1>Lot not found</h1>", status_code=404)

    path = STATIC / "report.html"
    if not path.exists():
        return _error_page("report.html is missing on this machine.", 404)

    # The QR must survive being scanned off a phone screen in a market, so it
    # carries an absolute URL. Over the cloudflared tunnel that is the public
    # HTTPS address; on localhost it degrades to the LAN URL, which still
    # works for anyone on the same bench network.
    verify_url = str(request.base_url).rstrip("/") + f"/verify/{lot_id}"
    try:
        # RT-001 T-7: swap stored manifest paths for fresh data URIs read
        # from disk now, so #shots finally shows the annotated trays. A
        # missing/unreadable image drops out of the gallery; the page never
        # fails over photographs.
        lot["evidence"] = evidence_mod.page_views(lot.get("evidence") or [])
        payload = _json_for_script(lot)
        page = path.read_text(encoding="utf-8").replace(
            '"__LOT_DATA__"', payload
        ).replace(
            "__VERIFY_URL__", verify_url
        ).replace(
            "__QR_DATA__", _qr_data_uri(verify_url) or ""
        )
    except Exception:  # noqa: BLE001 -- a broken template must still answer
        traceback.print_exc()
        return _error_page(f"The certificate page for lot {lot_id} could "
                           "not be built. Try again.", 503)
    return HTMLResponse(page)


# --------------------------------------------------------------------------
# Inference
# --------------------------------------------------------------------------


ANNOTATED_MAX_WIDTH = 1280
ANNOTATED_JPEG_QUALITY = 82

# QA LOOP-Q2216: upload ceiling and decode ceiling for /analyze.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024      # 25 MB wire cap per photo
UPLOAD_CHUNK_BYTES = 1024 * 1024         # read in 1 MB chunks
MAX_IMAGE_PIXELS = 40_000_000            # ~40 MP decoded-frame ceiling

# QA LOOP-Q2260: lot_ref becomes a _LAST_GOOD_SCALE key -- an unbounded
# client string parked ~800 MB of RAM across the 32 cache slots under a
# probe loop. The lot_ref cap mirrors /finalize's signed-record limit;
# tray_id only labels trays.
ANALYZE_MAX_LOT_REF = 120
ANALYZE_MAX_TRAY_ID = 64


def _annotate(image: np.ndarray, bulbs: list[dict]) -> str:
    """Draw boxes and return a base64 JPEG the phone can display directly.

    JPEG, not PNG, and capped at 1280 px wide. A full-resolution PNG of a
    tray runs ~2 MB, and base64 adds another third on top -- two looks would
    push 5 MB down a market-wifi tunnel before the officer sees anything.
    Boxes and a millimetre label survive this compression fine.
    """
    canvas = image.copy()

    scale_factor = 1.0
    if canvas.shape[1] > ANNOTATED_MAX_WIDTH:
        scale_factor = ANNOTATED_MAX_WIDTH / canvas.shape[1]
        canvas = cv2.resize(canvas, None, fx=scale_factor, fy=scale_factor,
                            interpolation=cv2.INTER_AREA)

    thickness = max(2, int(min(canvas.shape[:2]) / 300))

    for bulb in bulbs:
        # bboxes are in ORIGINAL image coordinates; scale them to match
        x0, y0, x1, y1 = (int(v * scale_factor) for v in bulb["bbox"])
        if bulb["decision"] == "REFER":
            colour = BOX_COLOURS["refer"]
        elif bulb["cls_name"] == "sound":
            colour = BOX_COLOURS["accept_sound"]
        else:
            colour = BOX_COLOURS["accept_defect"]

        cv2.rectangle(canvas, (x0, y0), (x1, y1), colour, thickness)

        if bulb.get("diameter_mm"):
            label = f"{bulb['diameter_mm']:.0f}mm"
            scale = max(0.4, min(canvas.shape[:2]) / 1400)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
            cv2.rectangle(canvas, (x0, y0 - th - 6), (x0 + tw + 4, y0), colour, -1)
            cv2.putText(canvas, label, (x0 + 2, y0 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), 1, cv2.LINE_AA)

    ok, buf = cv2.imencode(".jpg", canvas,
                           [int(cv2.IMWRITE_JPEG_QUALITY), ANNOTATED_JPEG_QUALITY])
    if not ok:
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


@app.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    lot_ref: str = Form(""),
    look_index: int = Form(0),
    tray_id: str = Form("T1"),
):
    try:
        # QA LOOP-Q2260: cheap field caps FIRST -- before the upload is read
        # a single byte. Over-limit lot_ref/tray_id would otherwise be
        # echoed, cached as carried-scale keys (lot_ref), or stored on
        # bulbs; refuse with field and limit named.
        if len(lot_ref) > ANALYZE_MAX_LOT_REF:
            return _error(f"lot_ref too long ({len(lot_ref)} characters, "
                          f"limit {ANALYZE_MAX_LOT_REF}). Shorten it and retry.")
        if len(tray_id) > ANALYZE_MAX_TRAY_ID:
            return _error(f"tray_id too long ({len(tray_id)} characters, "
                          f"limit {ANALYZE_MAX_TRAY_ID}). Shorten it and retry.")

        # RT-001 D-1: on a machine with plain opencv-python there is no
        # cv2.aruco at all. Import no longer dies (guarded in app/scale.py);
        # capture alone degrades, loudly, while pages/replay/dashboard/verify
        # keep serving. Fail before reading the upload -- nothing downstream
        # can proceed without a calibration module.
        if scale_mod.get_detector() is None:
            return _error("calibration module unavailable -- install "
                          "opencv-contrib-python (cv2.aruco is missing). "
                          "Replay mode still works: add ?replay=1.", 503)

        if MODEL is None:
            return _error(f"Model unavailable ({MODEL_ERROR}). "
                          "Use replay mode: add ?replay=1 to the URL.", 503)

        raw = bytearray()
        # QA LOOP-Q2216: bounded read. file.read() used to slurp the whole
        # upload into RAM unbounded -- a curl probe or a wedged client retry
        # loop could hand the venue laptop gigabytes. Starlette spools the
        # request body to disk, so this loop decides how much ever lands in
        # memory. Real tray photos land at 2-8 MB after the phone's own
        # downscale (see tests/test_upload_downscale.py).
        while True:
            chunk = await file.read(UPLOAD_CHUNK_BYTES)
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > MAX_UPLOAD_BYTES:
                mb = MAX_UPLOAD_BYTES // (1024 * 1024)
                return _error(
                    f"Photo exceeds the {mb} MB upload limit. Retake at a "
                    "lower resolution -- the SAMA capture button compresses "
                    "automatically -- and try again.", 413)
        raw = bytes(raw)
        if not raw:
            return _error("Empty upload. Try taking the photo again.")

        image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return _error("Could not read that image. Try again.")

        # QA LOOP-Q2216: pixel-bomb guard. A small FILE can decode into a
        # huge frame -- a ~100 MP JPEG costs hundreds of MB of RAM exactly
        # when two phones are already waiting on the model. Downscale, do
        # not refuse: a valid wide shot of a tray still grades fine, and
        # the response announces the resize instead of hiding it.
        resized_from = None
        height, width = image.shape[:2]
        if height * width > MAX_IMAGE_PIXELS:
            shrink = (MAX_IMAGE_PIXELS / float(height * width)) ** 0.5
            image = cv2.resize(image, None, fx=shrink, fy=shrink,
                               interpolation=cv2.INTER_AREA)
            resized_from = [width, height]

        # Edge-case guard (untested field condition): a godown-after-dusk or
        # flash-blown frame decodes fine, passes every upstream check, and
        # would otherwise reach the detector -- which happily emits boxes on
        # noise. Refuse the unusable; annotate the merely imperfect.
        quality = capture_quality.assess_capture_quality(image)
        if quality.get("blocked"):
            return _error(capture_quality.rejection_message(quality), 422)

        started = time.perf_counter()
        # Reuse this lot's last good scale if every marker is buried in THIS
        # photo. The mat and the phone barely move between two looks at one
        # tray, so a carried scale beats reporting no sizes at all.
        scale = grading.detect_scale(image, carried=_carried_scale(lot_ref))
        if scale.calibrated and scale.source != "carried":
            _remember_scale(lot_ref, scale)

        result = MODEL.predict(image, conf=0.25, verbose=False,
                               end2end=E2E_MODE, max_det=300)[0]

        bulbs: list[dict] = []
        if result.boxes is not None:
            for bbox, cls, conf in zip(result.boxes.xyxy.cpu().numpy(),
                                       result.boxes.cls.cpu().numpy(),
                                       result.boxes.conf.cpu().numpy()):
                cls_idx = int(cls)
                cls_name = (grading.CLASS_NAMES[cls_idx]
                            if cls_idx < len(grading.CLASS_NAMES) else "sound")
                diameter = grading.bulb_diameter_mm(bbox, scale)
                bulbs.append({
                    "bbox": [float(v) for v in bbox],
                    "cls": cls_idx,
                    "cls_name": cls_name,
                    "confidence": round(float(conf), 4),
                    "diameter_mm": round(diameter, 1) if diameter else None,
                    "size_grade": grading.size_grade(diameter),
                    "decision": grading.decide(float(conf)),
                    "tray_id": tray_id,
                })

        elapsed_ms = (time.perf_counter() - started) * 1000

        return {
            "lot_ref": lot_ref,
            "look_index": look_index,
            "tray_id": tray_id,
            "bulbs": bulbs,
            "n_bulbs": len(bulbs),
            "scale": scale.to_dict(),
            "quality": quality,
            "annotated": _annotate(image, bulbs),
            "annotated_scale": (ANNOTATED_MAX_WIDTH / image.shape[1]
                                if image.shape[1] > ANNOTATED_MAX_WIDTH else 1.0),
            "elapsed_ms": round(elapsed_ms, 1),
            # Present only when the decode was oversized and got shrunk.
            **({"resized_from": resized_from} if resized_from else {}),
        }
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return _error(f"Analysis failed: {type(exc).__name__}", 500)


# --------------------------------------------------------------------------
# Finalisation -- text hygiene and timestamp trust
# --------------------------------------------------------------------------

# C0 control bytes + DEL never belong in a person's name. Tab/newline/CR
# survive (harmless, occasionally meaningful); NUL especially must go,
# because every C-string consumer of the database truncates at it.
_CONTROL_CODEPOINTS = frozenset(range(0x20)) - {0x09, 0x0A, 0x0D} | {0x7F}


def _clean_text(value, field: str, max_len: int) -> str:
    """Sanitise one free-text field destined for a signed record.

    QA LOOP-Q2216 policy:
      * control bytes are stripped -- transport junk, not content;
      * anything unencodable to UTF-8 (lone surrogates arrive intact through
        json.loads) raises 400 naming the field;
      * over-limit input raises 400 naming field and limit -- silently
        truncating would ALTER a signed record without trace.
    """
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        raise ValueError(f"{field}: expected text.")
    cleaned = "".join(ch for ch in value if ord(ch) not in _CONTROL_CODEPOINTS)
    try:
        cleaned.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError(
            f"{field}: contains a character that cannot be stored "
            "(invalid encoding). Remove unusual symbols and retry."
        ) from None
    if len(cleaned) > max_len:
        raise ValueError(
            f"{field}: too long ({len(cleaned)} characters, limit {max_len})."
        )
    return cleaned.strip()


# A phone with a wrong clock may still take perfect photos; its TIMESTAMP,
# though, goes onto a certificate used in arbitration. Anything further from
# server time than this window loses its vote.
CLOCK_SKEW_TOLERANCE = timedelta(hours=24)


def _validated_centre_id(raw) -> tuple[int | None, str | None]:
    """Vet a client-supplied centre id. Returns (id_or_None, error_or_None).

    QA LOOP-Q2260: this field used to go straight through int(). "abc"
    raised ValueError -> generic 500; worse, a well-typed NONEXISTENT id
    passed and -- foreign keys being off -- minted a lot row whose centre
    JOIN matches nothing, so get_lot/report/verify/recent_lots all answered
    'no such certificate' for a record the ledger provably held.

    Accepted shapes follow what real callers send:
      * int                      -- API scripts;
      * numeric STRING           -- the shipped UI (<option value> is text);
      * integral float           -- JS-number clients;
    Everything else, non-positive ids, and ids with no centres row are
    refused BEFORE anything is written.
    """
    if isinstance(raw, bool):          # bool is an int subclass; not an id
        return None, ("centre_id must be a centre id from /api/centres "
                      "(got true/false).")
    if isinstance(raw, float):
        if not raw.is_integer():
            return None, f"centre_id {raw} is not a whole centre id."
        raw = int(raw)
    if isinstance(raw, str):
        try:
            raw = int(raw.strip())
        except ValueError:
            return None, (f"centre_id {raw!r} is not a centre id. Pick the "
                          "centre again from the list (or clear it to file "
                          "under a name).")
    if not isinstance(raw, int):
        return None, ("centre_id must be a centre id from /api/centres "
                      "(a number or numeric string).")
    if raw <= 0:
        return None, f"centre_id {raw} is not a valid centre id."
    if not db.centre_exists(raw):
        return None, (f"centre_id {raw} does not exist on this server. "
                      "Re-pick the centre from the list -- or clear it to "
                      "file under a centre name.")
    return raw, None


def _trusted_created_at(raw) -> tuple[str | None, str | None]:
    """Vet a client-supplied timestamp for a certificate.

    Returns (created_at_or_None, override_reason_or_None). None means "use
    server time" -- which is also what an absent field gets, so the normal
    frontend path stays flag-free; only PROVIDED-but-rejected values earn an
    override reason, which the response reports back honestly.
    """
    if raw is None:
        return None, None
    if not isinstance(raw, str) or not raw.strip():
        return None, "client timestamp was not usable text"
    try:
        parsed = datetime.fromisoformat(raw.strip())
    except ValueError:
        return None, "client timestamp was unreadable"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    skew = abs(parsed - datetime.now(timezone.utc))
    if skew > CLOCK_SKEW_TOLERANCE:
        hours = CLOCK_SKEW_TOLERANCE.total_seconds() / 3600
        return None, f"client clock off by more than {hours:.0f} h"
    return raw.strip(), None


@app.post("/finalize")
async def finalize(payload: dict):
    try:
        looks = payload.get("looks") or []
        if not looks:
            return _error("No looks captured. Photograph at least one tray.")

        # QA LOOP-Q2260: merge_looks() assumes a list of per-look lists of
        # bulb objects. A dict, a bare string, or scalar entries used to
        # explode inside it as AttributeError/TypeError -- a caller mistake
        # surfacing as the generic 500 'Could not save lot'. Validate the
        # SHAPE here so every rejection names where it broke.
        if not isinstance(looks, list):
            return _error("looks must be a list -- one list of bulb "
                          "detections per photo.", 400)
        for i, look in enumerate(looks):
            # A null look slot is LEGAL (tests/test_dispute_flow.py:
            # 'merge_looks tolerates null entries') -- it stands for a
            # skipped/failed photo and yields an empty bulb-id row.
            if look is not None and not isinstance(look, (list, tuple)):
                return _error(f"looks[{i}] must be a list of bulb "
                              "detections (one list per photo).", 400)
            for j, bulb in enumerate(look or ()):  # None -> nothing to check
                if not isinstance(bulb, dict):
                    return _error(
                        f"looks[{i}][{j}] must be a bulb object with cls, "
                        "confidence and size_grade fields.", 400)
        # NOTE(Q2260): all-empty looks ([[ ], []]) are deliberately NOT
        # rejected here -- tests/test_two_look_ci.py and
        # tests/test_finalize_defect_ci.py encode the contract that
        # degenerate/empty captures finalise successfully with no invented
        # interval fields. An honest empty record beats blocking the bench.

        # QA LOOP-Q2216: free-text fields are sanitised BEFORE anything can
        # reach the ledger or a public page. Unicode names are the norm
        # here; lone surrogates, control bytes and novel-length blobs are
        # not. A ValueError from _clean_text is a caller mistake -> 400.
        try:
            farmer_name = _clean_text(payload.get("farmer_name"),
                                      "farmer_name", max_len=200)
            officer_name = _clean_text(payload.get("officer_name"),
                                       "officer_name", max_len=200)
            centre_name = _clean_text(payload.get("centre_name"),
                                      "centre_name", max_len=120)
            lot_ref = _clean_text(payload.get("lot_ref"),
                                  "lot_ref", max_len=120)
        except ValueError as exc:
            return _error(str(exc), 400)

        # The server vouches for certificate timestamps: a client clock that
        # is wrong (dead battery, manual setting) does not get to date a
        # signed record into 1970 or next month.
        created_at, ts_override = _trusted_created_at(payload.get("created_at"))

        result = grading.merge_looks(looks)

        # RT-001 S-3: the defect percentage drove rejections but shipped as a
        # bare point estimate. Attach a Wilson interval around the same worst-
        # look statistic (occlusion-scaled) so the certificate's most-disputed
        # number carries its own uncertainty. Empty dict on degenerate input --
        # no interval is rendered rather than an invented one.
        result.update(arbitration.defect_ci_fields(result, looks))

        # LOOP-D2218 / RT-001 S-2: the pooled Grade-A interval treated both
        # looks of a shaken tray as independent bulbs. Recompute it at
        # effective sample size (worst-case rho=1 -> n_eff = obs / looks)
        # BEFORE insert_lot signs ci_low/ci_high into the hash chain. The
        # frozen pooled bounds survive as grade_a_ci_pooled_*; grading.py
        # itself is untouched. Empty captures add no fields.
        result.update(arbitration.grade_a_ci_fields(result))

        # QA LOOP-Q2260: validate BEFORE any write. A truthy check keeps
        # the legacy fallback the UI relies on -- it posts
        # `centre_id: $('centre').value || null`, so ''/null (and 0/False)
        # mean 'file under centre_name', exactly as before.
        centre_id: int
        if payload.get("centre_id"):
            centre_id, centre_err = _validated_centre_id(payload["centre_id"])
            if centre_err:
                return _error(centre_err, 400)
        else:
            centre_id = db.upsert_centre(centre_name or "Unassigned")

        written = db.insert_lot(
            centre_id=centre_id,
            lot_ref=lot_ref or "UNLABELLED",
            result=result,
            meta={
                "farmer_name": farmer_name,
                "officer_name": officer_name,
                "lat": payload.get("lat"),
                "lon": payload.get("lon"),
                "calibrated": payload.get("calibrated", False),
                "scale_source": payload.get("scale_source"),
                "scale_confidence": payload.get("scale_confidence"),
                "looks": looks,
                "created_at": created_at,
            },
            # Idempotent retries: a double-tap or a timeout-retry must not
            # mint a second certificate for the same physical lot.
            dedupe=True,
        )

        # RT-001 T-7: persist one annotated thumbnail per look so the
        # certificate's evidence section stops being permanently empty.
        # Deliberately AFTER insert_lot committed and inside its own
        # try/except: a photograph is supporting evidence, not a signed
        # field, so any failure here degrades to a note on a SUCCESSFUL
        # certificate instead of blocking it. A deduped retry lands on the
        # same lot id, overwriting byte-identical files -- harmless.
        evidence_saved = 0
        evidence_note = None
        try:
            shots, skipped = evidence_mod.extract_shots(payload.get("shots"))
            if shots:
                manifest = evidence_mod.save_lot_evidence(
                    written["lot_id"], shots)
                if manifest:
                    db.set_evidence(written["lot_id"], manifest)
                    evidence_saved = len(manifest)
            dropped = skipped + (len(shots) - evidence_saved)
            if dropped:
                evidence_note = (f"{dropped} photo(s) could not be stored; "
                                 "the certified numbers are unaffected.")
        except Exception as ev_exc:  # noqa: BLE001 -- degrade, never block
            traceback.print_exc()
            evidence_note = ("Photographs could not be saved to storage "
                             f"({type(ev_exc).__name__}); the certificate "
                             "and its numbers are unaffected.")

        response = {"lot_id": written["lot_id"], "row_hash": written["row_hash"],
                    # Per-look bulb row ids, shaped like the request's looks, so
                    # the UI can wire its contest button to real rows (RT-001 T-4).
                    "bulb_ids": written.get("bulb_ids"),
                    "result": result,
                    "evidence_saved": evidence_saved,
                    "duplicate": bool(written.get("duplicate"))}
        if evidence_note:
            response["evidence_note"] = evidence_note
        if ts_override:
            # Honest substitution: say so rather than quietly rewriting the
            # client's idea of when this happened.
            response["server_timestamp_used"] = True
            response["timestamp_note"] = ts_override
        return response
    except UnicodeEncodeError:
        # Garbage nested deeper than the per-field cleaner reaches (e.g.
        # inside look bulbs) surfaces at the sqlite bind. Still a caller
        # mistake, still 400 with a path forward -- not a bare 500 shrug.
        traceback.print_exc()
        return _error("Some text field contains characters that cannot be "
                      "stored (invalid encoding). Remove unusual symbols "
                      "and retry.", 400)
    except sqlite3.OperationalError as exc:
        traceback.print_exc()
        lowered = str(exc).lower()
        if "disk" in lowered or "full" in lowered or "space" in lowered:
            # SQLITE_FULL lands here. The critical question for an officer
            # mid-dispute is whether evidence half-saved: it did not -- the
            # insert transaction rolled back whole.
            return _error("Storage is full -- the certificate was NOT saved "
                          "and nothing was written. Free disk space on the "
                          "server (or archive old lots), then press Finalize "
                          "again.", 503)
        return _error(f"Could not save lot: {type(exc).__name__}", 500)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return _error(f"Could not save lot: {type(exc).__name__}", 500)


@app.post("/dispute/{bulb_id}")
def dispute(bulb_id: int):
    """Record a farmer's contest on one stored bulb row (RT-001 T-4).

    Disputes annotate the evidence, like the bulb rows themselves -- they sit
    outside the hash chain and do not alter any certified number. An unknown
    id is a 404 so the client can never show 'logged' without a row actually
    changing.
    """
    try:
        if not db.mark_disputed(bulb_id):
            return _error(f"No saved bulb record {bulb_id} to dispute.", 404)
        return {"ok": True, "bulb_id": bulb_id}
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return _error(f"Could not log dispute: {type(exc).__name__}", 500)


# --------------------------------------------------------------------------
# Read-only API
# --------------------------------------------------------------------------


@app.get("/api/centres")
def api_centres():
    try:
        return {"centres": db.list_centres()}
    except Exception as exc:  # noqa: BLE001
        return _error(f"{type(exc).__name__}", 500)


@app.get("/api/drift")
def api_drift():
    try:
        report_rows = db.drift_report()
        for row in report_rows:
            intact, count = db.verify_chain(row["centre_id"])
            row["chain_intact"] = intact
            row["chain_records"] = count
        return {"centres": report_rows}
    except Exception as exc:  # noqa: BLE001
        return _error(f"{type(exc).__name__}", 500)


@app.get("/api/twin/{lot_id}")
def api_twin(lot_id: int, severity: float = twin.DEFAULT_SEVERITY,
             seed: int | None = None):
    """Digital-twin replay of one certified lot under quality drift.

    Pure simulation on ledger data -- no model, no camera, no network.
    Baseline numbers are read from the hash-chained record (measured);
    scenario numbers are seeded forward replay (simulated). Same inputs
    always give the same answer, so this is safe to show next to a
    signed certificate.
    """
    try:
        lot = db.get_lot(lot_id)
    except Exception as exc:  # noqa: BLE001
        return _error(f"{type(exc).__name__}", 500)
    if lot is None:
        return _error(f"Lot {lot_id} not found.", 404)
    try:
        return twin.simulate_lot(lot, severity=severity, seed=seed)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: twin simulate failed on lot {lot_id} -- "
              f"{type(exc).__name__}: {exc}")
        return _error(f"{type(exc).__name__}", 500)


@app.get("/api/calibration")
def api_calibration():
    """Detector-confidence calibration: does the ACCEPT threshold mean what
    it promises?

    Serves the measured report from scripts/eval_calibration.py (ECE,
    reliability bins, recommended accept cut, temperature fit). No model, no
    camera, no network -- if the measurement has not been run, or its file
    is unreadable, the panel degrades to available:false instead of a dead
    screen. A missing calibration is a fact about the deployment, not an
    error the client needs a 404 dance for.
    """
    try:
        if not CALIBRATION_REPORT.exists():
            return {"available": False, "reason": "not_generated",
                    "hint": "python scripts/eval_calibration.py"}
        try:
            data = json.loads(CALIBRATION_REPORT.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"available": False, "reason": "corrupt",
                    "hint": "re-run python scripts/eval_calibration.py"}
        except OSError:
            return {"available": False, "reason": "unreadable",
                    "hint": "check permissions on runs/report/calibration.json"}
        return {"available": True, **data}
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: /api/calibration failed -- "
              f"{type(exc).__name__}: {exc}")
        return _error(f"{type(exc).__name__}", 500)


@app.get("/api/lots")
def api_lots(centre_id: int | None = None, limit: int = 20):
    try:
        return {"lots": db.recent_lots(centre_id, limit)}
    except Exception as exc:  # noqa: BLE001
        return _error(f"{type(exc).__name__}", 500)


def _list_replay_ids() -> list[int]:
    """Replay numbers present in the cache, tolerating a messy cache dir.

    QA audit B-001: a stray file such as replay_.json or replay_notes.json
    used to raise ValueError from int() and take /api/health down with it.
    Junk names are skipped, duplicates collapse, and an unscannable directory
    degrades to "none available" instead of an exception.
    """
    ids: set[int] = set()
    try:
        candidates = list(CACHE.glob("replay_*.json"))
    except Exception as exc:  # noqa: BLE001 -- health must answer regardless
        print(f"WARNING: cannot scan cache dir {CACHE} -- "
              f"{type(exc).__name__}: {exc}")
        return []
    for p in candidates:
        try:
            ids.add(int(p.stem.split("_")[1]))
        except (ValueError, IndexError):
            continue
    return sorted(ids)


@app.get("/api/replay/{n}")
def api_replay(n: int):
    """Cached /analyze response. The offline demo path -- no model, no GPU,
    no network. If this breaks, the demo has no fallback."""
    path = CACHE / f"replay_{n}.json"
    if not path.exists():
        return _error(f"No cached replay {n}. Available: {_list_replay_ids()}",
                      404)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _error(f"Replay file {n} is corrupt.", 500)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"WARNING: replay {n} read failed -- {type(exc).__name__}: {exc}")
        return _error(f"Replay file {n} could not be read "
                      f"({type(exc).__name__}).", 500)


@app.get("/api/health")
def api_health():
    return {
        "model_loaded": MODEL is not None,
        "model_error": MODEL_ERROR,
        "e2e_mode": E2E_MODE,
        # RT-001 D-1 diagnosis aid: False here explains a 503 from /analyze
        # without needing console access on the venue machine.
        "aruco_available": scale_mod.ARUCO_AVAILABLE,
        "constants": grading.CONSTANTS,
        "replays_available": _list_replay_ids(),
    }


# --------------------------------------------------------------------------
# Verification -- the public trust surface
# --------------------------------------------------------------------------


def _lot_verification(lot_id: int) -> dict | None:
    """Everything the verify page and API need about one certificate."""
    lot = db.get_lot(lot_id)
    if lot is None:
        return None
    intact, audits, n_records = db.audit_chain(lot["centre_id"])
    audit_by_id = {a["lot_id"]: a["ok"] for a in audits}
    return {
        "lot": {
            "id": lot["id"],
            "lot_ref": lot["lot_ref"],
            "centre_name": lot.get("centre_name"),
            "farmer_name": lot["farmer_name"],
            "officer_name": lot["officer_name"],
            "created_at": lot["created_at"],
            "grade_a_pct": lot["grade_a_pct"],
            "ci_low": lot["ci_low"],
            "ci_high": lot["ci_high"],
            "defect_pct": lot["defect_pct"],
            "n_bulbs": lot["n_bulbs"],
            "n_looks": lot["n_looks"],
            "row_hash": lot["row_hash"],
            "this_record_ok": audit_by_id.get(lot_id, False),
        },
        "chain": {
            "intact": intact,
            "records_checked": n_records,
            "audit": audits,
        },
    }


@app.get("/api/verify/{lot_id}")
def api_verify(lot_id: int):
    try:
        result = _lot_verification(lot_id)
        if result is None:
            return _error("No such certificate.", 404)
        return result
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return _error(f"Verification failed: {type(exc).__name__}", 500)


@app.get("/verify/{lot_id}", response_class=HTMLResponse)
def verify_page(lot_id: int, request: Request):
    data = _lot_verification(lot_id)
    if data is None:
        return HTMLResponse("<h1>No such certificate</h1>", status_code=404)
    path = STATIC / "verify.html"
    if not path.exists():
        return _error_page("verify.html is missing on this machine.", 404)
    try:
        page = path.read_text(encoding="utf-8").replace(
            '"__LOT_DATA__"', _json_for_script(data)
        ).replace(
            "__REPORT_URL__", str(request.base_url).rstrip("/") + f"/report/{lot_id}"
        )
    except Exception:  # noqa: BLE001 -- a broken template must still answer
        traceback.print_exc()
        return _error_page(f"The verification page for certificate {lot_id} "
                           "could not be built. Try again.", 503)
    return HTMLResponse(page)


# --------------------------------------------------------------------------
# Arbitration -- dispute verdicts, price bands, sample sufficiency
# --------------------------------------------------------------------------


def _compact_lot_for_arbitration(lot: dict) -> dict:
    return {
        "pct": float(lot["grade_a_pct"] or 0.0),
        "lo": float(lot["ci_low"] or 0.0),
        "hi": float(lot["ci_high"] or 100.0),
        "n": int(lot["n_bulbs"] or 0),
    }


@app.get("/api/arbitrate")
def api_arbitrate(a: int, b: int, alpha: float = 0.05):
    """Verdict on whether two independently graded lots agree."""
    try:
        if a == b:
            return _error("Pick two different certificates.")
        lot_a, lot_b = db.get_lot(a), db.get_lot(b)
        missing = [x for x, lot in (("A", lot_a), ("B", lot_b)) if lot is None]
        if missing:
            return _error(f"Certificate(s) not found: {', '.join(missing)}", 404)
        verdict = arbitration.compare_lots(
            _compact_lot_for_arbitration(lot_a),
            _compact_lot_for_arbitration(lot_b),
            alpha=max(0.001, min(0.5, alpha)),
        )
        for key, lot in (("lot_a_record", lot_a), ("lot_b_record", lot_b)):
            verdict[key] = {
                "id": lot["id"], "lot_ref": lot["lot_ref"],
                "centre_name": lot.get("centre_name"),
                "farmer_name": lot["farmer_name"],
                "created_at": lot["created_at"],
            }
        return verdict
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return _error(f"Arbitration failed: {type(exc).__name__}", 500)


@app.get("/api/price-band/{lot_id}")
def api_price_band(lot_id: int):
    """Rupees-per-quintal band implied by a certificate's grade mix."""
    try:
        lot = db.get_lot(lot_id)
        if lot is None:
            return _error("No such certificate.", 404)
        result = lot.get("result") or {}
        grade_pcts = result.get("grade_pcts") or {}
        if not grade_pcts:
            return _error("This certificate has no grade mix stored.", 400)
        band = arbitration.fair_price_band(
            grade_pcts,
            float(lot["ci_low"] or 0.0),
            float(lot["ci_high"] or 100.0),
        )
        band["lot_ref"] = lot["lot_ref"]
        band["grade_pcts"] = grade_pcts
        return band
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return _error(f"Price band failed: {type(exc).__name__}", 500)


@app.get("/api/sufficiency/{lot_id}")
def api_sufficiency(lot_id: int, target: float = arbitration.TARGET_HALF_WIDTH_PCT):
    """Would this certificate's sample size survive its own promise?"""
    try:
        lot = db.get_lot(lot_id)
        if lot is None:
            return _error("No such certificate.", 404)
        result = lot.get("result") or {}
        out = arbitration.sample_sufficiency(
            int(result.get("n_bulb_observations") or lot.get("n_bulbs") or 0),
            p_hat_pct=float(lot["grade_a_pct"] or 50.0),
            target_half_width_pct=target,
        )
        out["lot_ref"] = lot["lot_ref"]
        return out
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return _error(f"Sufficiency failed: {type(exc).__name__}", 500)


# --------------------------------------------------------------------------
# Tamper demo -- a LIVE attack on the record, and the proof it fails
#
# Demo theatre with honest mechanics: the attack endpoint really mutates the
# row (no simulation flag), exactly like a dishonest officer with database
# access would. The chain then flags THAT certificate red on every verify.
# Restore puts the original value back from in-memory state; if the server
# restarted between attack and restore, the value is recoverable from
# result_json, which the hash never covered.
# --------------------------------------------------------------------------

_TAMPER_STATE: dict[int, dict] = {}


def _tamper_original_value(lot: dict) -> float:
    """The true grade_a_pct even if this server restarted mid-attack."""
    saved = _TAMPER_STATE.get(lot["id"])
    if saved is not None:
        return saved["original"]
    return float((lot.get("result") or {}).get("grade_a_pct")
                 or lot.get("grade_a_pct") or 0.0)


def _set_grade_a(lot_id: int, value: float) -> None:
    """The one write path of the demo: edit the column, never touch hashes."""
    conn = db.connect()
    try:
        conn.execute("UPDATE lots SET grade_a_pct = ? WHERE id = ?",
                     (value, lot_id))
        conn.commit()
    finally:
        conn.close()


@app.post("/tamper/attack/{lot_id}")
def tamper_attack(lot_id: int):
    """One round trip does everything: edit the row, then honestly recompute
    the chain and report exactly which certificate went red. The UI renders
    the flip from this response alone -- no second fetch, so it stays under
    a second even on venue wifi."""
    try:
        lot = db.get_lot(lot_id)
        if lot is None:
            return _error("No such certificate.", 404)
        original = _tamper_original_value(lot)
        bumped = min(99.9, round(original + 25.0, 2))
        _set_grade_a(lot_id, bumped)
        _TAMPER_STATE[lot_id] = {"original": original}
        intact, audits, checked = db.audit_chain(lot["centre_id"])
        broken = [a["lot_id"] for a in audits if not a["ok"]]
        return {"ok": True, "lot_id": lot_id, "was": original, "now": bumped,
                "lot_ref": lot["lot_ref"], "centre_id": lot["centre_id"],
                "audit": {"intact": intact, "broken_lot_ids": broken,
                          "records_checked": checked},
                "note": "Row edited directly, hash NOT recomputed -- "
                        "exactly what an attacker with database access does."}
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return _error(f"Attack failed: {type(exc).__name__}", 500)


@app.post("/tamper/restore/{lot_id}")
def tamper_restore(lot_id: int):
    try:
        state = _TAMPER_STATE.pop(lot_id, None)
        lot = db.get_lot(lot_id)
        if lot is None:
            return _error("No such certificate.", 404)
        value = state["original"] if state else _tamper_original_value(lot)
        _set_grade_a(lot_id, value)
        intact, _, checked = db.audit_chain(lot["centre_id"])
        return {"ok": True, "lot_id": lot_id, "restored_to": value,
                "intact_after": intact, "records_checked": checked}
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return _error(f"Restore failed: {type(exc).__name__}", 500)


# Mismatch below this size is float rounding, not an attack.
_GRADE_A_MATCH_TOL = 0.05


@app.post("/tamper/restore-all")
def tamper_restore_all():
    """The demo must be impossible to leave broken.

    Two sweeps, both honest:
      1. every lot this server remembers attacking -> restore from memory;
      2. every row whose stored grade_a_pct disagrees with its own
         result_json copy -> restore from result_json. This catches attacks
         made before a server restart, when in-memory state is gone.
    result_json is written once at insert and never edited afterwards, and
    nothing else in the app UPDATEs lots, so a mismatch IS a live attack --
    restoring from result_json puts back the exact hashed value.
    """
    try:
        restored: list[dict] = []
        centres: set[int] = set()

        for lot_id, state in list(_TAMPER_STATE.items()):
            lot = db.get_lot(lot_id)
            if lot is None:
                _TAMPER_STATE.pop(lot_id, None)
                continue
            value = state["original"]
            if abs(float(lot["grade_a_pct"] or 0.0) - value) > _GRADE_A_MATCH_TOL:
                _set_grade_a(lot_id, value)
                restored.append({"lot_id": lot_id, "restored_to": value})
            centres.add(lot["centre_id"])
            _TAMPER_STATE.pop(lot_id, None)

        conn = db.connect()
        try:
            rows = conn.execute(
                "SELECT id, centre_id, grade_a_pct, result_json FROM lots"
            ).fetchall()
        finally:
            conn.close()
        for row in rows:
            try:
                truth = float(json.loads(row["result_json"] or "{}")
                              .get("grade_a_pct") or 0.0)
            except (ValueError, TypeError):
                continue  # unreadable result_json -- leave the row alone
            stored = float(row["grade_a_pct"] or 0.0)
            if abs(stored - truth) > _GRADE_A_MATCH_TOL:
                _set_grade_a(int(row["id"]), truth)
                restored.append({"lot_id": int(row["id"]), "restored_to": truth})
                centres.add(int(row["centre_id"]))

        # Dedupe (both sweeps can hit the same lot).
        seen: set[int] = set()
        restored = [r for r in restored
                    if not (r["lot_id"] in seen or seen.add(r["lot_id"]))]

        intact_after = True
        for centre_id in centres:
            intact, _, _ = db.audit_chain(centre_id)
            intact_after = intact_after and intact
        return {"ok": True, "restored": restored,
                "n_restored": len(restored), "intact_after": intact_after}
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return _error(f"Restore-all failed: {type(exc).__name__}", 500)


@app.get("/tamper-demo", response_class=HTMLResponse)
def tamper_demo_page():
    return _serve("tamper-demo.html")


@app.get("/arbitrate", response_class=HTMLResponse)
def arbitrate_page():
    return _serve("arbitrate.html")
