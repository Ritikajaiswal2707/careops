#!/usr/bin/env python3
"""CareOps synthetic-data demo API.

The interactive endpoints use the repository's model modules, while the main
operations dashboard is a precomputed snapshot. No endpoint writes to a real
scheduling system or sends patient/provider messages.
"""
import json
import re
import sys
from pathlib import Path
from typing import Literal, Optional
import os

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "model"
DASHBOARD_DIR = BASE_DIR / "dashboard"

# Model files use sibling-module imports. Match the path setup used by run.py.
sys.path.insert(0, str(MODEL_DIR))

from hybrid_extraction import extract_intent_hybrid  # noqa: E402
from capacity_recovery import (  # noqa: E402
    InvalidDateError,
    UnknownAppointmentError,
    recommend as recovery_recommend,
    validate_target_date,
)
from reschedule_agent import propose_reschedule  # noqa: E402
from visit_report import build_report, transcribe  # noqa: E402
from recovery_agent import run_recovery_agent  # noqa: E402
from approval_store import (  # noqa: E402
    CaseConflictError, CaseNotFoundError, create_case, decide_case, get_case,
)
from simulated_execution import RevalidationError, execute_approved_case  # noqa: E402

app = FastAPI(
    title="CareOps Demo API",
    description=(
        "Portfolio prototype using synthetic home-healthcare data. "
        "Recommendations are illustrative; no real messages or bookings are sent."
    ),
    version="1.1.0",
)

APPOINTMENT_ID_PATTERN = re.compile(r"^APT\d{6}$")
MAX_MESSAGE_LENGTH = 2000


def _public_demo_read_only() -> bool:
    """Disable persisted agent-case mutations on a public portfolio deployment."""
    return os.getenv("CAREOPS_PUBLIC_DEMO_READ_ONLY", "false").strip().lower() in {"1", "true", "yes", "on"}


def _ensure_agent_mutations_enabled() -> None:
    if _public_demo_read_only():
        raise HTTPException(
            status_code=403,
            detail="Agent case mutations are disabled on the public read-only demo. Run locally for the full simulated approval flow.",
        )


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AnalyzeRequest(RequestModel):
    message: str = Field(strict=True, min_length=1, max_length=MAX_MESSAGE_LENGTH)

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value


class RecoverRequest(RequestModel):
    appointment_id: str = Field(strict=True, pattern=r"^APT\d{6}$")
    target_date: str = Field(strict=True, pattern=r"^\d{4}-\d{2}-\d{2}$")
    service_type: Optional[Literal[
        "Diabetic Care Visit",
        "Nursing Visit",
        "Physiotherapy Session",
        "Post-Op Care",
        "Vitals Check",
        "Wound Dressing",
    ]] = None

    @field_validator("target_date")
    @classmethod
    def date_is_supported(cls, value: str) -> str:
        try:
            validate_target_date(value)
        except InvalidDateError as exc:
            raise ValueError(str(exc)) from exc
        return value


MAX_VISIT_NOTE_LENGTH = 4000
MAX_AUDIO_BYTES = 10 * 1024 * 1024
AUDIO_SUFFIXES = {".mp3", ".m4a", ".wav", ".ogg", ".opus", ".webm", ".mp4", ".mpeg", ".mpga", ".flac"}


class VisitReportRequest(RequestModel):
    transcript: str = Field(strict=True, min_length=1, max_length=MAX_VISIT_NOTE_LENGTH)

    @field_validator("transcript")
    @classmethod
    def transcript_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("transcript must not be blank")
        return value


class AgentDecisionRequest(RequestModel):
    decision: Literal["approve", "reject"]
    note: Optional[str] = Field(default=None, max_length=500)

    @field_validator("note")
    @classmethod
    def note_not_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            return None
        return value.strip() if value is not None else None


