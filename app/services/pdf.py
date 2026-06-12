"""
PDF generation pipeline:
  1. Render Jinja2 HTML template with report data
  2. Convert to PDF via WeasyPrint
  3. Upload to Cloudinary
  4. Return the secure URL
"""
import asyncio
import io
import uuid
from pathlib import Path

import cloudinary
import cloudinary.uploader
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from app.core.config import settings
from app.schemas.schemas import ReportOut

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_jinja_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)

_cloudinary_configured = False


def _ensure_cloudinary() -> None:
    """Configure Cloudinary lazily, failing loudly if credentials are missing."""
    global _cloudinary_configured
    if _cloudinary_configured:
        return
    missing = [
        name
        for name in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")
        if not getattr(settings, name)
    ]
    if missing:
        raise RuntimeError(f"Cloudinary not configured — missing env vars: {', '.join(missing)}")
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )
    _cloudinary_configured = True


async def generate_and_upload_pdf(report: ReportOut, assessment_name: str) -> str:
    """
    Render report HTML, convert to PDF bytes, upload to Cloudinary.
    Returns the secure Cloudinary URL.
    """
    _ensure_cloudinary()
    html_str = _render_html(report, assessment_name)
    # WeasyPrint rendering and the Cloudinary upload are blocking — keep them
    # off the event loop.
    pdf_bytes = await asyncio.to_thread(_html_to_pdf, html_str)
    url = await asyncio.to_thread(_upload_to_cloudinary, pdf_bytes, report.session_id)
    return url


def _render_html(report: ReportOut, assessment_name: str) -> str:
    template = _jinja_env.get_template("report.html")
    return template.render(
        report=report,
        assessment_name=assessment_name,
        radar_data=report.radar_data,
        tier_label=report.tier_result.replace("_", " ").title(),
    )


def _html_to_pdf(html_str: str) -> bytes:
    buf = io.BytesIO()
    HTML(string=html_str).write_pdf(buf)
    return buf.getvalue()


def _upload_to_cloudinary(pdf_bytes: bytes, session_id: uuid.UUID) -> str:
    public_id = f"red-elk/reports/{session_id}"
    result = cloudinary.uploader.upload(
        io.BytesIO(pdf_bytes),
        public_id=public_id,
        resource_type="raw",
        format="pdf",
        overwrite=True,
    )
    url = result.get("secure_url")
    if not url:
        raise RuntimeError(f"Cloudinary upload returned no secure_url: {result}")
    return url
