#!/usr/bin/env python3
"""
CareOps live demo API.

This is a thin product layer, not a rewrite: every endpoint below imports
and calls the SAME model/*.py functions the offline pipeline (run.py) uses
to produce dashboard/index.html. Nothing about the risk model, the
extraction logic, or the Recovery Score engine is reimplemented here.

Run locally:
    pip install -r requirements.txt
    uvicorn main:app --reload

Deploy: see render.yaml. Render runs
    uvicorn main:app --host 0.0.0.0 --port $PORT
"""
import json
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "model"
DASHBOARD_DIR = BASE_DIR / "dashboard"

# model/*.py files do bare `from sibling_module import x` (e.g.
# hybrid_extraction.py does `from communication_intelligence import
# extract_intent`), the same way run.py handles it by setting
# cwd=MODEL_DIR for each subprocess. A long-lived FastAPI process can't use
# cwd the same way, so MODEL_DIR goes on sys.path instead -- same effect,
# no change to any model file's own imports.
sys.path.insert(0, str(MODEL_DIR))

from hybrid_extraction import extract_intent_hybrid  # noqa: E402
from capacity_recovery import recommend as recovery_recommend  # noqa: E402
from reschedule_agent import propose_reschedule  # noqa: E402

app = FastAPI(title="CareOps Live Demo API")


class AnalyzeRequest(BaseModel):
    message: str


class RecoverRequest(BaseModel):
    appointment_id: str
    target_date: str
    service_type: Optional[str] = None


class RescheduleRequest(BaseModel):
    appointment_id: str
    message: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/operations")
def get_operations():
    """
    Today's simulated operations summary + flagged list, read straight from
    model/dashboard_data.json -- the same file generate_dashboard_data.py
    writes and dashboard/index.html embeds statically. This just serves it
    fresh over HTTP instead of requiring a re-run of the HTML file.
    """
    path = MODEL_DIR / "dashboard_data.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="model/dashboard_data.json not found -- run `python run.py` once to generate it.",
        )
    return json.loads(path.read_text())


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    """
    Rule-first hybrid intent extraction on a live message -- calls
    hybrid_extraction.extract_intent_hybrid() with its own default LLM
    fallback (Gemini if GEMINI_API_KEY is set, else Anthropic if
    ANTHROPIC_API_KEY is set, else the message escalates to a human rather
    than being guessed at -- see model/hybrid_extraction.py's
    default_llm_call()).
    """
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="message is required")
    return extract_intent_hybrid(req.message)


@app.post("/api/recover")
def recover(req: RecoverRequest):
    """
    Ranked recovery candidates (top 3) for one appointment on a given date,
    via the same weighted Recovery Score engine the offline pipeline uses
    (model/capacity_recovery.py's recommend()).
    """
    try:
        ranked = recovery_recommend(
            req.appointment_id, req.target_date, service_type=req.service_type, top_n=3
        )
    except IndexError:
        raise HTTPException(status_code=404, detail=f"appointment_id {req.appointment_id!r} not found")
    return {
        "appointment_id": req.appointment_id,
        "target_date": req.target_date,
        "candidates": ranked or [],
    }


@app.post("/api/reschedule")
def reschedule(req: RescheduleRequest):
    """
    Full message -> intent -> candidate-date search -> proposal chain, via
    model/reschedule_agent.py's propose_reschedule() unchanged.
    """
    try:
        return propose_reschedule(req.appointment_id, req.message)
    except IndexError:
        raise HTTPException(status_code=404, detail=f"appointment_id {req.appointment_id!r} not found")


# Registered last so it doesn't shadow the /api/* and /health routes above --
# FastAPI/Starlette match routes in registration order, and StaticFiles
# would otherwise try (and fail) to serve "api/analyze" as a file.
app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")
