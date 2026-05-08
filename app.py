"""
LogiScan API — FastAPI wrapper around analyze_claim()
Run: uvicorn app:app --reload --port 8000
"""
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dataclasses import asdict
import logging

from analyize_videos import ClaimInput, analyze_claim
from analyze_transcript import analyze_transcript, TranscriptResult, TRANSCRIPT_SYSTEM_PROMPT

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
