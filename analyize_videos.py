"""
Logistics Claims Video Analyzer — Production Grade
====================================================
Handles missing videos, poor frames, OCR failures, and partial evidence
gracefully. Every piece of evidence is optional — the system adapts its
confidence and decision based on what's actually available.

Requirements:
    pip install anthropic opencv-python-headless pytesseract numpy Pillow

External:
    - ffmpeg (apt install ffmpeg)
    - tesseract (apt install tesseract-ocr)
"""

import anthropic
import base64
import subprocess
import json
import os
import re
import glob
import shutil
import logging
from enum import Enum
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple

import urllib.request
import cv2
import numpy as np
import pytesseract

# ──────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/tmp/claims_analyzer.log", mode="a"),
    ],
)
log = logging.getLogger("claims_analyzer")


# ──────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────
@dataclass
class Config:
    model: str = "claude-sonnet-4-6"
    max_frames_per_video: int = 40        # 10 anchors (every 10%) + up to 10 scene frames
    anchor_pcts: Tuple = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
    dedup_threshold: float = 0.97         # histogram correlation above this = duplicate
    min_usable_frames: int = 2
    blur_threshold: float = 2.0
    brightness_range: Tuple[int, int] = (20, 240)
    ocr_confidence_min: int = 40
    awb_min_length: int = 8
    awb_max_length: int = 25
    llm_retries: int = 3
    scene_change_threshold: float = 0.10  # sensitive — catches package open, item reveal
    auto_approve_confidence: float = 0.85
    auto_reject_confidence: float = 0.80
    manual_review_below: float = 0.55
    work_dir: str = "/tmp/claims_workdir"


CFG = Config()


# ──────────────────────────────────────────────
# ENUMS & DATA CLASSES
# ──────────────────────────────────────────────
class EvidenceStatus(str, Enum):
    SHARED = "shared"
    NOT_SHARED = "not_shared"
    INVALID = "invalid"          # file exists but unusable
    PARTIAL = "partial"          # some frames usable, most bad


class Decision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    MANUAL_REVIEW = "manual_review"


@dataclass
class FrameQuality:
    path: str
    blur_score: float
    brightness: float
    is_usable: bool
    has_text: bool = False
    extracted_text: str = ""


@dataclass
class EvidenceReport:
    status: EvidenceStatus
    total_frames: int = 0
    usable_frames: int = 0
    detected_awbs: List[str] = field(default_factory=list)
    detected_texts: List[str] = field(default_factory=list)
    quality_issues: List[str] = field(default_factory=list)


@dataclass
class ClaimInput:
    case_name: str
    packing_video: Optional[str] = None   # local path or URL
    unboxing_video: Optional[str] = None  # local path or URL
    claim_type: str = ""                  # e.g. "damaged", "missing", "wrong item"


@dataclass
class ClaimResult:
    case_name: str
    timestamp: str = ""

    # Evidence availability
    packing_evidence: dict = field(default_factory=dict)
    unboxing_evidence: dict = field(default_factory=dict)

    # Analysis
    product_match: str = "not_assessed"
    packaging_integrity: str = "not_assessed"
    product_description_packing: str = ""
    product_description_unboxing: str = ""

    # Damage assessment
    item_broken: str = "not_assessed"
    break_details: List[str] = field(default_factory=list)
    item_missing: str = "not_assessed"
    loose_items_found: str = "not_assessed"
    outer_packaging_damage: List[str] = field(default_factory=list)
    accessory_count_packing: str = "unclear"
    accessory_count_unboxing: str = "unclear"
    accessory_count_match: str = "unclear"

    # AWB / chain of custody
    awb_packing: str = ""
    awb_unboxing: str = ""
    awb_match: str = "unclear"
    recipient_address_match: str = "unclear"

    # Decision
    confidence_score: float = 0.0
    recommended_decision: str = "manual_review"
    final_decision: str = "manual_review"
    rejection_reasons: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    reasoning: str = ""

    # Frame-level analysis
    frame_descriptions: List[dict] = field(default_factory=list)
    conclusion: str = ""

    # Metadata
    evidence_completeness: float = 0.0
    llm_raw_response: dict = field(default_factory=dict)
    processing_errors: List[str] = field(default_factory=list)
    token_usage: dict = field(default_factory=dict)


# ──────────────────────────────────────────────
# UTILITY: SAFE SUBPROCESS
# ──────────────────────────────────────────────
def run_cmd(cmd: List[str], timeout: int = 120) -> subprocess.CompletedProcess:
    """Run shell command with timeout and error capture."""
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        return result
    except subprocess.TimeoutExpired:
        log.warning(f"Command timed out: {' '.join(cmd[:3])}...")
        return None
    except FileNotFoundError:
        log.error(f"Binary not found: {cmd[0]}. Is it installed?")
        return None


