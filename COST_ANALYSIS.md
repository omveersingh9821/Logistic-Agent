# LogiScan Video Analysis — Cost Analysis

## System Overview

LogiScan uses **Claude Sonnet 4.6** (`claude-sonnet-4-6`) to analyze packing and unboxing video frames for logistics damage claims. The pipeline extracts up to **20 frames per video** (anchor + scene-change frames, deduplicated), encodes them as base64 JPEG images, and sends them alongside a structured system prompt to Claude for multimodal analysis.

---

## Pricing Reference — Claude Sonnet 4.6

| Token Type    | Price per 1M tokens |
|---------------|---------------------|
| Input tokens  | $3.00               |
| Output tokens | $15.00              |

---

## How Tokens Are Counted

### Image tokens
Frames are extracted at **1280 × 720 px** (16:9 video, `scale=1280:-1` in ffmpeg) and capped at 1568 px on the longest side before encoding.

```
Image tokens ≈ (width × height) / 750
             = (1280 × 720) / 750
             ≈ 1,229 tokens per frame
```

### Text tokens (fixed per call)
| Component                            | Approx. tokens |
|--------------------------------------|----------------|
| System prompt (SYSTEM_PROMPT const)  | ~1,500         |
| Case ID + evidence summary + OCR AWBs| ~400           |
| Per-frame timestamp labels           | ~10 each       |
| Analysis JSON template / request     | ~500           |

---

## Example 1 — Full Evidence: Both Videos Available (Damaged Item Claim)

**Scenario:** A customer claims a gold necklace arrived broken. Both packing and unboxing videos are provided.

| Video         | Duration | Anchor frames | Scene frames | After dedup | Sent to LLM |
|---------------|----------|---------------|--------------|-------------|-------------|
| Packing       | 60s      | 11            | 9            | 15          | 15          |
| Unboxing      | 45s      | 11            | 9            | 13          | 13          |
| **Total**     |          |               |              |             | **28**      |

### Input token breakdown

| Component                            | Tokens          |
|--------------------------------------|-----------------|
| System prompt                        | 1,500           |
| Context text (case ID, AWBs, labels) | 400             |
| Frame images (28 × 1,229)            | 34,412          |
| Per-frame labels (28 × 10)           | 280             |
| Analysis JSON template               | 500             |
| **Total input**                      | **37,092**      |

### Output token breakdown

Claude returns a fully populated JSON with all damage fields (product_match, break_details, AWB chain, frame_descriptions, conclusion, etc.).

| Component              | Tokens      |
|------------------------|-------------|
| JSON response          | ~1,500      |
| **Total output**       | **~1,500**  |

### Cost

| Token type | Tokens | Rate           | Cost      |
|------------|--------|----------------|-----------|
| Input      | 37,092 | $3.00 / 1M     | **$0.111**|
| Output     | 1,500  | $15.00 / 1M    | **$0.023**|
| **Total**  |        |                | **$0.134**|

> With the configured `llm_retries = 3`, worst-case cost per claim (all retries triggered):
> **3 × $0.134 = $0.402**

---

## Example 2 — Partial Evidence: Only Unboxing Video Available (Missing Item Claim)

**Scenario:** A customer claims the box arrived empty. No packing video was recorded. Only the unboxing video is available.

| Video         | Duration | Anchor frames | Scene frames | After dedup | Sent to LLM |
|---------------|----------|---------------|--------------|-------------|-------------|
| Packing       | N/A      | 0             | 0            | 0           | 0           |
| Unboxing      | 120s     | 11            | 9            | 18          | 18          |
| **Total**     |          |               |              |             | **18**      |

The system automatically detects the missing packing video, sets `packing_evidence.status = NOT_SHARED`, adds the `NO_PACKING_VIDEO` flag, and adapts the LLM prompt to skip packing-side fields.

### Input token breakdown

