"""
Transcript Analyzer API
Run: uvicorn main:app --reload --port 8001
"""
from dotenv import load_dotenv
load_dotenv("../../.env")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dataclasses import asdict
from typing import List

from analyzer import analyze_transcript

app = FastAPI(title="Transcript Analyzer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    transcript: str
    points: List[str]


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    if not req.transcript.strip():
        raise HTTPException(status_code=422, detail="transcript is required")
    if not req.points:
        raise HTTPException(status_code=422, detail="at least one point is required")
    cleaned_points = [p.strip() for p in req.points if p.strip()]
    if not cleaned_points:
        raise HTTPException(status_code=422, detail="at least one non-empty point is required")
    try:
        result = analyze_transcript(req.transcript, cleaned_points)
        return asdict(result)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
