import uuid
from pathlib import Path

from fastapi import UploadFile

from app.config import get_settings
from app.exceptions import UnauthorizedError

_ALLOWED_CONTENT_TYPES = {"application/pdf"}
_UPLOAD_DIR = Path("uploads")


def _validate_pdf(file: UploadFile, content: bytes) -> None:
    settings = get_settings()
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise UnauthorizedError(detail="Only PDF files are accepted")
    if len(content) > settings.max_upload_size_bytes:
        mb = settings.max_upload_size_bytes // 1_048_576
        raise UnauthorizedError(detail=f"File exceeds maximum size of {mb} MB")


async def read_and_validate_pdf(file: UploadFile) -> bytes:
    content = await file.read()
    _validate_pdf(file, content)
    return content


def save_pdf_locally(user_id: uuid.UUID, content: bytes) -> str:
    """Persist PDF to local uploads dir. Returns the relative file path."""
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{user_id}_{uuid.uuid4()}.pdf"
    path = _UPLOAD_DIR / filename
    path.write_bytes(content)
    return str(path)