def check_dependencies():
    """Verify ffmpeg and tesseract are installed."""
    missing = []
    if shutil.which("ffmpeg") is None:
        missing.append("ffmpeg")
    if shutil.which("tesseract") is None:
        missing.append("tesseract")
    if missing:
        raise EnvironmentError(
            f"Missing required binaries: {', '.join(missing)}. "
            f"Install with: apt install {' '.join(missing)}"
        )


# ──────────────────────────────────────────────
# FILE VALIDATION
# ──────────────────────────────────────────────
def validate_video(path: Optional[str]) -> Tuple[bool, str]:
    """Check if video file exists and is a real video."""
    if not path:
        return False, "No path provided"
    if not os.path.isfile(path):
        return False, f"File not found: {path}"

    # Check file size (empty or tiny = corrupt)
    size = os.path.getsize(path)
    if size < 1024:  # < 1KB
        return False, f"File too small ({size} bytes), likely corrupt"

    # Probe with ffmpeg
    result = run_cmd([
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_type,duration,width,height",
        "-of", "json", path
    ])
    if result is None or result.returncode != 0:
        return False, "ffprobe failed — not a valid video"

    try:
        probe = json.loads(result.stdout.decode())
        streams = probe.get("streams", [])
        if not streams:
            return False, "No video stream found"
        duration = float(streams[0].get("duration", 0))
        if duration < 1.0:
            return False, f"Video too short ({duration:.1f}s)"
        return True, f"Valid video ({duration:.1f}s)"
    except Exception as e:
        return False, f"Probe parse error: {e}"


def validate_image(path: Optional[str]) -> Tuple[bool, str]:
    """Check if image file exists and is readable."""
    if not path:
        return False, "No path provided"
    if not os.path.isfile(path):
        return False, f"File not found: {path}"

    img = cv2.imread(path)
    if img is None:
        return False, "OpenCV cannot read this image"
    h, w = img.shape[:2]
    if h < 50 or w < 50:
        return False, f"Image too small ({w}x{h})"
    return True, f"Valid image ({w}x{h})"


# ──────────────────────────────────────────────
# URL DOWNLOAD
# ──────────────────────────────────────────────
def download_if_url(path: Optional[str], dest: str) -> Optional[str]:
    """If path is a URL, download it to dest and return local path; otherwise return as-is."""
    if not path:
        return path
    if path.startswith("http://") or path.startswith("https://"):
        try:
            log.info(f"  Downloading {path[:80]}...")
            urllib.request.urlretrieve(path, dest)
            log.info(f"  Saved to {dest}")
            return dest
        except Exception as e:
            log.error(f"  Download failed: {e}")
            return None
    return path


# ──────────────────────────────────────────────
# FRAME EXTRACTION (ROBUST)
# ──────────────────────────────────────────────
def get_video_duration(video_path: str) -> float:
    """Return video duration in seconds, or 0 on failure."""
    result = run_cmd([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=duration", "-of", "json", video_path
    ])
    if result and result.returncode == 0:
        try:
            data = json.loads(result.stdout.decode())
            return float(data["streams"][0].get("duration", 0))
        except Exception:
            pass
    return 0.0


def deduplicate_frames(frames: List[str]) -> List[str]:
    """Remove visually near-identical frames using histogram correlation."""
    if not frames:
        return frames
    kept = [frames[0]]
    for path in frames[1:]:
        img = cv2.imread(path)
        ref = cv2.imread(kept[-1])
        if img is None or ref is None:
            kept.append(path)
            continue
        # Compare grayscale histograms
        h1 = cv2.calcHist([cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)], [0], None, [64], [0, 256])
        h2 = cv2.calcHist([cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)], [0], None, [64], [0, 256])
        similarity = cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL)
        if similarity < CFG.dedup_threshold:
            kept.append(path)
    return kept


