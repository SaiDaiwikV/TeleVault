import hashlib
import mimetypes
import secrets
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, File as UploadFileMarker, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.orm import Session, selectinload

from .auth import current_user, hash_password, issue_token, verify_password
from .config import BASE_DIR, settings
from .db import get_db, init_db
from .models import Chunk, File, Folder, ShareLink, UploadSession, User
from .oauth import router as oauth_router
from .security import SecurityHeadersMiddleware, enforce_auth_rate_limit
from .telegram_storage import ChunkIntegrityError, TelegramConfigError, storage


app = FastAPI(title="TeleVault", version="0.2.0")
app.include_router(oauth_router)
app.add_middleware(SecurityHeadersMiddleware)

# In development, default to allowing the Vite dev server. In production we do
# NOT silently fall back to localhost — an unset origin list means same-origin
# only (correct, since the built SPA is served by this very app), so a
# misconfiguration fails closed instead of quietly trusting localhost.
_cors_origins = settings.cors_origins
if not _cors_origins and not settings.is_production:
    _cors_origins = ["http://localhost:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# The built React SPA (npm run build in ./frontend) lands in static/app with
# Vite's default asset layout (static/app/assets/*). Mounting it at /assets
# lets the SPA's own index.html reference "/assets/..." unmodified.
_SPA_DIR = BASE_DIR / "static" / "app"
_SPA_DIR.mkdir(parents=True, exist_ok=True)
_SPA_ASSETS_DIR = _SPA_DIR / "assets"
_SPA_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/assets", StaticFiles(directory=_SPA_ASSETS_DIR), name="app-assets")


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=256)


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: int | None = None


class RenameBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class MoveBody(BaseModel):
    folder_id: int | None = None


class ShareCreate(BaseModel):
    expires_in_hours: int | None = Field(default=None, ge=1, le=settings.share_link_max_hours)
    max_downloads: int | None = Field(default=None, ge=1)


class UploadInit(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    total_size: int = Field(ge=0)
    folder_id: int | None = None
    mime: str | None = None
    encrypted: bool = True
    enc_alg: str | None = None
    enc_salt_b64: str | None = None
    enc_iv_b64: str | None = None
    enc_kdf: str | None = None
    enc_iterations: int | None = None
    original_sha256: str | None = None


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _copy_with_limit(src, dst, dst_path: Path) -> int:
    """Stream `src` into `dst`, aborting if it exceeds settings.max_upload_bytes.

    Enforcing the cap while copying (rather than after) means an oversized
    upload can't fill the scratch disk before we notice. On overflow we delete
    the partial file and raise 413.
    """
    limit = settings.max_upload_bytes
    written = 0
    while True:
        block = src.read(1024 * 1024)
        if not block:
            break
        written += len(block)
        if limit and written > limit:
            dst.flush()
            dst_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds the maximum upload size of {limit} bytes",
            )
        dst.write(block)
    return written


def file_json(file: File) -> dict:
    return {
        "id": file.id,
        "name": file.name,
        "folder_id": file.folder_id,
        "size": file.size,
        "mime": file.mime,
        "sha256": file.sha256,
        "original_sha256": file.original_sha256,
        "encrypted": file.encrypted,
        "enc_alg": file.enc_alg,
        "enc_salt_b64": file.enc_salt_b64,
        "enc_iv_b64": file.enc_iv_b64,
        "enc_kdf": file.enc_kdf,
        "enc_iterations": file.enc_iterations,
        "created_at": file.created_at.isoformat(),
        "chunks": [
            {
                "order": chunk.order,
                "tg_message_id": chunk.tg_message_id,
                "size": chunk.size,
                "sha256": chunk.sha256,
            }
            for chunk in file.chunks
        ],
    }


def folder_json(folder: Folder) -> dict:
    return {
        "id": folder.id,
        "name": folder.name,
        "parent_id": folder.parent_id,
        "created_at": folder.created_at.isoformat(),
    }


def owned_folder(db: Session, user: User, folder_id: int | None) -> Folder | None:
    if folder_id is None:
        return None
    folder = db.get(Folder, folder_id)
    if folder is None or folder.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


