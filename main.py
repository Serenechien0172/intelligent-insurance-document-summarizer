import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from extractor import extract_policy_fields, extract_text_from_pdf, generate_summary


app = FastAPI(title="Insurance Document Summarizer")

BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = BASE_DIR / "uploads"
OUTPUTS_DIR = BASE_DIR / "outputs"


class Premium(BaseModel):
    interval: str
    amount: str


class PolicySummaryResponse(BaseModel):
    filename: str
    upload_path: str
    output_path: str
    policy_number: str | None = None
    insured_name: str | None = None
    effective_date: str | None = None
    expiration_date: str | None = None
    premium: Premium | None = None
    coverage_limits: list[str]
    exclusions: list[str]
    summary: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/upload", response_model=PolicySummaryResponse)
async def upload_policy(file: UploadFile = File(...)) -> PolicySummaryResponse:
    filename = file.filename or "upload.pdf"

    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    try:
        contents = await file.read()
        if not contents.startswith(b"%PDF"):
            raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF.")

        upload_path = _save_uploaded_pdf(filename, contents)
        output_path = _output_path_for(upload_path)

        text = extract_text_from_pdf(upload_path)
        if not text:
            raise HTTPException(status_code=422, detail="PDF contains no extractable text.")

        fields = extract_policy_fields(text)
        summary = generate_summary(fields)

        response = PolicySummaryResponse(
            filename=filename,
            upload_path=str(upload_path.relative_to(BASE_DIR)),
            output_path=str(output_path.relative_to(BASE_DIR)),
            policy_number=fields.get("policy_number"),
            insured_name=fields.get("insured_name"),
            effective_date=fields.get("effective_date"),
            expiration_date=fields.get("expiration_date"),
            premium=fields.get("premium"),
            coverage_limits=fields.get("coverage_limits", []),
            exclusions=fields.get("exclusions", []),
            summary=summary,
        )

        _save_result(response, output_path)
        return response
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to process PDF: {exc}") from exc


def _save_uploaded_pdf(filename: str, contents: bytes) -> Path:
    UPLOADS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_name = _safe_filename(filename)
    upload_path = UPLOADS_DIR / f"{timestamp}_{safe_name}"
    upload_path.write_bytes(contents)
    return upload_path


def _output_path_for(upload_path: Path) -> Path:
    OUTPUTS_DIR.mkdir(exist_ok=True)
    return OUTPUTS_DIR / f"{upload_path.stem}.json"


def _save_result(response: PolicySummaryResponse, output_path: Path) -> None:
    payload: dict[str, Any] = response.model_dump()
    rendered = json.dumps(payload, indent=2) + "\n"
    output_path.write_text(rendered, encoding="utf-8")
    (BASE_DIR / "sample_output.json").write_text(rendered, encoding="utf-8")


def _safe_filename(filename: str) -> str:
    name = Path(filename).name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "upload.pdf"