def extract_frames(video_path: str, out_dir: str) -> List[Tuple[str, float]]:
    """
    Returns List[(path, timestamp_seconds)] sorted chronologically.
    3-layer strategy:
      1. Anchor frames  — exact timestamps at 0%, 25%, 50%, 75%, 100%
      2. Scene-change   — key visual transitions (open, reveal, labels)
      3. Deduplication  — drops near-identical consecutive frames
    """
    os.makedirs(out_dir, exist_ok=True)
    n        = CFG.max_frames_per_video
    duration = get_video_duration(video_path)
    log.info(f"  Duration: {duration:.1f}s | target={n} frames")

    scene_dir  = os.path.join(out_dir, "scene")
    anchor_dir = os.path.join(out_dir, "anchor")
    os.makedirs(scene_dir,  exist_ok=True)
    os.makedirs(anchor_dir, exist_ok=True)

    # ── Layer 1: Anchor frames — one per 10% interval, exact timestamps in filename ──
    anchor_pairs: List[Tuple[str, float]] = []
    if duration > 0:
        for pct in CFG.anchor_pcts:
            t = round(duration * pct, 2)
            out_path = f"{anchor_dir}/anchor_t{t:.2f}.jpg"
            run_cmd([
                "ffmpeg", "-y", "-ss", str(t), "-i", video_path,
                "-vframes", "1", "-vf", "scale=1280:-1", "-q:v", "2", out_path
            ])
            if os.path.isfile(out_path):
                anchor_pairs.append((out_path, t))

    # ── Layer 2: Scene-change frames (temporal position approximated) ──
    run_cmd([
        "ffmpeg", "-y", "-i", video_path,
        "-vf", f"select='gt(scene,{CFG.scene_change_threshold})',scale=1280:-1",
        "-vsync", "vfr", "-q:v", "2",
        f"{scene_dir}/scene_%04d.jpg"
    ])
    all_scene = sorted(glob.glob(f"{scene_dir}/*.jpg"))
    remaining = max(0, n - len(anchor_pairs))
    if len(all_scene) > remaining:
        step = len(all_scene) / remaining
        all_scene = [all_scene[int(i * step)] for i in range(remaining)]
    # Approximate timestamp: position in sorted list × duration
    total_scene = max(len(all_scene), 1)
    scene_pairs: List[Tuple[str, float]] = [
        (p, round(duration * (i / total_scene), 2))
        for i, p in enumerate(all_scene)
    ]

    combined = anchor_pairs + scene_pairs

    # Fallback: evenly spaced with calculated timestamps
    if not combined:
        log.warning("  Anchor+scene failed, falling back to evenly spaced frames")
        fps = max(0.1, min(round(n / duration, 3) if duration > 0 else 1.0, 4.0))
        even_dir = os.path.join(out_dir, "even")
        os.makedirs(even_dir, exist_ok=True)
        run_cmd([
            "ffmpeg", "-y", "-i", video_path,
            "-vf", f"fps={fps},scale=1280:-1", "-q:v", "2",
            f"{even_dir}/fps_%04d.jpg"
        ])
        even_paths = sorted(glob.glob(f"{even_dir}/*.jpg"))
        total_even = max(len(even_paths), 1)
        combined = [(p, round(duration * i / total_even, 2)) for i, p in enumerate(even_paths)]

    # Sort by timestamp, deduplicate paths, remove near-identical frames
    combined = sorted({p: t for p, t in combined}.items(), key=lambda x: x[1])
    paths_deduped = deduplicate_frames([p for p, _ in combined])
    path_set = set(paths_deduped)
    combined = [(p, t) for p, t in combined if p in path_set][:n]

    log.info(f"  → {len(anchor_pairs)} anchors + {len(scene_pairs)} scene → {len(combined)} after dedup")
    return combined


# ──────────────────────────────────────────────
# FRAME QUALITY ASSESSMENT
# ──────────────────────────────────────────────
def assess_frame(path: str) -> FrameQuality:
    """Score a single frame for blur, brightness, and text content."""
    img = cv2.imread(path)
    if img is None:
        return FrameQuality(path=path, blur_score=0, brightness=0, is_usable=False)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Blur detection (Laplacian variance — higher = sharper)
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()

    # Brightness (mean pixel value)
    brightness = float(np.mean(gray))

    is_usable = (
        blur_score >= CFG.blur_threshold
        and CFG.brightness_range[0] <= brightness <= CFG.brightness_range[1]
    )

    return FrameQuality(
        path=path,
        blur_score=round(blur_score, 2),
        brightness=round(brightness, 2),
        is_usable=is_usable,
    )


def filter_usable_frames(frames: List[str]) -> Tuple[List[str], List[str]]:
    """Return (usable_paths, quality_issues)."""
    issues = []
    usable = []

    for f in frames:
        q = assess_frame(f)
        if q.is_usable:
            usable.append(f)
        else:
            if q.blur_score < CFG.blur_threshold:
                issues.append(f"Blurry frame skipped: {os.path.basename(f)} (score={q.blur_score})")
            else:
                issues.append(f"Dark/bright frame skipped: {os.path.basename(f)} (brightness={q.brightness})")

    return usable, issues


# ──────────────────────────────────────────────
# OCR — ENHANCED AWB EXTRACTION
# ──────────────────────────────────────────────
AWB_PATTERNS = [
    re.compile(r"\b\d{12,18}\b"),                        # Pure numeric (Delhivery, Ecom Express)
    re.compile(r"\b[A-Z]{2,5}\d{8,15}\b", re.IGNORECASE),  # Prefix+numeric (WMLC, SF, R+digits)
    re.compile(r"\b[A-Z]\d{8,12}[A-Z]?\b", re.IGNORECASE), # I25523370, R1928378983WMA
    re.compile(r"\bSHOP\d{8,15}\b", re.IGNORECASE),      # SHOP50000020562
]


