"""
Transcript Analyzer — uses Claude to validate checklist points against a transcript
"""

import anthropic
import json
import os
from dataclasses import dataclass, field
from typing import List

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM_PROMPT = """You are an expert conversation analyst. You will be given a transcript and a list of points to validate.

For each point, determine whether it is satisfied (positive) or not satisfied (negative) based solely on the transcript content.

Respond ONLY with valid JSON in this exact format:
{
  "results": [
    {
      "point": "<exact point text>",
      "status": "positive" or "negative",
      "evidence": "<brief quote or explanation from the transcript, or 'Not found' if negative>"
    }
  ],
  "summary": "<2-3 sentence overall summary of the transcript and how well it met the criteria>"
}"""


@dataclass
class PointResult:
    point: str
    status: str  # "positive" | "negative"
    evidence: str


@dataclass
class AnalysisResult:
    results: List[PointResult] = field(default_factory=list)
    summary: str = ""
    positive_count: int = 0
    negative_count: int = 0


def analyze_transcript(transcript: str, points: List[str]) -> AnalysisResult:
    if not transcript.strip():
        raise ValueError("Transcript cannot be empty")
    if not points:
        raise ValueError("At least one point is required")

    points_list = "\n".join(f"{i+1}. {p}" for i, p in enumerate(points))
    user_message = f"""TRANSCRIPT:
{transcript}

POINTS TO VALIDATE:
{points_list}

Analyze the transcript and validate each point."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    data = json.loads(raw)

    point_results = [
        PointResult(
            point=r["point"],
            status=r["status"],
            evidence=r.get("evidence", ""),
        )
        for r in data["results"]
    ]

    positive = sum(1 for r in point_results if r.status == "positive")
    negative = len(point_results) - positive

    return AnalysisResult(
        results=point_results,
        summary=data.get("summary", ""),
        positive_count=positive,
        negative_count=negative,
    )
