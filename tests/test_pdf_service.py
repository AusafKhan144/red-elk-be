"""Tests for the PDF service: Cloudinary guard rails and the generation pipeline."""
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

import app.services.pdf as pdf_service
from app.schemas.schemas import RadarPoint, ReportOut


@pytest.fixture(autouse=True)
def _reset_cloudinary_flag():
    pdf_service._cloudinary_configured = False
    yield
    pdf_service._cloudinary_configured = False


def _set_creds(monkeypatch, name="cloud", key="key", secret="secret"):
    monkeypatch.setattr(pdf_service.settings, "CLOUDINARY_CLOUD_NAME", name)
    monkeypatch.setattr(pdf_service.settings, "CLOUDINARY_API_KEY", key)
    monkeypatch.setattr(pdf_service.settings, "CLOUDINARY_API_SECRET", secret)


def _make_report() -> ReportOut:
    return ReportOut(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        scores={"strategy": 80.0},
        overall_score=80.0,
        tier_result="leading",
        recommendations={"strategy": "keep going"},
        radar_data=[RadarPoint(dimension="strategy", score=80.0, label="Strategy & Vision")],
        pdf_url=None,
        generated_at=datetime.now(timezone.utc),
    )


def test_ensure_cloudinary_raises_on_missing_creds(monkeypatch):
    _set_creds(monkeypatch, name="", key="", secret="")
    with pytest.raises(RuntimeError, match="CLOUDINARY_CLOUD_NAME"):
        pdf_service._ensure_cloudinary()


def test_ensure_cloudinary_names_only_missing_vars(monkeypatch):
    _set_creds(monkeypatch, name="cloud", key="", secret="secret")
    with pytest.raises(RuntimeError) as exc_info:
        pdf_service._ensure_cloudinary()
    assert "CLOUDINARY_API_KEY" in str(exc_info.value)
    assert "CLOUDINARY_CLOUD_NAME" not in str(exc_info.value)


async def test_generate_and_upload_fails_fast_without_creds(monkeypatch):
    _set_creds(monkeypatch, name="", key="", secret="")
    with pytest.raises(RuntimeError, match="Cloudinary not configured"):
        await pdf_service.generate_and_upload_pdf(_make_report(), "Test Assessment")


async def test_generate_and_upload_returns_secure_url(monkeypatch):
    _set_creds(monkeypatch)
    report = _make_report()
    with patch.object(
        pdf_service.cloudinary.uploader, "upload",
        return_value={"secure_url": "https://res.cloudinary.test/x.pdf"},
    ) as mock_upload:
        url = await pdf_service.generate_and_upload_pdf(report, "Test Assessment")

    assert url == "https://res.cloudinary.test/x.pdf"
    # real WeasyPrint render ran — uploaded bytes must be a PDF
    uploaded = mock_upload.call_args.args[0]
    assert uploaded.read(5) == b"%PDF-"
    assert mock_upload.call_args.kwargs["public_id"] == f"red-elk/reports/{report.session_id}"


async def test_upload_without_secure_url_raises(monkeypatch):
    _set_creds(monkeypatch)
    with patch.object(pdf_service.cloudinary.uploader, "upload", return_value={"error": "denied"}):
        with pytest.raises(RuntimeError, match="no secure_url"):
            await pdf_service.generate_and_upload_pdf(_make_report(), "Test Assessment")