def enhanced_ocr(image_path: str) -> Tuple[str, List[str]]:
    """
    Multi-pass OCR with preprocessing.
    Returns (full_text, list_of_awb_candidates).
    """
    img = cv2.imread(image_path)
    if img is None:
        return "", []

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    awb_candidates = set()
    all_text_parts = []

    # Pass 1: Original grayscale
    preprocessed = [gray]

    # Pass 2: Adaptive threshold (handles uneven lighting)
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    preprocessed.append(thresh)

    # Pass 3: OTSU threshold (good for labels)
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    preprocessed.append(otsu)

    # Pass 4: Inverted (white text on dark background)
    preprocessed.append(cv2.bitwise_not(gray))

    for i, processed in enumerate(preprocessed):
        try:
            # Use pytesseract with confidence data
            data = pytesseract.image_to_data(
                processed, output_type=pytesseract.Output.DICT
            )
            text_parts = []
            for j, word in enumerate(data["text"]):
                conf = int(data["conf"][j])
                if conf >= CFG.ocr_confidence_min and word.strip():
                    text_parts.append(word.strip())

            full_text = " ".join(text_parts)
            all_text_parts.append(full_text)

            # Pattern match for AWBs
            for pattern in AWB_PATTERNS:
                matches = pattern.findall(full_text)
                for m in matches:
                    cleaned = m.strip().upper()
                    if CFG.awb_min_length <= len(cleaned) <= CFG.awb_max_length:
                        awb_candidates.add(cleaned)

        except Exception as e:
            log.debug(f"OCR pass {i} failed on {image_path}: {e}")
            continue

    combined_text = " | ".join(filter(None, all_text_parts))
    return combined_text, list(awb_candidates)


def extract_awbs_from_frames(frames: List[str]) -> Tuple[List[str], List[str]]:
    """Extract AWBs from all frames. Returns (awbs, raw_texts)."""
    all_awbs = set()
    all_texts = []

    for frame in frames:
        text, awbs = enhanced_ocr(frame)
        all_awbs.update(awbs)
        if text.strip():
            all_texts.append(text)

    return list(all_awbs), all_texts


# ──────────────────────────────────────────────
# AWB MATCHING
# ──────────────────────────────────────────────
def awb_match_score(detected: List[str], expected: str) -> Tuple[str, float]:
    """
    Compare detected AWBs against the expected AWB.
    Returns (status, confidence).
    """
    if not detected:
        return "not_detected", 0.0

    expected_clean = expected.strip().upper()

    for d in detected:
        if d == expected_clean:
            return "exact_match", 1.0

    # Partial match (OCR errors — allow 1-2 char difference)
    for d in detected:
        if len(d) == len(expected_clean):
            diff = sum(1 for a, b in zip(d, expected_clean) if a != b)
            if diff <= 2:
                return "partial_match", 0.7

    # Substring match
    for d in detected:
        if expected_clean in d or d in expected_clean:
            return "substring_match", 0.6

    return "no_match", 0.0


# ──────────────────────────────────────────────
# ENCODE FOR LLM
# ──────────────────────────────────────────────
MAX_IMAGE_DIM = 1568  # Anthropic many-image limit is 2000px; stay safely below


def encode_image_b64(path: str) -> Optional[str]:
    """Encode image to base64, resizing if either dimension exceeds MAX_IMAGE_DIM."""
    try:
        img = cv2.imread(path)
        if img is None:
            return None
        h, w = img.shape[:2]
        if h > MAX_IMAGE_DIM or w > MAX_IMAGE_DIM:
            scale = MAX_IMAGE_DIM / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return base64.b64encode(buf.tobytes()).decode()
    except Exception as e:
        log.warning(f"Failed to encode {path}: {e}")
        return None


