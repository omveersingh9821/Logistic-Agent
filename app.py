"""
LogiScan API — FastAPI wrapper around analyze_claim()
Run: uvicorn app:app --reload --port 8000
"""
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
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

DEFAULT_IMAGE_PROMPT = """You are a logistics and e-commerce visual analyst. Analyze this image carefully and provide:

1. **What's shown** — describe the image contents clearly
2. **Package / product condition** — intact, damaged, sealed, open, tampered?
3. **Visible text / labels** — any order ID, AWB, barcode, address, or brand visible
4. **Delivery or claims relevance** — any evidence useful for NDR validation, damage claims, or proof of delivery
5. **Overall assessment** — is this image consistent with a legitimate delivery attempt?

Be specific and factual. Flag any anomalies."""

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

        client = anthropic.Anthropic()
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