| Component                            | Tokens      |
|--------------------------------------|-------------|
| System prompt                        | 1,500       |
| Context text (reduced — no packing)  | 300         |
| Frame images (18 × 1,229)            | 22,122      |
| Per-frame labels (18 × 10)           | 180         |
| Analysis JSON template (adapted)     | 400         |
| **Total input**                      | **24,502**  |

### Output token breakdown

Claude returns a shorter JSON — many fields are set to `not_assessed_no_packing_video`, so the output is leaner.

| Component              | Tokens      |
|------------------------|-------------|
| JSON response          | ~800        |
| **Total output**       | **~800**    |

### Cost

| Token type | Tokens | Rate           | Cost       |
|------------|--------|----------------|------------|
| Input      | 24,502 | $3.00 / 1M     | **$0.074** |
| Output     | 800    | $15.00 / 1M    | **$0.012** |
| **Total**  |        |                | **$0.086** |

> Worst-case with 3 retries: **3 × $0.086 = $0.258**

---

## Side-by-Side Comparison

| Metric                     | Example 1 (Full Evidence) | Example 2 (Unboxing Only) |
|----------------------------|--------------------------|--------------------------|
| Frames sent                | 28                       | 18                       |
| Input tokens               | 37,092                   | 24,502                   |
| Output tokens              | ~1,500                   | ~800                     |
| **Cost per claim**         | **$0.134**               | **$0.086**               |
| Worst-case (3 retries)     | $0.402                   | $0.258                   |
| Decision quality           | High (can cross-compare) | Medium (no baseline)     |
| Auto-decision possible     | Yes (if conf ≥ 0.85)     | Manual review likely     |

---

## Volume Cost Projections

Assumes a realistic **70/30 split** between full-evidence (Ex 1) and partial-evidence (Ex 2) claims, with an average of **1.1 LLM calls per claim** (occasional single retry).

| Claims / Month | Avg cost / claim | Monthly Cost  |
|----------------|------------------|---------------|
| 100            | ~$0.118          | **~$12**      |
| 1,000          | ~$0.118          | **~$118**     |
| 5,000          | ~$0.118          | **~$590**     |
| 10,000         | ~$0.118          | **~$1,180**   |
| 50,000         | ~$0.118          | **~$5,900**   |

---

## Cost Drivers & Levers

### What increases cost
| Factor                          | Impact                                        |
|---------------------------------|-----------------------------------------------|
| More frames per video           | Each extra frame adds ~$0.004 to input cost   |
| Higher image resolution         | Tokens scale with pixel area — avoid >1568px  |
| LLM retries (JSON parse errors) | Up to 3× multiplier on per-call cost          |
| Longer output (verbose JSON)    | Output cost at $15/1M is 5× input rate        |

### Optimization opportunities
| Change                                      | Estimated saving      |
|---------------------------------------------|-----------------------|
| Reduce `max_frames_per_video` from 20 → 12  | ~40% fewer image tokens|
| Lower JPEG quality 85 → 70                  | Minor (same token count)|
| Cache system prompt (prompt caching)        | ~$0.020 saved/call on repeated prompt |
| Skip LLM when both videos invalid           | Avoid full call cost  |
| Use Haiku 4.5 for low-confidence re-check   | $0.80/$4 vs $3/$15    |

### Prompt caching (recommended)
The `SYSTEM_PROMPT` is ~1,500 tokens and identical across every call. Enabling Anthropic prompt caching would reduce repeated system-prompt charges from **$3.00/1M → $0.30/1M** on cache hits.

Estimated saving at 1,000 claims/month:
```
1,500 tokens × 1,000 calls × ($3.00 - $0.30) / 1,000,000
= $4.05 saved/month (~3.4% of total bill)
```

---

## Key Configuration Values (from `analyize_videos.py`)

```python
model                   = "claude-sonnet-4-6"
max_frames_per_video    = 20      # hard cap per video
max_tokens (LLM output) = 16,000  # ceiling; typical use ~800–1,500
llm_retries             = 3       # max retry attempts on JSON parse failure
MAX_IMAGE_DIM           = 1568    # px — images rescaled before encoding
JPEG quality            = 85      # controlled in encode_image_b64()
```