# ──────────────────────────────────────────────
# LLM PROMPT BUILDER
# ──────────────────────────────────────────────
SYSTEM_PROMPT = """You are a strict logistics claims analyst for a D2C jewelry marketplace.
Analyze packing and unboxing video frames to verify claims of damage, tampering, substitution, or missing items.
Frames are labelled with their exact timestamp (e.g. [Packing @ 5.2s]) — use these to describe when events occur.

━━━ CORE RULES ━━━
1. Analyze ONLY what you can see. Mark anything unclear as "unclear" — never guess.
2. Compare every packing detail against unboxing frames systematically.
3. Count items, components, and accessories in both videos and note any discrepancy.
4. The frames are in chronological order — track what changes over time.

━━━ PACKING VIDEO — WHAT TO CAPTURE ━━━
- Jewelry type (necklace, ring, earring set, bracelet, pendant, anklet, combo set).
- Metal color (gold / rose-gold / silver / oxidised), stone color, stone count, design motif.
- Packaging: branded box, velvet pouch, foam insert, bubble wrap, card backing.
- All accessories packed: how many pieces, any separate chain/pendant/earring backs.
- Tags: price tag, hallmark, certification card, QR sticker, brand label.
- AWB/tracking number and delivery address visible on label.
- Condition of the item at packing time: intact, new, no visible damage.

━━━ UNBOXING VIDEO — DAMAGE & BREAK DETECTION ━━━
OUTER PACKAGING:
- Sealed or pre-opened? Torn tape, re-taped seams, punctured bag, irregular tear pattern.
- AWB label: does it match packing video? Different recipient address = possible RTO/wrong shipment.
- Physical marks, dents, or crush damage on box/bag not present during packing.

INNER PACKAGING:
- Is the jewelry box/pouch intact or opened/crushed?
- Are protective inserts (foam, velvet, bubble wrap) present, displaced, or missing?
- Are all accessories still in their slots, or loose/missing?

PRODUCT — BROKEN/DAMAGED ITEM CHECKS:
- Snapped or kinked chain (look for sharp bends, broken links, disconnected sections).
- Broken clasp or lobster lock (detached, bent, not functional).
- Missing or loose stones (empty prong settings, rattling stones, stone chips on surface).
- Bent prongs or settings that could cause stone loss.
- Cracked, shattered, or chipped enamel/stone surface.
- Tarnishing, black spots, or corrosion not present during packing.
- Dents or deformation in metal (ring band, pendant bail, bracelet links).
- Broken earring post, missing butterfly back.
- Item appears crushed or warped compared to packing.

SUBSTITUTION / WRONG ITEM SIGNALS:
- Different metal color, finish, or design from packing.
- Different stone color, count, size, or cut.
- Different brand tag or no brand tag when one was packed.
- Item is a cheaper / different variant (e.g. silver instead of gold).
- Completely wrong product category (e.g. ring instead of necklace).
- Empty box/pouch — item missing entirely.
- Loose unidentified object found instead of the product.

ACCESSORY COUNT:
- Count pieces in packing vs unboxing. Missing earring back? Missing pendant? Missing chain?

━━━ AWB & CHAIN OF CUSTODY ━━━
- Record ALL AWB/tracking numbers visible in both videos.
- Flag if packing AWB ≠ unboxing AWB — could indicate wrong shipment, RTO relabeling, or fraud.
- Note recipient addresses if visible — mismatch is a red flag.

━━━ FRAUD SIGNALS ━━━
- Pre-opened package + intact outer seal = possible internal swap.
- Clean snap on chain/clasp = likely intentional damage for claim.
- Item missing but packaging undamaged = possible empty-box fraud.
- Certification card / invoice removed in unboxing but present in packing.
- Extra layers of tape covering original seal.
- RTO bag with different AWB over the original label.

You must respond with valid JSON only — no markdown fences, no text outside JSON."""


def build_llm_content(
    claim: ClaimInput,
    packing_frames: List[Tuple[str, float]],
    unboxing_frames: List[Tuple[str, float]],
    packing_awbs: List[str],
    unboxing_awbs: List[str],
) -> list:
    """Build multimodal content array for Claude."""
    content = []

    # Context
    evidence_summary = []
    if packing_frames:
        evidence_summary.append(f"Packing video: {len(packing_frames)} frames")
    else:
        evidence_summary.append("Packing video: NOT PROVIDED")

    if unboxing_frames:
        evidence_summary.append(f"Unboxing video: {len(unboxing_frames)} frames")
    else:
        evidence_summary.append("Unboxing video: NOT PROVIDED")

    content.append({
        "type": "text",
        "text": (
            f"CASE ID: {claim.case_name}\n\n"
            f"EVIDENCE AVAILABLE:\n" + "\n".join(evidence_summary) + "\n\n"
            f"OCR-detected AWBs in packing frames: {packing_awbs or 'None detected'}\n"
            f"OCR-detected AWBs in unboxing frames: {unboxing_awbs or 'None detected'}\n"
        ),
    })

    # Packing frames
    if packing_frames:
        content.append({"type": "text", "text": "=== PACKING VIDEO FRAMES ==="})
        for path, ts in packing_frames:
            encoded = encode_image_b64(path)
            if encoded:
                content.append({"type": "text", "text": f"[Packing @ {ts:.1f}s]"})
                content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": encoded},
                })
    else:
        content.append({
            "type": "text",
            "text": "=== PACKING VIDEO: NOT AVAILABLE — skip packing analysis ==="
        })

    # Unboxing frames
    if unboxing_frames:
        content.append({"type": "text", "text": "=== UNBOXING VIDEO FRAMES ==="})
        for path, ts in unboxing_frames:
            encoded = encode_image_b64(path)
            if encoded:
                content.append({"type": "text", "text": f"[Unboxing @ {ts:.1f}s]"})
                content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": encoded},
                })
    else:
        content.append({
            "type": "text",
            "text": "=== UNBOXING VIDEO: NOT AVAILABLE — skip unboxing analysis ==="
        })

    # Analysis request — adapts to what's available
    analysis_fields = []
    if packing_frames and unboxing_frames:
        analysis_fields.append('"product_match": "match | mismatch | unclear"')
        analysis_fields.append('"packaging_integrity": "intact | tampered | unclear"')
    elif unboxing_frames:
        analysis_fields.append('"product_match": "not_assessed_no_packing_video"')
        analysis_fields.append('"packaging_integrity": "intact | tampered | unclear"')
    elif packing_frames:
        analysis_fields.append('"product_match": "not_assessed_no_unboxing_video"')
        analysis_fields.append('"packaging_integrity": "not_assessed_no_unboxing_video"')
    else:
        analysis_fields.append('"product_match": "not_assessed_no_video"')
        analysis_fields.append('"packaging_integrity": "not_assessed_no_video"')

    analysis_fields.extend([
        '"awb_packing": "AWB number from packing video or null"',
        '"awb_unboxing": "AWB number from unboxing video or null"',
        '"awb_match": "yes | no | multiple_found | unclear"',
        '"recipient_address_match": "yes | no | unclear"',
        '"pre_opened_package": "yes | no | unclear"',
        '"outer_packaging_damage": ["list of physical damage to courier bag/box or empty"]',
        '"item_broken": "yes | no | unclear"',
        '"break_details": ["snapped chain | broken clasp | missing stone | bent prong | cracked enamel | dent | crushed | other — or empty"]',
        '"accessory_count_packing": "number or unclear"',
        '"accessory_count_unboxing": "number or unclear"',
        '"accessory_count_match": "yes | no | unclear"',
        '"loose_items_found": "yes | no | unclear"',
        '"item_missing": "yes | no | unclear"',
        '"video_appears_continuous": "yes | no | unclear"',
        '"visible_tampering_signs": ["list of specific signs or empty"]',
        '"product_description_packing": "what was packed"',
        '"product_description_unboxing": "what was found on unboxing"',
        '"frame_descriptions": [{"timestamp_sec": 5.2, "source": "packing|unboxing", "description": "one sentence of what is visible"}, ...]',
        '"confidence_score": 0.0 to 1.0',
        '"recommended_decision": "approve | reject | manual_review"',
        '"reasoning": "2-3 sentence explanation"',
        '"conclusion": "comprehensive 5-7 sentence final conclusion covering: product match, damage found, AWB chain of custody, packaging integrity, and claim validity"',
    ])

    content.append({
        "type": "text",
        "text": (
            "Analyze all provided evidence and respond with this JSON structure ONLY:\n\n"
            "{\n  " + ",\n  ".join(analysis_fields) + "\n}"
        ),
    })

    return content