def _persist_file_record(
    db: Session,
    user: User,
    *,
    folder_id: int | None,
    filename: str,
    size: int,
    mime: str,
    digest: str,
    original_sha256: str | None,
    encrypted: bool,
    enc_alg: str | None,
    enc_salt_b64: str | None,
    enc_iv_b64: str | None,
    enc_kdf: str | None,
    enc_iterations: int | None,
    chunk_rows: list,
) -> File:
    record = File(
        owner_id=user.id,
        folder_id=folder_id,
        name=filename,
        size=size,
        mime=mime,
        sha256=digest,
        original_sha256=original_sha256,
        encrypted=encrypted,
        enc_alg=enc_alg,
        enc_salt_b64=enc_salt_b64,
        enc_iv_b64=enc_iv_b64,
        enc_kdf=enc_kdf,
        enc_iterations=enc_iterations,
    )
    db.add(record)
    db.flush()
    for chunk in chunk_rows:
        db.add(
            Chunk(
                file_id=record.id,
                order=chunk.order,
                tg_message_id=chunk.tg_message_id,
                size=chunk.size,
                sha256=chunk.sha256,
            )
        )
    db.commit()
    db.refresh(record)
    return db.scalar(select(File).options(selectinload(File.chunks)).where(File.id == record.id))


async def _upload_bytes_to_telegram_or_dedupe(
    db: Session, user: User, tmp_path: Path, digest: str, caption: str
):
    """Uploads chunk(s) to Telegram, unless an identical ciphertext already
    exists for this user (content-addressed dedup, Phase 3) — in which case
    the existing chunk metadata (Telegram message IDs) is reused and nothing
    new is sent over MTProto.
    """
    existing = db.scalar(
        select(File)
        .options(selectinload(File.chunks))
        .where(and_(File.owner_id == user.id, File.sha256 == digest))
        .order_by(File.created_at.desc())
    )
    if existing is not None and existing.chunks:
        return existing.chunks, True
    uploaded = await storage.upload_path(tmp_path, caption)
    return uploaded, False


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.on_event("shutdown")
async def shutdown() -> None:
    await storage.disconnect()


@app.get("/")
def index():
    spa_index = _SPA_DIR / "index.html"
    if spa_index.exists():
        return FileResponse(spa_index)
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/status")
def status():
    return {
        "app": settings.app_name,
        "telegram_ready": settings.telegram_ready,
        "chunk_size": settings.chunk_size,
        "storage_channel_id": bool(settings.telegram_storage_channel_id),
    }


@app.get("/api/auth/providers")
def auth_providers():
    """Return which OAuth providers are configured so the frontend can show
    only the buttons that will actually work."""
    return {
        "google": settings.google_enabled,
        "github": settings.github_enabled,
    }


@app.get("/api/telegram/check")
async def telegram_check():
    """Pre-flight configuration check. The frontend gates uploads on this so
    misconfigured Telegram credentials fail fast with a clear reason instead
    of during a half-finished upload."""
    return await storage.check_config()


@app.post("/api/auth/register")
def register(payload: Credentials, request: Request, db: Session = Depends(get_db)):
    enforce_auth_rate_limit(request, payload.username)
    existing = db.scalar(select(User).where(User.username == payload.username.lower()))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Username already exists")
    user = User(username=payload.username.lower(), password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"token": issue_token(db, user), "user": {"id": user.id, "username": user.username}}


@app.post("/api/auth/login")
def login(payload: Credentials, request: Request, db: Session = Depends(get_db)):
    enforce_auth_rate_limit(request, payload.username)
    user = db.scalar(select(User).where(User.username == payload.username.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"token": issue_token(db, user), "user": {"id": user.id, "username": user.username}}


@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "username": user.username}