class RescheduleRequest(RequestModel):
    appointment_id: str = Field(strict=True, pattern=r"^APT\d{6}$")
    message: str = Field(strict=True, min_length=1, max_length=MAX_MESSAGE_LENGTH)

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """Return actionable schema errors without echoing submitted message text."""
    safe_errors = [
        {
            "loc": error.get("loc", ()),
            "msg": error.get("msg", "Invalid request"),
            "type": error.get("type", "value_error"),
        }
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": safe_errors})


@app.get("/health")
def health():
    """Liveness endpoint; it does not imply the optional LLM is available."""
    return {"status": "ok", "mode": "synthetic-demo"}


@app.get("/api/operations")
def get_operations():
    """Serve the fixed synthetic snapshot generated by the offline pipeline."""
    path = MODEL_DIR / "dashboard_data.json"
    if not path.is_file():
        raise HTTPException(
            status_code=503,
            detail="The synthetic dashboard snapshot is unavailable. Run `python run.py` to generate it.",
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise HTTPException(
            status_code=503,
            detail="The synthetic dashboard snapshot could not be loaded.",
        )


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    """Parse one supplied message, escalating if no safe structured result exists."""
    return extract_intent_hybrid(req.message)


@app.post("/api/visit-report")
def visit_report(req: VisitReportRequest):
    """Structure a caregiver's visit note. Deterministic checks run after the model:
    unverifiable vitals and red flags send the report to a coordinator, and the family
    summary is withheld until then. Fails closed when no LLM is configured."""
    return build_report(req.transcript)


@app.post("/api/visit-report/audio")
async def visit_report_audio(file: UploadFile = File(...)):
    """Voice note -> transcript (Whisper) -> structured, safety-checked report."""
    if os.getenv("CAREOPS_DISABLE_EXTERNAL_LLM", "false").strip().lower() in {"1", "true", "yes", "on"}:
        raise HTTPException(status_code=503, detail="Speech-to-text is disabled in this public demo.")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in AUDIO_SUFFIXES:
        raise HTTPException(status_code=422, detail="Unsupported audio type.")
    data = await file.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file is larger than 10 MB.")
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        text, err = transcribe(tmp_path)
    finally:
        os.unlink(tmp_path)
    if text is None:
        raise HTTPException(status_code=502, detail=err or "Transcription failed.")
    return build_report(text)


@app.post("/api/recover")
def recover(req: RecoverRequest):
    """Return ranked feasible candidates from the synthetic capacity model."""
    try:
        ranked = recovery_recommend(
            req.appointment_id,
            req.target_date,
            service_type=req.service_type,
            top_n=3,
        )
    except UnknownAppointmentError:
        raise HTTPException(status_code=404, detail="Unknown appointment_id")
    except InvalidDateError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Required synthetic data is unavailable")
    return {
        "appointment_id": req.appointment_id,
        "target_date": req.target_date,
        "candidates": ranked or [],
        "simulated": True,
    }


@app.post("/api/reschedule")
def reschedule(req: RescheduleRequest):
    """Return a proposed reschedule; never books or notifies in the real world."""
    try:
        result = propose_reschedule(req.appointment_id, req.message)
    except (UnknownAppointmentError, IndexError):
        raise HTTPException(status_code=404, detail="Unknown appointment_id")
    except InvalidDateError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Required synthetic data is unavailable")
    return {**result, "simulated": True}


@app.post("/api/agent/run")
def run_agent(req: RescheduleRequest):
    """Run the bounded agent and persist approval-gated proposals; no booking occurs."""
    _ensure_agent_mutations_enabled()
    try:
        result = run_recovery_agent(req.appointment_id, req.message)
        case = create_case(result) if result.get("proposal") else None
        if case:
            result["case_id"] = case["case_id"]
            result["case_status"] = case["status"]
        result["booking_executed"] = False
        return result
    except (UnknownAppointmentError, IndexError):
        raise HTTPException(status_code=404, detail="Unknown appointment_id")
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Required synthetic data is unavailable")


@app.get("/api/agent/cases/{case_id}")
def agent_case(case_id: str):
    """Retrieve a persisted synthetic proposal and its audit history."""
    _ensure_agent_mutations_enabled()
    try:
        return get_case(case_id)
    except CaseNotFoundError:
        raise HTTPException(status_code=404, detail="Unknown recovery case")


@app.post("/api/agent/cases/{case_id}/decision")
def decide_agent_case(case_id: str, req: AgentDecisionRequest):
    """Record coordinator approval/rejection; approval does not execute a booking."""
    _ensure_agent_mutations_enabled()
    try:
        return decide_case(case_id, req.decision, req.note)
    except CaseNotFoundError:
        raise HTTPException(status_code=404, detail="Unknown recovery case")
    except CaseConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/api/agent/cases/{case_id}/execute")
def execute_agent_case(case_id: str):
    """Revalidate and record an approved recovery in simulation only."""
    _ensure_agent_mutations_enabled()
    try:
        return execute_approved_case(case_id)
    except CaseNotFoundError:
        raise HTTPException(status_code=404, detail="Unknown recovery case")
    except CaseConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RevalidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except InvalidDateError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Required synthetic data is unavailable")


# Register the static dashboard last so it cannot shadow the API endpoints.
app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")
