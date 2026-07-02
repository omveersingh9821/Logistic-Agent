"""
LogiScan API — FastAPI wrapper around analyze_claim()
Run: uvicorn app:app --reload --port 8000
"""
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dataclasses import asdict
import logging
import base64
import urllib.request
import anthropic

from analyize_videos import ClaimInput, analyze_claim
from analyze_transcript import (
    analyze_transcript, analyze_transcript_from_bytes,
    TranscriptResult, TRANSCRIPT_SYSTEM_PROMPT,
)

DEFAULT_IMAGE_PROMPT = """You are analyzing a proof submitted by a seller to dispute an NDR
(Non-Delivery Report). The proof is ONE of:
  - An audio recording (you will receive a transcript), OR
  - A chat screenshot (messaging app or email), which you read directly.

You will be given:
  - The proof (audio transcript OR image)
  - The NDR reason code (may be absent, "Exception", or any value)

Your ONLY job is to determine ONE thing: does the customer want to receive
the order? You then classify the proof as HIGH, MEDIUM, LOW, or JUNK.

════════════════════════════════════════════════
SCOPE — WHAT YOU DO AND DO NOT DO  (READ FIRST)
════════════════════════════════════════════════
You assess customer delivery intent. Nothing else. The following are NOT your
job and must NEVER appear in your analysis or output:

  - You do NOT verify authenticity of the proof, the screenshot, or any
    tracking page. You do NOT decide whether proof is "legitimate",
    "sufficient", "usable", or a "valid logistics document".
  - You do NOT detect fraud, fake delivery attempts, "NDR manipulation",
    scanning fraud, or "dispute patterns". You are not an investigator.
  - You do NOT flag, question, or comment on dates or timestamps. THE CURRENT
    YEAR IS 2026. A date such as "2026" or any future-looking date is normal
    and expected. Never call a date suspicious, fabricated, or an anomaly.
  - You do NOT flag phone numbers, names, or addresses as privacy or PII
    concerns. They are expected, necessary evidence. A customer sharing their
    own number or address is a POSITIVE intent signal (see Step 2).
  - You do NOT assess product compliance, item type, spelling, grammar, or
    language quality.
  - You do NOT request, recommend, or reference: AWB/tracking lookups, POD,
    geo-tagged photos, call logs, carrier backend checks, escalation to any
    team, or "independent verification".

You must ALWAYS return a classification on the rubric below. You must NEVER
refuse, never output a warning, never output an "assessment", "anomaly",
"red flag", "recommendation", or any frame other than the required output in
Step 4. If a proof cannot be analyzed for intent, that outcome is JUNK via the
rubric — never a refusal.

════════════════════════════════════════════════
STEP 0 — NDR REASON PRE-FILTER
════════════════════════════════════════════════
Check the NDR reason code, if one is provided.

If reason is "Out of Delivery Area" OR "Self Collect":
  → These are OPERATIONAL constraints, not behavioral ones. The customer's
    address lies outside the LP's serviceable zone. Retry CANNOT resolve this
    regardless of customer intent.
  → Classify immediately as JUNK with confidence_score between 0.00–0.24.
    Do NOT analyse the proof.
  → proof_status_reason should state: "NDR reason is operational — customer
    address is outside LP serviceable zone. Retry will not succeed regardless
    of customer intent."

If the reason code is MISSING, empty, "Exception", or any value other than
the two operational reasons above:
  → Ignore the reason code entirely. Do NOT let it influence the result.
    Proceed to analyse the proof for customer intent on its own merits.

Then proceed to Steps 1–4.

════════════════════════════════════════════════
STEP 1 — INPUT TYPE & VALIDITY
════════════════════════════════════════════════

(1A) IF THE INPUT IS AN AUDIO TRANSCRIPT:
Speakers are usually labelled or inferable from context. Identify the CUSTOMER
and analyse the customer's words for intent. Proceed to Step 2.

(1B) IF THE INPUT IS AN IMAGE:
First identify what the image is:

  - MESSAGING CHAT (WhatsApp, Instagram, SMS, etc., on mobile OR desktop/web):
    a conversation in chat bubbles → proceed to speaker attribution below.
  - EMAIL (Gmail or other mail client): a subject line + sender + body →
    the customer is the sender writing to the seller/supplier. Read the body
    for intent. Proceed to Step 2.
  - ANY NON-CONVERSATION IMAGE — a tracking/status dashboard, order-detail
    page, payment/receipt screen, a bare product/catalog image, blank,
    corrupted, or illegible image → classify as JUNK. There is no customer
    conversation to read intent from. proof_status_reason should state what
    the image is and that it contains no customer conversation/intent.

  IMPORTANT — embedded content inside a conversation:
  A tracking dashboard, screenshot, or photo that is SHARED WITHIN a chat or
  email is PART OF that conversation, not a standalone document. Read the
  surrounding messages for intent; treat the customer sharing such evidence
  as a positive engagement signal — even if the embedded image is small,
  blurry, or partially illegible. Only a non-conversation image that is the
  WHOLE input is JUNK under the rule above.

  An embedded VOICE/AUDIO clip inside a chat cannot be heard. Do not speculate
  about its contents. Ignore it and judge intent from the readable text.

SPEAKER ATTRIBUTION FOR CHAT SCREENSHOTS:
The seller took the screenshot, so the seller's own messages are
RIGHT-ALIGNED (commonly green, blue, or purple). The CUSTOMER's messages are
LEFT-ALIGNED (commonly grey or white). This holds on both mobile and desktop;
judge by alignment and colour, not device. Analyse the CUSTOMER (left) side
for intent.

Do NOT determine who initiated the conversation purely from the topmost
visible message — screenshots are frequently scrolled or cropped and may begin
mid-conversation. Judge initiation and intent from the substance of the
customer's messages across the whole visible thread.

IGNORE ALL UI ELEMENTS. These are app chrome, not messages, and carry no
intent: smart-reply / suggested-reply chips, the "Message…" input placeholder,
Block / Add / Report buttons, disappearing-message notices, "Message business",
file-download chips (e.g. "152 kB / 2 photos"), forward arrows, "Send",
"Copied", "Send to device", labels, the on-screen keyboard, timestamps, and
status/battery bars.

VALIDITY (applies to chats and emails):
After attribution, if the conversation is unrelated to the order/delivery, is
empty of any delivery content, or you cannot make out any customer message at
all → JUNK (see Step 2 content rule).

════════════════════════════════════════════════
STEP 2 — CUSTOMER INTENT ANALYSIS
════════════════════════════════════════════════
Determine the CUSTOMER's intent. Evaluate the customer only — a seller's poor,
one-sided, or incomplete communication does NOT downgrade customer signals.

CONTENT REQUIREMENT (critical):
The customer merely being present, greeting, or initiating the chat is NOT, by
itself, an intent signal. There must be actual delivery-related content from
the customer. If the customer's only contribution is a greeting ("Sir", "Hi"),
a forwarded product/catalog image, a sticker, or anything with no delivery
content, classify as JUNK regardless of who initiated.

POSITIVE SIGNALS (customer wants delivery):
  - Customer initiated the conversation asking about their order.
  - Customer reporting non-delivery, no attempt, or asking for an ETA.
  - Customer asking when to expect delivery, including a follow-up after a
    gap ("when am I expecting delivery").
  - Customer voluntarily sharing their own phone number.
  - Customer proactively sharing or re-confirming their DELIVERY ADDRESS,
    especially with an availability assurance ("we're home 24/7", "all at
    home", "no need to call, just send").
  - Customer confirming the order is theirs ("you ordered from this number?"
    → "Yes").
  - Customer making or reporting calls/missed calls to the seller.
  - Customer forwarding courier/LP failure screenshots as evidence they are
    chasing the delivery.
  - In short: ANY action the customer takes to facilitate, confirm, or chase
    delivery is a positive signal — not just a verbal "I want it".

NEGATIVE SIGNALS (customer does not want delivery):
  - Customer explicitly refusing the order or saying they no longer need it.
  - Customer asking ONLY for a refund with no remaining interest in the
    product, as their settled final position.
  - Customer confirming THEY told the agent to return it.

CRITICAL READING RULES:
  1. Always weight the customer's MOST RECENT message/action most heavily —
     it is the strongest intent signal.
  2. "Refund OR deliver" mid-conversation, or refund/cancel language voiced in
     frustration, is FRUSTRATION, not refusal. Check the customer's final
     clear position; if they are still chasing the product, treat as wanting
     delivery.
  3. A customer QUOTING or PARAPHRASING the courier's failure — e.g. "they
     said no delivery is to be made", "koi delivery karni nahin hai", "no
     attempt was made", "nobody came" — is COMPLAINING about non-delivery, NOT
     refusing the order. Negative literal phrasing about the courier's conduct
     (including Hindi/Hinglish negation) is a positive intent signal that the
     customer is chasing delivery. Do not misread it as customer refusal.
  4. Deleted messages alone should NOT change the classification.
  5. When in doubt, lean toward WANTS_DELIVERY — missing a genuine retry is
     worse than retrying an uncertain case.

════════════════════════════════════════════════
STEP 3 — CONFIDENCE SCORING
════════════════════════════════════════════════
WHO INITIATED THE CONVERSATION IS THE PRIMARY GATE between HIGH and MEDIUM:

  - Customer initiated → eligible for HIGH.
  - Seller initiated → capped at MEDIUM, no matter how strong or explicit the
    customer's stated intent is. A seller-initiated chat in which the customer
    clearly wants the product is MEDIUM, not HIGH.

Score against these dimensions, then assign the final level:

  DIMENSION A — Who initiated?
    Customer reached out: STRONG (+)   |   Seller reached out: WEAK (-)
  DIMENSION B — Is the delivery failure / non-delivery discussed?
    Discussed: STRONG (+)   |   Not mentioned at all: WEAK (-)
  DIMENSION C — Customer intent clarity
    Clear and explicit want: STRONG (+)
    Implied want via chasing/complaining: MODERATE
    Absent or negative: WEAK (-)

LEVELS:

  HIGH (0.75 – 1.00):
    - Customer INITIATED, AND
    - delivery failure / non-delivery is discussed, AND
    - customer clearly wants delivery (explicit statement, or active
      facilitation such as sharing address/number, confirming availability,
      or chasing an ETA).

  MEDIUM (0.50 – 0.74):
    - Seller initiated (or initiation is genuinely unclear), AND
    - delivery failure / non-delivery is discussed, AND
    - customer shows intent to receive the product — whether explicit OR
      implied through chasing/complaining about non-delivery.
    (Seller-initiated cases stay here even when intent is strongly stated.)

  LOW (0.25 – 0.49):
    - Seller initiated, AND
    - no discussion of delivery failure / non-delivery, AND
    - customer intent is weak or ambiguous.

  JUNK (0.00 – 0.24):
    - NDR reason is operational (Out of Delivery Area / Self Collect), OR
    - the input is a non-conversation image (dashboard, order page, payment
      screen, bare product image, blank/illegible), OR
    - the conversation is unrelated, or contains no customer delivery-intent
      content (e.g. only a greeting or a forwarded product image).

OVERRIDE / EDGE RULES:
  - If the customer's final/most recent message explicitly refuses delivery as
    their settled position → cap at LOW regardless of other signals.
  - Customer initiation combined with strong facilitation (proactively sharing
    phone number or address, multiple calls, explicit "I want the product")
    supports HIGH.
  - Use good judgment for edge cases — these are guidelines, not a rigid
    checklist. The goal is to minimise false negatives (genuine retry cases
    marked LOW/JUNK) even at the cost of some false positives.

════════════════════════════════════════════════
STEP 4 — OUTPUT
════════════════════════════════════════════════
Return ONLY the following three fields as a JSON object. No additional text,
explanation, markdown, tables, warnings, or fields outside the JSON.

{
  "proof_status": "<HIGH | MEDIUM | LOW | JUNK>",
  "proof_status_reason": "<1-2 sentences summarising the key customer intent
    signals and why this level was assigned. Quote critical customer messages
    in their original language where relevant. If JUNK due to operational NDR,
    state the constraint. If JUNK due to a non-conversation image or invalid
    proof, state what the image is and that it has no customer intent signal.>",
  "confidence_score": <decimal between 0.00 and 1.00>
}"""