# ──────────────────────────────────────────────
# LLM CALL WITH RETRIES
# ──────────────────────────────────────────────
def call_claude(content: list) -> Optional[Dict]:
    """Call Claude API with retries and response validation."""
    client = anthropic.Anthropic()

    for attempt in range(CFG.llm_retries):
        try:
            log.info(f"  LLM call attempt {attempt + 1}/{CFG.llm_retries}")

            response = client.messages.create(
                model=CFG.model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
            )

            raw = response.content[0].text.strip()

            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)

            parsed = json.loads(raw)
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            }
            log.info(f"  LLM response parsed successfully (tokens: {usage['total_tokens']})")
            return parsed, usage

        except json.JSONDecodeError as e:
            log.warning(f"  LLM returned non-JSON (attempt {attempt + 1}): {e}")
            log.debug(f"  Raw response: {raw[:500]}")
        except anthropic.APIError as e:
            log.warning(f"  API error (attempt {attempt + 1}): {e}")
        except Exception as e:
            log.error(f"  Unexpected error (attempt {attempt + 1}): {e}")

    log.error("All LLM attempts failed")
    return None, {}


# ──────────────────────────────────────────────
# RULE ENGINE — POST-LLM DECISION LOGIC
# ──────────────────────────────────────────────
def compute_evidence_completeness(packing_ok: bool, unboxing_ok: bool) -> float:
    """Score 0–1 for how complete the evidence set is."""
    score = 0.0
    if packing_ok:
        score += 0.45
    if unboxing_ok:
        score += 0.55
    return round(score, 2)


