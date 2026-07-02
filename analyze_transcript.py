"""
NDR Transcript Analyzer
=======================
Downloads a call transcript from any URL (Footwork S3 presigned, HTTP, HTTPS)
and analyzes it with Claude to validate NDR claims.
"""

import anthropic
import json
import logging
import os
import re
import tempfile
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List
from urllib.parse import urlparse

# OpenAI (audio transcription + Hinglish translation) is routed through the LiteLLM proxy.
LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "https://litellm.blitzshopdeck.in/").strip()

log = logging.getLogger("transcript_analyzer")

# ──────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT — NDR Transcript Validator
# ──────────────────────────────────────────────────────────────────────────────

TRANSCRIPT_SYSTEM_PROMPT = """You are analyzing a proof submitted by a seller to dispute an NDR
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


# ──────────────────────────────────────────────────────────────────────────────
# DATA CLASS
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class TranscriptResult:
    url: str
    timestamp: str = ""

    # Point 1 — Who initiated
    call_initiator: str = "unknown"
    call_direction: str = "unknown"

    # Point 2 — Customer wants order / delivery attempted / calls
    customer_wants_order: Optional[bool] = None
    delivery_attempted: Optional[bool] = None
    delivery_agent_called_customer: Optional[bool] = None
    customer_received_calls: Optional[bool] = None
    no_call_no_attempt: bool = False
    call_count_by_agent: Optional[str] = None

    # Point 3 — NDR mark
    ndr_reason: str = "UNKNOWN"
    ndr_correctly_marked: Optional[bool] = None
    fake_ndr_suspected: bool = False
    ndr_mark_mismatch_reason: Optional[str] = None

    # Point 4 — Product
    product_mentioned: Optional[str] = None
    order_id_mentioned: Optional[str] = None
    cod_amount_mentioned: Optional[str] = None
    product_urgency: Optional[str] = None

    # Intent & complaint
    customer_intent: str = "UNCLEAR"
    complaint_nature: str = ""

    # Additional scenario flags
    ndr_followup_confirmed_want: Optional[bool] = None
    repeat_ndr: bool = False
    rto_already_initiated: bool = False

    # Resolution
    resolution_offered: Optional[str] = None
    resolution_requested: Optional[str] = None
    recommended_action: str = "NO_ACTION"

    # Risk
    escalation_needed: bool = False
    escalation_reason: Optional[str] = None
    fraud_signals: List[str] = field(default_factory=list)
    promises_made: List[str] = field(default_factory=list)

    # Evidence
    key_quotes: dict = field(default_factory=dict)

    # Meta
    confidence_score: float = 0.0
    summary: str = ""
    language_detected: str = "unknown"
    sentiment: str = "neutral"
    call_duration_mentioned: Optional[str] = None

    # Technical
    transcript_length_chars: int = 0
    audio_transcribed: bool = False
    needs_openai_key: bool = False
    raw_transcript: str = ""
    cleaned_transcript: str = ""
    processing_errors: List[str] = field(default_factory=list)
    token_usage: dict = field(default_factory=dict)
    llm_raw_response: dict = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────────────
# DOWNLOAD
# ──────────────────────────────────────────────────────────────────────────────

def download_url(url: str) -> tuple:
    """Download URL, return (raw_bytes, content_type)."""
    req = urllib.request.Request(url, headers={"User-Agent": "LogiScan-NDR/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        content_type = resp.headers.get("Content-Type", "").lower()
        raw_bytes = resp.read()
    return raw_bytes, content_type


# ──────────────────────────────────────────────────────────────────────────────
# AUDIO DETECTION & TRANSCRIPTION
# ──────────────────────────────────────────────────────────────────────────────

_AUDIO_MIME = {
    "audio/mpeg", "audio/mp3", "audio/wav", "audio/ogg", "audio/webm",
    "audio/mp4", "audio/m4a", "audio/x-m4a", "audio/aac", "audio/flac",
    "audio/x-wav", "audio/wave", "audio/3gpp", "audio/amr",
    # video containers that carry audio
    "video/mp4", "video/quicktime", "video/x-msvideo", "video/x-matroska",
    "video/mpeg", "video/x-ms-wmv", "video/webm",
}
_AUDIO_EXT = {
    ".mp3", ".wav", ".ogg", ".webm", ".m4a", ".aac", ".flac",
    ".wma", ".3gp", ".amr", ".opus",
    # video containers
    ".mp4", ".mov", ".avi", ".mkv", ".mpeg", ".mpg",
}

# Formats OpenAI Whisper API accepts without pre-conversion
_WHISPER_NATIVE_EXT = frozenset({
    ".mp3", ".wav", ".ogg", ".webm", ".m4a", ".flac",
    ".mp4", ".mpeg", ".mpg", ".mpga", ".oga",
})


def is_audio(url: str, content_type: str, raw_bytes: bytes) -> bool:
    """Return True if the content is audio or video (needs Whisper transcription)."""
    mime = content_type.split(";")[0].strip()
    if mime in _AUDIO_MIME:
        return True
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    if ext in _AUDIO_EXT:
        return True
    # Magic bytes: ID3 (MP3), RIFF (WAV), OggS, fLaC, MP4/MOV ftyp box
    if raw_bytes[:3] == b"ID3":
        return True
    if len(raw_bytes) >= 2 and raw_bytes[0] == 0xFF and raw_bytes[1] in (0xFB, 0xFA, 0xF3, 0xF2, 0xE3):
        return True
    if raw_bytes[:4] == b"RIFF":
        return True
    if raw_bytes[:4] == b"OggS":
        return True
    if raw_bytes[:4] == b"fLaC":
        return True
    if len(raw_bytes) >= 8 and raw_bytes[4:8] == b"ftyp":
        return True  # MP4/MOV/M4A ISO base media
    return False


_OPENAI_WHISPER_MAX_BYTES = 24 * 1024 * 1024  # 24 MB — OpenAI limit is 25 MB

_WHISPER_PROMPT_HI = (
    "यह एक भारतीय ई-कॉमर्स डिलीवरी कस्टमर सपोर्ट कॉल है। "
    "This is an Indian e-commerce delivery support call. "
    "Common terms: order, delivery, NDR, courier, AWB, COD, address, pincode, reattempt, "
    "delivery boy, refused, unavailable, fake attempt, Hinglish."
)


def _is_looping(text: str) -> bool:
    """Return True if Whisper hallucinated a repetition loop."""
    words = text.split()
    if len(words) < 10:
        return False
    top_word_freq = max(words.count(w) for w in set(words)) / len(words)
    return top_word_freq > 0.4


def _extract_left_channel(raw_path: str) -> str:
    """Extract left audio channel to a 16kHz mono WAV (fallback for noisy right channel)."""
    import subprocess
    out = raw_path + "_left.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", raw_path, "-ar", "16000", "-ac", "1",
         "-af", "pan=mono|c0=FL", out],
        capture_output=True, timeout=60,
    )
    return out


def transcribe_audio(source: str, audio_bytes: bytes, content_type: str = None) -> str:
    """
    Transcribe audio/video using OpenAI gpt-4o-transcribe by sending the raw
    bytes directly (no FFmpeg pre-processing). If the transcript comes back in
    Devanagari script, translate it to natural spoken Hinglish via gpt-4o-mini;
    Hinglish/English transcripts pass through unchanged.
    source: original URL or filename — used only to derive a filename/extension.
    """
    import openai

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set in .env")

    if len(audio_bytes) > _OPENAI_WHISPER_MAX_BYTES:
        raise RuntimeError(
            f"Audio is {len(audio_bytes) // (1024*1024)} MB — OpenAI's limit is 25 MB. "
            "Please upload a shorter or more compressed clip."
        )

    # Give OpenAI a filename with a valid extension so it can infer the format.
    ext = os.path.splitext(urlparse(source).path)[1].lower()
    if ext not in _AUDIO_EXT:
        ext = ".mp3"
    filename = f"audio{ext}"

    client = openai.OpenAI(api_key=api_key, base_url=LITELLM_BASE_URL)
    log.info(f"gpt-4o-transcribe @ {LITELLM_BASE_URL}: {filename}, ct={content_type or '-'}, {len(audio_bytes) // 1024} KB")

    audio_file = (filename, audio_bytes, content_type) if content_type else (filename, audio_bytes)

    try:
        response = client.audio.transcriptions.create(
            model="gpt-4o-transcribe",
            file=audio_file,
            response_format="text",
        )
    except openai.OpenAIError as e:
        log.error(f"OpenAI audio API failed: {e}")
        raise RuntimeError(f"OpenAI transcription API failed: {e}") from e

    transcription = response if isinstance(response, str) else getattr(response, "text", "")
    if not transcription:
        raise RuntimeError("Empty transcription response received from OpenAI")

    # Only translate if Devanagari (U+0900–U+097F) is present; else pass through.
    if not any("ऀ" <= c <= "ॿ" for c in transcription):
        log.info(f"Transcription complete: {len(transcription)} chars | preview: {transcription[:150]}")
        return transcription

    log.info("Devanagari detected — translating to Hinglish via gpt-4o-mini")
    try:
        translation_response = client.responses.create(
            model="gpt-4o-mini",
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are transcribing an Indian customer service phone call. "
                        "Convert the Hindi (Devanagari) text to natural spoken Hinglish — the way Indians actually speak in everyday conversations, mixing Hindi and English words naturally. "
                        "Do NOT translate to formal English. Keep Hindi words like 'ji', 'aap', 'kal', 'theek hai', 'bhaiya', 'didi' as-is in Roman script. "
                        "Preserve the exact conversational flow, filler words, and natural speech patterns. "
                        "Return every single word — do not skip, summarize, or shorten anything."
                    ),
                },
                {"role": "user", "content": transcription},
            ],
            max_output_tokens=20000,
        )
        translated = getattr(translation_response, "output_text", None)
    except openai.OpenAIError as e:
        log.warning(f"Hinglish translation failed — returning raw Devanagari transcript: {e}")
        return transcription

    if not translated:
        log.warning("Empty translation response — returning raw Devanagari transcript")
        return transcription

    log.info(f"Transcription+translation complete: {len(translated)} chars | preview: {translated[:150]}")
    return translated


# ──────────────────────────────────────────────────────────────────────────────
# PARSE — extract readable transcript from text/JSON format
# ──────────────────────────────────────────────────────────────────────────────

def _turns_to_text(turns: list) -> str:
    lines = []
    for t in turns:
        if isinstance(t, dict):
            speaker = (t.get("speaker") or t.get("role") or
                       t.get("from") or t.get("agent") or "Speaker")
            text = (t.get("text") or t.get("content") or
                    t.get("message") or t.get("utterance") or "")
            if text:
                lines.append(f"{speaker}: {text}")
        elif isinstance(t, str):
            lines.append(t)
    return "\n".join(lines)


def bytes_to_text(raw_bytes: bytes) -> str:
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return raw_bytes.decode("latin-1")


def extract_transcript_text(raw_bytes: bytes, content_type: str) -> str:
    raw = bytes_to_text(raw_bytes)
    stripped = raw.strip()
    if stripped.startswith(("{", "[")):
        try:
            data = json.loads(stripped)
            if isinstance(data, dict):
                for key in ("transcript", "text", "content", "conversation",
                            "dialogue", "body", "message", "data"):
                    val = data.get(key)
                    if isinstance(val, str) and len(val) > 30:
                        return val
                for key in ("turns", "messages", "utterances", "segments",
                            "conversation_turns", "entries"):
                    val = data.get(key)
                    if isinstance(val, list):
                        return _turns_to_text(val)
                return json.dumps(data, ensure_ascii=False, indent=2)
            elif isinstance(data, list):
                return _turns_to_text(data)
        except json.JSONDecodeError:
            pass
    return raw


# ──────────────────────────────────────────────────────────────────────────────
# LLM CALL
# ──────────────────────────────────────────────────────────────────────────────

MAX_CHARS = 40_000  # keep well within input token budget


def clean_and_translate_transcript(raw_text: str) -> str:
    """
    Use Claude Haiku to fix Whisper transcription errors, add speaker labels,
    and produce an English translation alongside the original.
    This runs before the main NDR analysis to dramatically improve accuracy.
    """
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": (
                "You are a transcript cleaning expert for Indian e-commerce customer support calls.\n\n"
                "The text below is a raw speech-to-text output from an Indian call recording (Hindi/Hinglish/English). "
                "It was auto-generated and may have errors like wrong words, missing punctuation, mixed scripts, "
                "or garbled Hindi romanization.\n\n"
                "Please:\n"
                "1. Fix obvious transcription errors (e.g. 'पून नमबर' → 'फोन नंबर', 'अड्रेश' → 'address/पता')\n"
                "2. Add speaker labels: Agent: / Customer: wherever you can identify them\n"
                "3. After the cleaned version, add a section '=== English Translation ===' with a full English translation\n"
                "4. Keep the format clean and readable\n\n"
                "Do NOT summarize or omit anything — preserve every detail.\n\n"
                f"RAW TRANSCRIPT:\n{raw_text}\n\n"
                "Return ONLY the cleaned transcript + English translation. No extra commentary."
            )
        }]
    )
    return resp.content[0].text.strip()


def call_claude(transcript_text: str, system_prompt: str = None) -> tuple:
    client = anthropic.Anthropic()
    truncated = transcript_text[:MAX_CHARS]
    user_msg = (
        "Analyze this customer support call transcript according to your instructions.\n\n"
        f"TRANSCRIPT:\n{truncated}\n\nEND OF TRANSCRIPT\n\n"
        "Respond with ONLY the JSON object defined in your instructions. "
        "No markdown fences, no explanation, no text before or after the JSON."
    )

    for attempt in range(3):
        try:
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=8192,
                system=system_prompt or TRANSCRIPT_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )

            log.info(f"Attempt {attempt+1}: stop_reason={resp.stop_reason}, blocks={len(resp.content)}")

            # Pull text from whichever block has it
            raw = ""
            for block in resp.content:
                text = getattr(block, "text", None)
                if text:
                    raw = text.strip()
                    break

            log.info(f"Raw response ({len(raw)} chars): {raw[:300]}")

            if not raw:
                log.warning(f"Empty response (stop_reason={resp.stop_reason}), retrying")
                continue

            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw.strip())

            parsed = json.loads(raw)
            usage = {
                "input_tokens": resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
                "total_tokens": resp.usage.input_tokens + resp.usage.output_tokens,
            }
            log.info(f"LLM OK — tokens: {usage['total_tokens']}")
            return parsed, usage

        except json.JSONDecodeError as e:
            log.error(f"Attempt {attempt+1} non-JSON: {e} | raw[:500]={raw[:500] if raw else 'empty'}")
        except Exception as e:
            log.error(f"Attempt {attempt+1} error: {type(e).__name__}: {e}")

    return None, {}


# ──────────────────────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ──────────────────────────────────────────────────────────────────────────────

def _run_pipeline(
    result: TranscriptResult,
    raw_bytes: bytes,
    source_id: str,
    content_type: str,
    custom_prompt: str = None,
) -> TranscriptResult:
    """Core pipeline shared by URL and direct-upload paths."""

    # 1. Audio/video → Whisper; text → parse directly
    if is_audio(source_id, content_type, raw_bytes):
        log.info("Audio/video file detected — routing to OpenAI Whisper API")
        try:
            text = transcribe_audio(source_id, raw_bytes, content_type)
            result.audio_transcribed = True
            result.raw_transcript = text
            result.transcript_length_chars = len(text)
        except Exception as e:
            result.processing_errors.append(f"Audio transcription failed: {e}")
            return result
    else:
        try:
            text = extract_transcript_text(raw_bytes, content_type)
            result.raw_transcript = text
            result.transcript_length_chars = len(text)
        except Exception as e:
            result.processing_errors.append(f"Parse failed: {e}")
            text = bytes_to_text(raw_bytes)
            result.raw_transcript = text
            result.transcript_length_chars = len(text)

    if result.transcript_length_chars < 5:
        result.processing_errors.append(
            "Transcript is empty — audio may be silent or the format is unsupported. "
            "Check API logs for Whisper output details."
        )
        return result

    # 2. Clean + translate via Claude Haiku
    try:
        log.info("Cleaning and translating transcript via Claude Haiku…")
        cleaned = clean_and_translate_transcript(text)
        result.cleaned_transcript = cleaned
        log.info(f"Cleaned transcript: {len(cleaned)} chars | preview: {cleaned[:120]}")
        text = cleaned
    except Exception as e:
        log.warning(f"Transcript cleaning failed (continuing with raw): {e}")
        result.cleaned_transcript = text

    # 3. NDR analysis via Claude
    llm, usage = call_claude(text, system_prompt=custom_prompt)
    result.token_usage = usage

    if not llm:
        result.processing_errors.append("LLM analysis failed")
        return result

    result.llm_raw_response = llm

    result.call_initiator = llm.get("call_initiator", "unknown")
    result.call_direction = llm.get("call_direction", "unknown")

    result.customer_wants_order = llm.get("customer_wants_order")
    result.delivery_attempted = llm.get("delivery_attempted")
    result.delivery_agent_called_customer = llm.get("delivery_agent_called_customer")
    result.customer_received_calls = llm.get("customer_received_calls")
    result.no_call_no_attempt = bool(llm.get("no_call_no_attempt", False))
    result.call_count_by_agent = llm.get("call_count_by_agent")

    result.ndr_reason = llm.get("ndr_reason", "UNKNOWN")
    result.ndr_correctly_marked = llm.get("ndr_correctly_marked")
    result.fake_ndr_suspected = bool(llm.get("fake_ndr_suspected", False))
    result.ndr_mark_mismatch_reason = llm.get("ndr_mark_mismatch_reason")

    result.product_mentioned = llm.get("product_mentioned")
    result.order_id_mentioned = llm.get("order_id_mentioned")
    result.cod_amount_mentioned = llm.get("cod_amount_mentioned")
    result.product_urgency = llm.get("product_urgency")

    result.customer_intent = llm.get("customer_intent", "UNCLEAR")
    result.complaint_nature = llm.get("complaint_nature", "")

    result.ndr_followup_confirmed_want = llm.get("ndr_followup_confirmed_want")
    result.repeat_ndr = bool(llm.get("repeat_ndr", False))
    result.rto_already_initiated = bool(llm.get("rto_already_initiated", False))

    result.resolution_offered = llm.get("resolution_offered")
    result.resolution_requested = llm.get("resolution_requested")
    result.recommended_action = llm.get("recommended_action", "NO_ACTION")

    result.escalation_needed = bool(llm.get("escalation_needed", False))
    result.escalation_reason = llm.get("escalation_reason")
    result.fraud_signals = llm.get("fraud_signals", [])
    result.promises_made = llm.get("promises_made", [])

    result.key_quotes = llm.get("key_quotes", {})

    result.confidence_score = float(llm.get("confidence_score", 0.0))
    result.summary = llm.get("summary", "")
    result.language_detected = llm.get("language_detected", "unknown")
    result.sentiment = llm.get("sentiment", "neutral")
    result.call_duration_mentioned = llm.get("call_duration_mentioned")

    return result


def analyze_transcript(url: str, custom_prompt: str = None) -> TranscriptResult:
    result = TranscriptResult(url=url, timestamp=datetime.now(timezone.utc).isoformat())
    try:
        raw_bytes, content_type = download_url(url)
        log.info(f"Downloaded {len(raw_bytes)} bytes, content-type: {content_type}")
    except Exception as e:
        result.processing_errors.append(f"Download failed: {e}")
        return result
    return _run_pipeline(result, raw_bytes, url, content_type, custom_prompt)


def analyze_transcript_from_bytes(
    raw_bytes: bytes,
    filename: str,
    content_type: str = "",
    custom_prompt: str = None,
) -> TranscriptResult:
    """Analyze a file supplied as raw bytes (direct upload path)."""
    result = TranscriptResult(url=filename, timestamp=datetime.now(timezone.utc).isoformat())
    return _run_pipeline(result, raw_bytes, filename, content_type, custom_prompt)