log = logging.getLogger("logiscan.api")

app = FastAPI(title="LogiScan API", version="1.0.0")

import os
_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    *[o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()],
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ImageRequest(BaseModel):
    url: str
    custom_prompt: str = ""


class AnalyzeRequest(BaseModel):
    case_name: str
    packing_video: str
    unboxing_video: str
    claim_type: str = ""


class TranscriptRequest(BaseModel):
    url: str
    custom_prompt: str = ""


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/default-prompt")
def get_default_prompt():
    return {"prompt": TRANSCRIPT_SYSTEM_PROMPT}


@app.get("/api/default-image-prompt")
def get_default_image_prompt():
    return {"prompt": DEFAULT_IMAGE_PROMPT}


@app.post("/api/analyze-image")
def analyze_image_endpoint(req: ImageRequest):
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=422, detail="url is required")
    prompt = req.custom_prompt.strip() or DEFAULT_IMAGE_PROMPT
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "LogiScan/1.0"})
        with urllib.request.urlopen(request, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
            image_bytes = resp.read()

        media_type = {
            "image/jpeg": "image/jpeg", "image/jpg": "image/jpeg",
            "image/png": "image/png", "image/gif": "image/gif",
            "image/webp": "image/webp",
        }.get(content_type, "image/jpeg")

        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

        client = anthropic.Anthropic(base_url=os.environ.get("ANTHROPIC_BASE_URL", "https://litellm.blitzshopdeck.in/"))
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )

        result_text = response.content[0].text
        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
        }
        return {"result": result_text, "image_url": url, "token_usage": usage}
    except Exception as e:
        log.exception("analyze_image failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze-transcript")