def apply_decision_rules(
    llm_output: Optional[Dict],
    claim: ClaimInput,
    packing_evidence: EvidenceReport,
    unboxing_evidence: EvidenceReport,
) -> ClaimResult:
    """
    Combine LLM analysis with hard business rules.
    Business rules can OVERRIDE the LLM when evidence is missing.
    """
    result = ClaimResult(
        case_name=claim.case_name,
        timestamp=datetime.utcnow().isoformat(),
    )

    result.packing_evidence = asdict(packing_evidence)
    result.unboxing_evidence = asdict(unboxing_evidence)

    # Evidence completeness
    result.evidence_completeness = compute_evidence_completeness(
        packing_evidence.status == EvidenceStatus.SHARED,
        unboxing_evidence.status == EvidenceStatus.SHARED,
    )

    # ── Hard rules (override LLM) ──

    # Rule 1: No unboxing video → cannot verify condition
    if unboxing_evidence.status == EvidenceStatus.NOT_SHARED:
        result.flags.append("NO_UNBOXING_VIDEO")
        result.rejection_reasons.append("Unboxing video not available")

    # Rule 2: No packing video → cannot compare
    if packing_evidence.status == EvidenceStatus.NOT_SHARED:
        result.flags.append("NO_PACKING_VIDEO")
        result.rejection_reasons.append("Packing video not shared")

    # ── LLM-informed rules ──
    if llm_output:
        result.llm_raw_response = llm_output
        result.confidence_score = llm_output.get("confidence_score", 0.0)
        result.reasoning = llm_output.get("reasoning", "")
        result.conclusion = llm_output.get("conclusion", "")
        result.frame_descriptions = llm_output.get("frame_descriptions", [])
        result.product_match = llm_output.get("product_match", "not_assessed")
        result.packaging_integrity = llm_output.get("packaging_integrity", "not_assessed")
        result.product_description_packing = llm_output.get("product_description_packing", "")
        result.product_description_unboxing = llm_output.get("product_description_unboxing", "")

        # Damage fields
        result.item_broken = llm_output.get("item_broken", "not_assessed")
        result.break_details = llm_output.get("break_details", [])
        result.item_missing = llm_output.get("item_missing", "not_assessed")
        result.loose_items_found = llm_output.get("loose_items_found", "not_assessed")
        result.outer_packaging_damage = llm_output.get("outer_packaging_damage", [])
        result.accessory_count_packing = str(llm_output.get("accessory_count_packing", "unclear"))
        result.accessory_count_unboxing = str(llm_output.get("accessory_count_unboxing", "unclear"))
        result.accessory_count_match = llm_output.get("accessory_count_match", "unclear")

        # AWB chain of custody
        result.awb_packing = str(llm_output.get("awb_packing") or "")
        result.awb_unboxing = str(llm_output.get("awb_unboxing") or "")
        result.awb_match = llm_output.get("awb_match", "unclear")
        result.recipient_address_match = llm_output.get("recipient_address_match", "unclear")

        # Auto-flags from new fields
        if result.item_broken == "yes":
            result.flags.append(f"ITEM_BROKEN: {', '.join(result.break_details)}" if result.break_details else "ITEM_BROKEN")
        if result.item_missing == "yes":
            result.flags.append("ITEM_MISSING")
        if result.awb_match == "no":
            result.flags.append(f"AWB_MISMATCH: packing={result.awb_packing} unboxing={result.awb_unboxing}")
            result.rejection_reasons.append("AWB number mismatch between packing and unboxing videos")
        if result.accessory_count_match == "no":
            result.flags.append(f"ACCESSORY_COUNT_MISMATCH: packed={result.accessory_count_packing} received={result.accessory_count_unboxing}")
        if result.loose_items_found == "yes":
            result.flags.append("LOOSE_ITEM_FOUND_OUTSIDE_PACKAGING")
        if result.outer_packaging_damage:
            result.flags.append(f"OUTER_PACKAGING_DAMAGED: {', '.join(result.outer_packaging_damage)}")

        # Pre-opened package detection
        if llm_output.get("pre_opened_package") == "yes":
            result.flags.append("PRE_OPENED_UNBOXING")
            result.rejection_reasons.append("Unboxing video shows pre-opened package")

        # Tampering signs
        signs = llm_output.get("visible_tampering_signs", [])
        if signs:
            result.flags.append(f"TAMPERING_DETECTED: {', '.join(signs)}")

        # Product mismatch
        if llm_output.get("product_match") == "mismatch":
            result.flags.append("PRODUCT_MISMATCH_CONFIRMED")

        # Intact condition (no actual damage)
        if llm_output.get("packaging_integrity") == "intact":
            result.flags.append("PACKAGE_INTACT")
            result.rejection_reasons.append("Product received in intact condition")

        result.recommended_decision = llm_output.get("recommended_decision", "manual_review")
    else:
        result.processing_errors.append("LLM analysis failed — falling back to rules only")
        result.confidence_score = 0.0

    # ── Final decision logic ──
    decision = result.recommended_decision

    # Override 1: Too many missing evidence types → manual review
    if result.evidence_completeness < 0.40:
        decision = Decision.MANUAL_REVIEW
        result.flags.append("LOW_EVIDENCE_COMPLETENESS")

    # Override 2: Low confidence → manual review
    if result.confidence_score < CFG.manual_review_below:
        decision = Decision.MANUAL_REVIEW

    # Override 3: Package intact + claim says damaged → reject
    if "PACKAGE_INTACT" in result.flags and "damaged" in claim.claim_type.lower():
        decision = Decision.REJECT

    # Override 4: Pre-opened unboxing → reject (evidence integrity compromised)
    if "PRE_OPENED_UNBOXING" in result.flags:
        decision = Decision.REJECT

    # Override 5: High confidence approve
    if (
        decision == Decision.APPROVE.value
        and result.confidence_score >= CFG.auto_approve_confidence
        and result.evidence_completeness >= 0.70
        and not result.rejection_reasons
    ):
        decision = Decision.APPROVE

    result.final_decision = decision if isinstance(decision, str) else decision.value

    return result