@app.get("/api/items")
def list_items(
    folder_id: int | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if folder_id is not None:
        owned_folder(db, user, folder_id)
    folder_filter = Folder.parent_id.is_(None) if folder_id is None else Folder.parent_id == folder_id
    file_filter = File.folder_id.is_(None) if folder_id is None else File.folder_id == folder_id
    if q:
        pattern = f"%{q}%"
        folders = db.scalars(
            select(Folder).where(and_(Folder.owner_id == user.id, Folder.name.ilike(pattern)))
        ).all()
        files = db.scalars(
            select(File)
            .options(selectinload(File.chunks))
            .where(and_(File.owner_id == user.id, File.name.ilike(pattern)))
            .order_by(File.created_at.desc())
        ).all()
    else:
        folders = db.scalars(
            select(Folder)
            .where(and_(Folder.owner_id == user.id, folder_filter))
            .order_by(Folder.name.asc())
        ).all()
        files = db.scalars(
            select(File)
            .options(selectinload(File.chunks))
            .where(and_(File.owner_id == user.id, file_filter))
            .order_by(File.created_at.desc())
        ).all()
    return {"folders": [folder_json(f) for f in folders], "files": [file_json(f) for f in files]}


@app.get("/api/folders/all")
def list_all_folders(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Flat list of every folder the user owns — used by the move-file picker
    so a file can be relocated anywhere in the tree, not just within the
    currently-viewed folder."""
    folders = db.scalars(
        select(Folder).where(Folder.owner_id == user.id).order_by(Folder.name.asc())
    ).all()
    return [folder_json(f) for f in folders]


@app.post("/api/folders")
def create_folder(payload: FolderCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    owned_folder(db, user, payload.parent_id)
    folder = Folder(owner_id=user.id, parent_id=payload.parent_id, name=payload.name)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder_json(folder)


@app.patch("/api/folders/{folder_id}/rename")
def rename_folder(folder_id: int, payload: RenameBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    folder = owned_folder(db, user, folder_id)
    folder.name = payload.name
    db.commit()
    db.refresh(folder)
    return folder_json(folder)


@app.delete("/api/folders/{folder_id}")
def delete_folder(folder_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    folder = owned_folder(db, user, folder_id)
    files = db.scalars(select(File).where(and_(File.owner_id == user.id, File.folder_id == folder.id))).all()
    child_folders = db.scalars(select(Folder).where(and_(Folder.owner_id == user.id, Folder.parent_id == folder.id))).all()
    if files or child_folders:
        raise HTTPException(status_code=409, detail="Folder must be empty before deletion")
    db.delete(folder)
    db.commit()
    return {"ok": True}


@app.post("/api/files")
async def upload_file(
    upload: UploadFile = UploadFileMarker(...),
    folder_id: int | None = Form(default=None),
    encrypted: bool = Form(default=True),
    enc_alg: str | None = Form(default=None),
    enc_salt_b64: str | None = Form(default=None),
    enc_iv_b64: str | None = Form(default=None),
    enc_kdf: str | None = Form(default=None),
    enc_iterations: int | None = Form(default=None),
    original_sha256: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    owned_folder(db, user, folder_id)
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = Path(tmp.name)
        _copy_with_limit(upload.file, tmp, tmp_path)
    try:
        size = tmp_path.stat().st_size
        digest = sha256_of_file(tmp_path)
        chunk_rows, deduped = await _upload_bytes_to_telegram_or_dedupe(
            db, user, tmp_path, digest, f"user {user.id} file {upload.filename}"
        )
        record = _persist_file_record(
            db,
            user,
            folder_id=folder_id,
            filename=upload.filename,
            size=size,
            mime=upload.content_type or mimetypes.guess_type(upload.filename)[0] or "application/octet-stream",
            digest=digest,
            original_sha256=original_sha256,
            encrypted=encrypted,
            enc_alg=enc_alg,
            enc_salt_b64=enc_salt_b64,
            enc_iv_b64=enc_iv_b64,
            enc_kdf=enc_kdf,
            enc_iterations=enc_iterations,
            chunk_rows=chunk_rows,
        )
        payload = file_json(record)
        payload["deduplicated"] = deduped
        return payload
    except TelegramConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    finally:
        tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Resumable uploads (Phase 4)
#
# init -> client streams ordered byte ranges via PUT .../chunk -> complete.
# The server tracks received_bytes so a dropped connection can resume from
# that offset instead of restarting the whole (already-encrypted) file.
# ---------------------------------------------------------------------------


@app.post("/api/uploads/init")
def init_upload(payload: UploadInit, db: Session = Depends(get_db), user: User = Depends(current_user)):
    owned_folder(db, user, payload.folder_id)
    if settings.max_upload_bytes and payload.total_size > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the maximum upload size of {settings.max_upload_bytes} bytes",
        )
    upload_id = uuid.uuid4().hex
    scratch_path = settings.scratch_dir / f"{upload_id}.part"
    scratch_path.touch()
    session = UploadSession(
        upload_id=upload_id,
        owner_id=user.id,
        folder_id=payload.folder_id,
        filename=payload.filename,
        mime=payload.mime or mimetypes.guess_type(payload.filename)[0] or "application/octet-stream",
        total_size=payload.total_size,
        received_bytes=0,
        scratch_path=str(scratch_path),
        encrypted=payload.encrypted,
        enc_alg=payload.enc_alg,
        enc_salt_b64=payload.enc_salt_b64,
        enc_iv_b64=payload.enc_iv_b64,
        enc_kdf=payload.enc_kdf,
        enc_iterations=payload.enc_iterations,
        original_sha256=payload.original_sha256,
    )
    db.add(session)
    db.commit()
    return {"upload_id": upload_id, "received_bytes": 0}


def _get_upload_session(db: Session, user: User, upload_id: str) -> UploadSession:
    session = db.scalar(select(UploadSession).where(UploadSession.upload_id == upload_id))
    if session is None or session.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Upload session not found")
    if session.completed:
        raise HTTPException(status_code=409, detail="Upload already completed")
    return session


@app.get("/api/uploads/{upload_id}/status")
def upload_status(upload_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    session = _get_upload_session(db, user, upload_id)
    return {"upload_id": upload_id, "received_bytes": session.received_bytes, "total_size": session.total_size}


@app.put("/api/uploads/{upload_id}/chunk")
async def upload_chunk(upload_id: str, request: Request, offset: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    session = _get_upload_session(db, user, upload_id)
    if offset != session.received_bytes:
        raise HTTPException(
            status_code=409,
            detail=f"Offset mismatch: server has {session.received_bytes} bytes, client sent offset {offset}",
        )
    scratch_path = Path(session.scratch_path)
    body = await request.body()
    # Guard against a client sending more than it declared (or than we allow),
    # which would otherwise grow the scratch file unbounded.
    if settings.max_upload_bytes and session.received_bytes + len(body) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Upload exceeds the maximum allowed size")
    if session.received_bytes + len(body) > session.total_size:
        raise HTTPException(status_code=409, detail="Chunk exceeds declared total size")
    with scratch_path.open("ab") as f:
        f.write(body)
    session.received_bytes += len(body)
    db.commit()
    return {"received_bytes": session.received_bytes}


@app.post("/api/uploads/{upload_id}/complete")
async def complete_upload(upload_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    session = _get_upload_session(db, user, upload_id)
    scratch_path = Path(session.scratch_path)
    if session.received_bytes != session.total_size or not scratch_path.exists():
        raise HTTPException(status_code=409, detail="Upload is incomplete")
    try:
        digest = sha256_of_file(scratch_path)
        chunk_rows, deduped = await _upload_bytes_to_telegram_or_dedupe(
            db, user, scratch_path, digest, f"user {user.id} file {session.filename}"
        )
        record = _persist_file_record(
            db,
            user,
            folder_id=session.folder_id,
            filename=session.filename,
            size=session.total_size,
            mime=session.mime,
            digest=digest,
            original_sha256=session.original_sha256,
            encrypted=session.encrypted,
            enc_alg=session.enc_alg,
            enc_salt_b64=session.enc_salt_b64,
            enc_iv_b64=session.enc_iv_b64,
            enc_kdf=session.enc_kdf,
            enc_iterations=session.enc_iterations,
            chunk_rows=chunk_rows,
        )
        session.completed = True
        db.commit()
        payload = file_json(record)
        payload["deduplicated"] = deduped
        return payload
    except TelegramConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    finally:
        scratch_path.unlink(missing_ok=True)


@app.get("/api/files/{file_id}/download")
async def download_file(file_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    record = db.scalar(select(File).options(selectinload(File.chunks)).where(File.id == file_id))
    if record is None or record.owner_id != user.id:
        raise HTTPException(status_code=404, detail="File not found")
    return _stream_file(record)


def _content_disposition(filename: str) -> str:
    """Build a safe Content-Disposition header.

    User-controlled filenames must never be interpolated raw into a header:
    a quote or CRLF could break out of the value or inject other headers. We
    strip control characters, provide an ASCII-only fallback for the legacy
    `filename=` field, and add an RFC 5987 `filename*` for full-fidelity
    (e.g. non-ASCII) names.
    """
    cleaned = "".join(ch for ch in filename if ch.isprintable() and ch not in '\r\n"\\') or "download"
    ascii_fallback = cleaned.encode("ascii", "ignore").decode("ascii") or "download"
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(cleaned)}"


def _stream_file(record: File) -> StreamingResponse:
    chunk_pairs = [(chunk.tg_message_id, chunk.sha256) for chunk in record.chunks]

    async def stream():
        try:
            async for data in storage.download_messages(chunk_pairs):
                yield data
        except ChunkIntegrityError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    headers = {"Content-Disposition": _content_disposition(record.name)}
    return StreamingResponse(stream(), media_type=record.mime, headers=headers)


@app.patch("/api/files/{file_id}/rename")
def rename_file(file_id: int, payload: RenameBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    record = db.get(File, file_id)
    if record is None or record.owner_id != user.id:
        raise HTTPException(status_code=404, detail="File not found")
    record.name = payload.name
    db.commit()
    db.refresh(record)
    return file_json(db.scalar(select(File).options(selectinload(File.chunks)).where(File.id == record.id)))


@app.patch("/api/files/{file_id}/move")
def move_file(file_id: int, payload: MoveBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    record = db.get(File, file_id)
    if record is None or record.owner_id != user.id:
        raise HTTPException(status_code=404, detail="File not found")
    owned_folder(db, user, payload.folder_id)
    record.folder_id = payload.folder_id
    db.commit()
    return {"ok": True}


@app.delete("/api/files/{file_id}")
async def delete_file(file_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    record = db.scalar(select(File).options(selectinload(File.chunks)).where(File.id == file_id))
    if record is None or record.owner_id != user.id:
        raise HTTPException(status_code=404, detail="File not found")

    message_ids = [chunk.tg_message_id for chunk in record.chunks]
    # Content-addressed dedup means another file may still reference the same
    # Telegram messages — only delete messages no longer referenced by anyone.
    still_referenced = set()
    if message_ids:
        other_chunks = db.scalars(
            select(Chunk).where(and_(Chunk.tg_message_id.in_(message_ids), Chunk.file_id != record.id))
        ).all()
        still_referenced = {c.tg_message_id for c in other_chunks}
    to_delete = [mid for mid in message_ids if mid not in still_referenced]

    await storage.delete_messages(to_delete)
    db.delete(record)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Share links (Phase 3)
# ---------------------------------------------------------------------------


def _share_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@app.post("/api/files/{file_id}/share")
def create_share_link(file_id: int, payload: ShareCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    record = db.get(File, file_id)
    if record is None or record.owner_id != user.id:
        raise HTTPException(status_code=404, detail="File not found")
    hours = payload.expires_in_hours or settings.share_link_default_hours
    token = secrets.token_urlsafe(32)
    link = ShareLink(
        file_id=record.id,
        owner_id=user.id,
        token_hash=_share_token_hash(token),
        expires_at=datetime.utcnow() + timedelta(hours=hours),
        max_downloads=payload.max_downloads,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return {
        "id": link.id,
        "token": token,
        "url": f"/api/share/{token}/download",
        "expires_at": link.expires_at.isoformat(),
        "max_downloads": link.max_downloads,
    }


@app.get("/api/files/{file_id}/shares")
def list_share_links(file_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    record = db.get(File, file_id)
    if record is None or record.owner_id != user.id:
        raise HTTPException(status_code=404, detail="File not found")
    links = db.scalars(select(ShareLink).where(ShareLink.file_id == file_id)).all()
    return [
        {
            "id": l.id,
            "expires_at": l.expires_at.isoformat() if l.expires_at else None,
            "max_downloads": l.max_downloads,
            "download_count": l.download_count,
            "revoked": l.revoked,
        }
        for l in links
    ]


@app.delete("/api/shares/{share_id}")
def revoke_share_link(share_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    link = db.get(ShareLink, share_id)
    if link is None or link.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Share link not found")
    link.revoked = True
    db.commit()
    return {"ok": True}


@app.get("/api/share/{token}/download")
async def download_shared_file(token: str, db: Session = Depends(get_db)):
    token_hash = _share_token_hash(token)
    link = db.scalar(select(ShareLink).where(ShareLink.token_hash == token_hash))
    if link is None or link.revoked:
        raise HTTPException(status_code=404, detail="Link not found or revoked")
    if link.expires_at and link.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Link expired")
    if link.max_downloads is not None and link.download_count >= link.max_downloads:
        raise HTTPException(status_code=410, detail="Download limit reached")
    record = db.scalar(select(File).options(selectinload(File.chunks)).where(File.id == link.file_id))
    if record is None:
        raise HTTPException(status_code=404, detail="File not found")
    link.download_count += 1
    db.commit()
    return _stream_file(record)