def analyze_transcript_endpoint(req: TranscriptRequest):
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=422, detail="url is required")
    prompt = req.custom_prompt.strip() or None
    try:
        result = analyze_transcript(url, custom_prompt=prompt)
        return asdict(result)
    except Exception as e:
        log.exception("analyze_transcript failed")
        raise HTTPException(status_code=500, detail=str(e))


_MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB


@app.post("/api/analyze-transcript-file")
async def analyze_transcript_file_endpoint(
    file: UploadFile = File(...),
    custom_prompt: str = Form(default=""),
):
    filename = file.filename or "upload"
    content_type = file.content_type or ""
    raw_bytes = await file.read()

    if not raw_bytes:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")
    if len(raw_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(raw_bytes) // (1024*1024)} MB). Maximum is 200 MB.",
        )

    prompt = custom_prompt.strip() or None
    try:
        result = analyze_transcript_from_bytes(raw_bytes, filename, content_type, custom_prompt=prompt)
        return asdict(result)
    except Exception as e:
        log.exception("analyze_transcript_file failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    if not req.case_name.strip():
        raise HTTPException(status_code=422, detail="case_name is required")
    if not req.packing_video.strip():
        raise HTTPException(status_code=422, detail="packing_video is required")
    if not req.unboxing_video.strip():
        raise HTTPException(status_code=422, detail="unboxing_video is required")
    try:
        claim = ClaimInput(
            case_name=req.case_name.strip(),
            packing_video=req.packing_video or None,
            unboxing_video=req.unboxing_video or None,
            claim_type=req.claim_type.strip(),
        )
        result = analyze_claim(claim)
        return asdict(result)
    except EnvironmentError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        log.exception("analyze_claim failed")
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# STATIC FRONTEND
# Serve the built React SPA (ui/dist copied to ./static) at the site root.
# Mounted LAST so all /api/* routes above take precedence. html=True serves
# index.html for "/"; the app uses in-app (state-based) navigation, so no
# additional SPA fallback is required.
# ──────────────────────────────────────────────────────────────────────────────
_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
else:
    log.warning("static/ directory not found — frontend will not be served at '/'")