# ──────────────────────────────────────────────
# MAIN PIPELINE
# ──────────────────────────────────────────────
def analyze_claim(claim: ClaimInput) -> ClaimResult:
    """
    Full analysis pipeline. Tolerates any combination of missing evidence.
    """
    log.info(f"{'='*60}")
    log.info(f"Analyzing case {claim.case_name}")
    log.info(f"{'='*60}")

    check_dependencies()
    work = Path(CFG.work_dir) / claim.case_name
    work.mkdir(parents=True, exist_ok=True)

    # ── 0. Resolve URLs to local paths ──
    packing_local = download_if_url(
        claim.packing_video, str(work / "packing_input.mp4")
    )
    unboxing_local = download_if_url(
        claim.unboxing_video, str(work / "unboxing_input.mp4")
    )

    # ── 1. Process packing video ──
    packing_report = EvidenceReport(status=EvidenceStatus.NOT_SHARED)
    packing_frames_for_llm: List[Tuple[str, float]] = []
    packing_awbs = []

    valid, msg = validate_video(packing_local)
    if valid:
        log.info(f"Packing video: {msg}")
        packing_raw = extract_frames(packing_local, str(work / "packing"))
        packing_paths = [p for p, _ in packing_raw]
        usable_paths, issues = filter_usable_frames(packing_paths)
        usable_set = set(usable_paths)
        usable_pairs = [(p, t) for p, t in packing_raw if p in usable_set]
        packing_awbs, texts = extract_awbs_from_frames(usable_paths or packing_paths[:3])

        packing_report = EvidenceReport(
            status=EvidenceStatus.SHARED if len(usable_pairs) >= CFG.min_usable_frames
                   else (EvidenceStatus.PARTIAL if usable_pairs else EvidenceStatus.INVALID),
            total_frames=len(packing_raw),
            usable_frames=len(usable_pairs),
            detected_awbs=packing_awbs,
            detected_texts=texts[:3],
            quality_issues=issues,
        )
        packing_frames_for_llm = usable_pairs or packing_raw
    else:
        log.warning(f"Packing video: {msg}")

    # ── 2. Process unboxing video ──
    unboxing_report = EvidenceReport(status=EvidenceStatus.NOT_SHARED)
    unboxing_frames_for_llm: List[Tuple[str, float]] = []
    unboxing_awbs = []

    valid, msg = validate_video(unboxing_local)
    if valid:
        log.info(f"Unboxing video: {msg}")
        unboxing_raw = extract_frames(unboxing_local, str(work / "unboxing"))
        unboxing_paths = [p for p, _ in unboxing_raw]
        usable_paths, issues = filter_usable_frames(unboxing_paths)
        usable_set = set(usable_paths)
        usable_pairs = [(p, t) for p, t in unboxing_raw if p in usable_set]
        unboxing_awbs, texts = extract_awbs_from_frames(usable_paths or unboxing_paths[:3])

        unboxing_report = EvidenceReport(
            status=EvidenceStatus.SHARED if len(usable_pairs) >= CFG.min_usable_frames
                   else (EvidenceStatus.PARTIAL if usable_pairs else EvidenceStatus.INVALID),
            total_frames=len(unboxing_raw),
            usable_frames=len(usable_pairs),
            detected_awbs=unboxing_awbs,
            detected_texts=texts[:3],
            quality_issues=issues,
        )
        unboxing_frames_for_llm = usable_pairs or unboxing_raw
    else:
        log.warning(f"Unboxing video: {msg}")

    # ── 3. LLM analysis (always runs if any frames were extracted) ──
    llm_output = None
    llm_token_usage = {}
    if packing_frames_for_llm or unboxing_frames_for_llm:
        content = build_llm_content(
            claim, packing_frames_for_llm, unboxing_frames_for_llm,
            packing_awbs, unboxing_awbs,
        )
        llm_output, llm_token_usage = call_claude(content)
    else:
        log.warning("No frames extracted from any video — skipping LLM analysis")

    # ── 4. Apply rules ──
    result = apply_decision_rules(
        llm_output, claim,
        packing_report, unboxing_report,
    )
    result.token_usage = llm_token_usage

    log.info(f"RESULT: {result.final_decision} (confidence={result.confidence_score})")
    log.info(f"Flags: {result.flags}")
    log.info(f"Rejection reasons: {result.rejection_reasons}")

    # ── 7. Cleanup ──
    shutil.rmtree(work, ignore_errors=True)

    return result


# ──────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────
if __name__ == "__main__":
    result = analyze_claim(ClaimInput(
        case_name="Tampered/Wrong/Missing RTO received",
        packing_video="https://example.com/packing.mp4",   # URL or local path
        unboxing_video="https://example.com/unboxing.mp4", # URL or local path
    ))
    print(json.dumps(asdict(result), indent=2))