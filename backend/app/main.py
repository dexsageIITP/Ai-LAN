from __future__ import annotations

import json
import os
import base64
import asyncio
import hashlib
import hmac
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "ailan.db"
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

CATEGORIES = ["roads", "water_supply", "drainage", "waste_management", "public_lighting",
              "public_infrastructure", "waterlogging", "environment", "other"]
SEVERITIES = ["low", "medium", "high", "critical"]
STATUSES = ["submitted", "processing", "authority_verification_pending", "notification_pending",
            "notification_sent", "under_review", "assigned", "in_progress", "resolved", "rejected",
            "closed", "manual_review"]
ROLES = {"citizen", "government", "admin"}
ADMIN_EMAIL = "arihantghosh28@gmail.com"
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connection() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS authorities (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, department TEXT NOT NULL,
              jurisdiction TEXT NOT NULL, issue_categories TEXT NOT NULL,
              official_email TEXT, phone_number TEXT, helpline TEXT, address TEXT,
              source_url TEXT, verification_status TEXT NOT NULL, last_verified_at TEXT,
              active INTEGER NOT NULL DEFAULT 1, demo INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS users (
              id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
              password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'citizen',
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
              token TEXT PRIMARY KEY, user_id TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS issues (
              id TEXT PRIMARY KEY, report_number TEXT UNIQUE NOT NULL, category TEXT NOT NULL,
              title TEXT NOT NULL, description TEXT NOT NULL, ai_summary TEXT NOT NULL,
              latitude REAL NOT NULL, longitude REAL NOT NULL, location_text TEXT,
              severity TEXT NOT NULL, ai_confidence REAL NOT NULL, status TEXT NOT NULL,
              authority_id TEXT, ai_status TEXT NOT NULL, notification_status TEXT NOT NULL,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL, demo INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS history (
              id TEXT PRIMARY KEY, issue_id TEXT NOT NULL, old_status TEXT, new_status TEXT NOT NULL,
              note TEXT, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS media (
              id TEXT PRIMARY KEY, issue_id TEXT NOT NULL, filename TEXT NOT NULL,
              mime_type TEXT NOT NULL, storage_key TEXT NOT NULL
            );
            """
        )
        db.execute(
            """UPDATE issues SET ai_confidence = CASE lower(trim(CAST(ai_confidence AS TEXT)))
               WHEN 'low' THEN 0.35
               WHEN 'medium' THEN 0.65
               WHEN 'high' THEN 0.90
               WHEN 'critical' THEN 0.95
               ELSE ai_confidence
               END
               WHERE typeof(ai_confidence) = 'text'"""
        )
        columns = {row["name"] for row in db.execute("PRAGMA table_info(issues)")}
        if "ai_guidance" not in columns:
            db.execute("ALTER TABLE issues ADD COLUMN ai_guidance TEXT NOT NULL DEFAULT ''")
        if db.execute("SELECT COUNT(*) FROM authorities").fetchone()[0] == 0:
            db.execute(
                """INSERT INTO authorities VALUES
                ('auth-demo-patna','Patna Municipal Corporation','Roads & Public Works',
                 'Patna, Bihar','["roads","public_infrastructure","waterlogging"]',
                 'demo.roads@patna.example.gov.in','Contact number unavailable',
                 '1800-000-0000','Demonstration Civic Centre, Patna',
                 'https://pmc.bihar.gov.in','verified',?,1,1),
                ('auth-demo-water','Patna Water Supply Division','Water Supply Department',
                 'Patna, Bihar','["water_supply","drainage"]',
                 'demo.water@patna.example.gov.in',NULL,'Contact number unavailable',
                 'Demonstration Water Office, Patna',
                 'https://phed.bihar.gov.in','verified',?,1,1)""",
                (now(), now()),
            )
        if db.execute("SELECT COUNT(*) FROM issues").fetchone()[0] == 0:
            samples = [
                ("roads", "Pothole near Rajendra Nagar", "Large pothole affecting the main road junction.",
                 25.6093, 85.1376, "Rajendra Nagar, Patna", "high", "in_progress", "auth-demo-patna"),
                ("waste_management", "Overflowing community bin", "Waste accumulation beside the public market.",
                 25.6121, 85.1584, "Kankarbagh, Patna", "medium", "under_review", "auth-demo-patna"),
                ("water_supply", "Pipeline leakage", "Water is visibly leaking onto the street.",
                 25.5941, 85.1371, "Gandhi Maidan, Patna", "high", "notification_sent", "auth-demo-water"),
                ("public_lighting", "Streetlight not working", "A dark stretch near the pedestrian crossing.",
                 25.6224, 85.1058, "Boring Road, Patna", "medium", "resolved", "auth-demo-patna"),
            ]
            for idx, (category, title, description, lat, lng, location, severity, status, authority) in enumerate(samples, 1):
                issue_id = str(uuid.uuid4())
                created = f"2026-10-{max(1, 20 - idx):02d}T10:00:00+00:00"
                db.execute(
                    """INSERT INTO issues
                    (id, report_number, category, title, description, ai_summary, latitude,
                     longitude, location_text, severity, ai_confidence, status, authority_id,
                     ai_status, notification_status, created_at, updated_at, demo)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (issue_id, f"AIL-2026-{idx:05d}", category, title, description,
                     description, lat, lng, location, severity, .94, status, authority,
                     "completed", "sent", created, created, 1),
                )
                db.execute("INSERT INTO history VALUES (?,?,?,?,?,?)",
                           (str(uuid.uuid4()), issue_id, None, "submitted", "Demonstration report imported", created))
        db.commit()


class ReportOut(BaseModel):
    id: str
    report_number: str
    category: str
    title: str
    description: str
    ai_summary: str
    ai_guidance: str
    latitude: float
    longitude: float
    location_text: str | None
    severity: str
    ai_confidence: float
    status: str
    ai_status: str
    notification_status: str
    created_at: str
    updated_at: str
    demo: bool
    authority: dict | None = None


class StatusUpdate(BaseModel):
    status: str
    note: str | None = Field(default=None, max_length=500)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in STATUSES:
            raise ValueError("Unsupported complaint status")
        return value


def authority_dict(row: sqlite3.Row | None) -> dict | None:
    if not row:
        return None
    result = dict(row)
    result["issue_categories"] = json.loads(result["issue_categories"])
    result["active"] = bool(result["active"])
    result["demo"] = bool(result["demo"])
    return result


def report_dict(row: sqlite3.Row) -> dict:
    result = dict(row)
    result["demo"] = bool(result["demo"])
    with connection() as db:
        result["authority"] = authority_dict(db.execute(
            "SELECT * FROM authorities WHERE id = ?", (result["authority_id"],)
        ).fetchone())
    return result


def find_verified_authority(
    db: sqlite3.Connection, category: str, location_text: str | None
) -> sqlite3.Row | None:
    authorities = db.execute(
        "SELECT * FROM authorities WHERE active=1 AND verification_status='verified'"
    ).fetchall()
    location = (location_text or "").casefold()
    matches: list[tuple[int, sqlite3.Row]] = []
    for authority in authorities:
        categories = json.loads(authority["issue_categories"])
        if category not in categories:
            continue
        jurisdiction = authority["jurisdiction"].casefold()
        score = 2 if jurisdiction in location or location in jurisdiction else 0
        if authority["official_email"]:
            score += 1
        matches.append((score, authority))
    return max(matches, key=lambda match: match[0])[1] if matches else None


def next_report_number(db: sqlite3.Connection) -> str:
    year = datetime.now(timezone.utc).year
    count = db.execute("SELECT COUNT(*) FROM issues").fetchone()[0] + 1
    return f"AIL-{year}-{count:05d}"


def password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)
    return f"{salt.hex()}:{digest.hex()}"


def password_matches(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split(":", 1)
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 240_000).hex()
        return hmac.compare_digest(candidate, digest)
    except ValueError:
        return False


def requested_role(email: str, role: str) -> str:
    normalized_email = email.strip().lower()
    if normalized_email == ADMIN_EMAIL:
        return "admin"
    if role not in ROLES - {"admin"}:
        raise HTTPException(400, "Choose Citizen or Government")
    return role


def current_user(authorization: str | None) -> sqlite3.Row:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in is required")
    token = authorization.removeprefix("Bearer ").strip()
    with connection() as db:
        user = db.execute(
            "SELECT users.* FROM users JOIN sessions ON sessions.user_id = users.id "
            "WHERE sessions.token = ?", (token,)
        ).fetchone()
    if not user:
        raise HTTPException(401, "Your session is invalid or expired")
    return user


def require_roles(authorization: str | None, allowed: set[str]) -> sqlite3.Row:
    user = current_user(authorization)
    if user["role"] not in allowed:
        raise HTTPException(403, "Your account does not have permission for this action")
    return user


class AuthPayload(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
    name: str | None = Field(default=None, max_length=100)
    role: str = "citizen"


class GoogleAuthPayload(BaseModel):
    credential: str = Field(min_length=20)


def auth_response(row: sqlite3.Row) -> dict:
    return {"token": secrets.token_urlsafe(32), "user": {
        "id": row["id"], "email": row["email"], "name": row["name"], "role": row["role"]}}


async def analyze_with_gemini(description: str, files: list[tuple[str, bytes]]) -> dict | None:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("AI_API_KEY")
    if not api_key or os.getenv("AI_PROVIDER", "gemini") != "gemini":
        return None
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    parts = [{"text": (
        "Classify this civic issue. Return JSON only with keys category, issue_type, summary, "
        "severity, confidence, evidence, uncertainty, guidance. Allowed categories: " + ", ".join(CATEGORIES) +
        ". guidance must be a short, practical safety/action suggestion based on both the image and description. "
        "Do not invent facts. User description: " + description)}]
    for mime_type, content in files:
        parts.append({"inline_data": {"mime_type": mime_type, "data": base64.b64encode(content).decode()}})
    async with httpx.AsyncClient(timeout=45) as client:
        for attempt in range(3):
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": api_key},
                json={"contents": [{"parts": parts}],
                      "generationConfig": {"responseMimeType": "application/json"}},
            )
            if response.status_code not in {429, 500, 502, 503, 504} or attempt == 2:
                break
            await asyncio.sleep(2 ** attempt)
    response.raise_for_status()
    text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("Gemini returned a non-object classification")
    category = str(result.get("category", "")).strip().lower()
    severity = str(result.get("severity", "")).strip().lower()
    if category not in CATEGORIES or severity not in SEVERITIES:
        raise ValueError("Gemini returned an invalid civic classification")
    result["category"] = category
    result["severity"] = severity
    confidence = result.get("confidence", 0)
    if isinstance(confidence, str):
        confidence_labels = {"low": 0.35, "medium": 0.65, "high": 0.9}
        confidence = confidence_labels.get(confidence.strip().lower(), confidence)
    result["confidence"] = max(0, min(1, float(confidence)))
    guidance = result.get("guidance")
    if not isinstance(guidance, str) or not guidance.strip():
        raise ValueError("Gemini returned no actionable guidance")
    result["guidance"] = guidance.strip()
    return result


async def find_office_with_gemini(category: str, location_text: str | None) -> dict:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("AI_API_KEY")
    if not api_key or os.getenv("AI_PROVIDER", "gemini") != "gemini":
        raise HTTPException(503, "Live office lookup is not configured")
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    prompt = (
        "Find the official government office responsible for this civic complaint. "
        "Use Google Search grounding. Return JSON only with keys name, department, address, "
        "official_email, phone, source_url. Prefer official government sources, never invent "
        "contact details, and use null for any field that cannot be verified. "
        f"Complaint category: {category.replace('_', ' ')}. Locality: {location_text or 'not provided'}."
    )
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "tools": [{"google_search": {}}],
            },
        )
    response.raise_for_status()
    parts = response.json()["candidates"][0]["content"]["parts"]
    text = next((part["text"] for part in parts if "text" in part), "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Live office lookup returned no JSON object")
    result = json.loads(text[start:end + 1])
    if not isinstance(result, dict) or not result.get("name") or not result.get("address"):
        raise ValueError("Live office lookup returned incomplete official details")
    return {
        "name": str(result["name"]),
        "department": result.get("department"),
        "address": str(result["address"]),
        "official_email": result.get("official_email"),
        "phone": result.get("phone"),
        "source_url": result.get("source_url"),
        "source": "Gemini Google Search grounding",
    }


def has_image_signature(mime_type: str, contents: bytes) -> bool:
    signatures = {
        "image/jpeg": contents.startswith(b"\xff\xd8\xff"),
        "image/png": contents.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": contents.startswith(b"RIFF") and contents[8:12] == b"WEBP",
    }
    return signatures.get(mime_type, False)


init_db()
app = FastAPI(title="Ai-LAN Civic Intelligence API", version="1.0.0")
frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
allowed_origins = list(dict.fromkeys([
    frontend_origin,
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]))
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/auth/register")
def register(payload: AuthPayload) -> dict:
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(400, "Enter a valid email address")
    role = requested_role(email, payload.role)
    with connection() as db:
        if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise HTTPException(409, "An account with this email already exists")
        user_id = str(uuid.uuid4())
        db.execute("INSERT INTO users VALUES (?,?,?,?,?,?)",
                   (user_id, email, (payload.name or email.split("@")[0]).strip(),
                    password_hash(payload.password), role, now()))
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO sessions VALUES (?,?,?)", (token, user_id, now()))
        db.commit()
        return auth_response(db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()) | {"token": token}


@app.post("/api/auth/login")
def login(payload: AuthPayload) -> dict:
    with connection() as db:
        user = db.execute("SELECT * FROM users WHERE email = ?", (payload.email.strip().lower(),)).fetchone()
        if not user or not password_matches(payload.password, user["password_hash"]):
            raise HTTPException(401, "Invalid email or password")
        role = requested_role(payload.email, payload.role)
        if user["email"] == ADMIN_EMAIL and user["role"] != "admin":
            db.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user["id"],))
            user = db.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        elif user["role"] != role:
            raise HTTPException(403, "Select the account type assigned to this account")
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO sessions VALUES (?,?,?)", (token, user["id"], now()))
        db.commit()
        return auth_response(user) | {"token": token}


@app.get("/api/auth/google-config")
def google_config() -> dict:
    return {"client_id": os.getenv("GOOGLE_CLIENT_ID", "")}


@app.post("/api/auth/google")
async def google_login(payload: GoogleAuthPayload) -> dict:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(503, "Google Sign-In is not configured")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": payload.credential},
            )
        response.raise_for_status()
        profile = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(401, "Google identity could not be verified")
    if profile.get("aud") != client_id or profile.get("email_verified") != "true":
        raise HTTPException(401, "Google identity verification failed")
    email = profile.get("email", "").strip().lower()
    subject = profile.get("sub")
    if not email or not subject:
        raise HTTPException(401, "Google did not return a usable account")
    with connection() as db:
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user:
            user_id = str(uuid.uuid4())
            db.execute("INSERT INTO users VALUES (?,?,?,?,?,?)",
                       (user_id, email, profile.get("name") or email.split("@")[0],
                        password_hash(secrets.token_urlsafe(32)),
                        "admin" if email == ADMIN_EMAIL else "citizen", now()))
            user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        elif email == ADMIN_EMAIL and user["role"] != "admin":
            db.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user["id"],))
            user = db.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO sessions VALUES (?,?,?)", (token, user["id"], now()))
        db.commit()
        return auth_response(user) | {"token": token}


@app.get("/api/health")
def health() -> dict:
    try:
        with connection() as db:
            db.execute("SELECT 1")
        connected = True
    except sqlite3.Error:
        connected = False
    return {"status": "ok" if connected else "degraded", "database_connected": connected,
            "ai_configured": bool(os.getenv("GEMINI_API_KEY") or os.getenv("AI_API_KEY")),
            "demo_mode": os.getenv("DEMO_MODE", "false").lower() == "true"}


@app.get("/api/issues", response_model=list[ReportOut])
def list_issues(
    category: str | None = None, severity: str | None = None, status: str | None = None,
    min_lat: float | None = Query(None, ge=-90, le=90), max_lat: float | None = Query(None, ge=-90, le=90),
    min_lng: float | None = Query(None, ge=-180, le=180), max_lng: float | None = Query(None, ge=-180, le=180),
) -> list[dict]:
    clauses, values = [], []
    for field, value in (("category", category), ("severity", severity), ("status", status)):
        if value:
            clauses.append(f"{field} = ?")
            values.append(value)
    for field, op, value in (("latitude", ">=", min_lat), ("latitude", "<=", max_lat),
                             ("longitude", ">=", min_lng), ("longitude", "<=", max_lng)):
        if value is not None:
            clauses.append(f"{field} {op} ?")
            values.append(value)
    query = "SELECT * FROM issues" + ((" WHERE " + " AND ".join(clauses)) if clauses else "") + " ORDER BY created_at DESC LIMIT 500"
    with connection() as db:
        return [report_dict(row) for row in db.execute(query, values).fetchall()]


@app.get("/api/issues/{report_number}", response_model=ReportOut)
def get_issue(report_number: str) -> dict:
    with connection() as db:
        row = db.execute("SELECT * FROM issues WHERE report_number = ?", (report_number,)).fetchone()
        if not row:
            raise HTTPException(404, "Report not found")
        return report_dict(row)


@app.get("/api/issues/{report_number}/history")
def issue_history(report_number: str) -> list[dict]:
    with connection() as db:
        issue = db.execute("SELECT id FROM issues WHERE report_number = ?", (report_number,)).fetchone()
        if not issue:
            raise HTTPException(404, "Report not found")
        return [dict(row) for row in db.execute(
            "SELECT old_status, new_status, note, created_at FROM history WHERE issue_id = ? ORDER BY created_at",
            (issue["id"],)
        ).fetchall()]


@app.get("/api/issues/{report_number}/office")
async def issue_office(report_number: str) -> dict:
    with connection() as db:
        issue = db.execute(
            "SELECT category, location_text FROM issues WHERE report_number = ?",
            (report_number,),
        ).fetchone()
    if not issue:
        raise HTTPException(404, "Report not found")
    try:
        return await find_office_with_gemini(issue["category"], issue["location_text"])
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(502, f"Live office lookup failed: {error}") from error


@app.get("/api/geocode/reverse")
async def reverse_geocode(latitude: float = Query(..., ge=-90, le=90),
                          longitude: float = Query(..., ge=-180, le=180)) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"lat": latitude, "lon": longitude, "format": "jsonv2",
                        "addressdetails": 1},
                headers={"User-Agent": "Ai-LAN civic reporting app"},
            )
        response.raise_for_status()
        address = response.json().get("display_name")
        if not address:
            raise ValueError("No readable address returned")
        return {"address": address}
    except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(502, f"Address lookup failed: {error}") from error


@app.post("/api/issues/{report_number}/status", response_model=ReportOut)
def update_status(
    report_number: str, payload: StatusUpdate, authorization: str | None = Header(default=None)
) -> dict:
    require_roles(authorization, {"government", "admin"})
    with connection() as db:
        row = db.execute("SELECT * FROM issues WHERE report_number = ?", (report_number,)).fetchone()
        if not row:
            raise HTTPException(404, "Report not found")
        if row["status"] == payload.status:
            return report_dict(row)
        timestamp = now()
        db.execute("UPDATE issues SET status = ?, updated_at = ? WHERE report_number = ?",
                   (payload.status, timestamp, report_number))
        db.execute("INSERT INTO history VALUES (?,?,?,?,?,?)",
                   (str(uuid.uuid4()), row["id"], row["status"], payload.status, payload.note, timestamp))
        db.execute(
            "UPDATE issues SET notification_status = ?, updated_at = ? WHERE report_number = ?",
            ("disabled", timestamp, report_number),
        )
        db.commit()
        return report_dict(db.execute("SELECT * FROM issues WHERE report_number = ?", (report_number,)).fetchone())


@app.post("/api/issues", response_model=ReportOut, status_code=201)
async def create_issue(
    description: Annotated[str, Form(...)],
    latitude: Annotated[float, Form(...)],
    longitude: Annotated[float, Form(...)],
    location_text: Annotated[str | None, Form()] = None,
    category: Annotated[str | None, Form()] = None,
    files: list[UploadFile] = File(default=[]),
    authorization: str | None = Header(default=None),
) -> dict:
    if not description.strip():
        raise HTTPException(400, "A description is required")
    if len(description) > 2000:
        raise HTTPException(400, "Description must be 2,000 characters or fewer")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise HTTPException(400, "Choose valid coordinates")
    if not files:
        raise HTTPException(400, "Upload at least one JPG, PNG or WEBP photograph")
    upload_contents: list[tuple[str, bytes, str]] = []
    for file in files:
        if file.content_type not in ALLOWED_TYPES:
            raise HTTPException(400, "Only JPG, PNG and WEBP images are accepted")
        contents = await file.read()
        if not contents or len(contents) > 10 * 1024 * 1024:
            raise HTTPException(413, "Each image must be smaller than 10 MB")
        if not has_image_signature(file.content_type, contents):
            raise HTTPException(400, "The uploaded file does not appear to be a valid image")
        upload_contents.append((file.content_type, contents, file.filename or "evidence"))
    selected_category = category if category in CATEGORIES else "other"
    ai_status = "manual_review"
    ai_note = "AI analysis requires manual review"
    ai_result = None
    try:
        ai_result = await analyze_with_gemini(description.strip(), [(mime, content) for mime, content, _ in upload_contents])
        if ai_result is None:
            ai_status = "not_configured"
            ai_note = "Gemini AI is not configured; set GEMINI_API_KEY in backend/.env"
    except (httpx.HTTPError, ValueError, KeyError, json.JSONDecodeError) as error:
        ai_status = "failed"
        if isinstance(error, httpx.HTTPStatusError) and error.response.status_code == 429:
            ai_note = (
                "Gemini rate limit or quota exceeded; enable billing, wait for the quota reset, "
                "or configure another Gemini project/key; report retained for manual review"
            )
        else:
            ai_note = "Gemini analysis failed; report retained for manual review"
    if ai_result:
        selected_category = ai_result["category"]
        ai_status = "completed"
    issue_type = str(ai_result.get("issue_type", "")).strip() if ai_result else ""
    title = (f"{issue_type.title()} Issue" if issue_type else
             {"roads": "Road Surface Issue", "water_supply": "Water Supply Issue",
              "drainage": "Drainage Issue", "waste_management": "Waste Management Issue"}.get(
                  selected_category, f"{selected_category.replace('_', ' ').title()} Issue"))
    issue_id = str(uuid.uuid4())
    timestamp = now()
    with connection() as db:
        report_number = next_report_number(db)
        authority = find_verified_authority(db, selected_category, location_text)
        authority_id = authority["id"] if authority else None
        db.execute("""INSERT INTO issues
                   (id, report_number, category, title, description, ai_summary, latitude,
                    longitude, location_text, ai_guidance, severity, ai_confidence, status, authority_id,
                    ai_status, notification_status, created_at, updated_at, demo)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (issue_id, report_number, selected_category, title, description.strip(),
                    ai_result["summary"] if ai_result else description.strip(), latitude, longitude,
                    location_text,
                    ai_result["guidance"] if ai_result else "Stay safe, document the issue from a safe distance, and report any immediate danger.",
                    ai_result["severity"] if ai_result else "medium",
                    ai_result["confidence"] if ai_result else 0.0,
                    "authority_verification_pending" if authority_id else "manual_review", "unavailable",
                    ai_status, "pending", timestamp, timestamp, 0))
        db.execute("INSERT INTO history VALUES (?,?,?,?,?,?)",
                   (str(uuid.uuid4()), issue_id, None, "submitted",
                    "Report received; AI analysis completed" if ai_result else ai_note, timestamp))
        if authority_id:
            db.execute("UPDATE issues SET authority_id = ?, status = 'authority_verification_pending' WHERE id = ?",
                       (authority_id, issue_id))
        for mime_type, content, filename in upload_contents:
            safe_name = f"{issue_id}-{Path(filename).name}"
            storage = UPLOAD_DIR / safe_name
            storage.write_bytes(content)
            db.execute("INSERT INTO media VALUES (?,?,?,?,?)",
                       (str(uuid.uuid4()), issue_id, filename, mime_type, str(storage)))
        issue = dict(db.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone())
        db.execute("UPDATE issues SET notification_status = ? WHERE id = ?", ("disabled", issue_id))
        db.commit()
        return report_dict(db.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone())


@app.get("/api/authorities")
def authorities() -> list[dict]:
    with connection() as db:
        return [authority_dict(row) for row in db.execute(
            "SELECT * FROM authorities WHERE active=1 ORDER BY name"
        ).fetchall()]


@app.get("/api/analytics")
def analytics() -> dict:
    with connection() as db:
        total = db.execute("SELECT COUNT(*) FROM issues").fetchone()[0]
        category = {row["category"]: row["count"] for row in db.execute(
            "SELECT category, COUNT(*) count FROM issues GROUP BY category"
        )}
        severity = {row["severity"]: row["count"] for row in db.execute(
            "SELECT severity, COUNT(*) count FROM issues GROUP BY severity"
        )}
        return {"total": total, "pending": db.execute(
            "SELECT COUNT(*) FROM issues WHERE status NOT IN ('resolved','closed','rejected')").fetchone()[0],
                "resolved": db.execute("SELECT COUNT(*) FROM issues WHERE status='resolved'").fetchone()[0],
                "high_priority": db.execute(
                    "SELECT COUNT(*) FROM issues WHERE severity IN ('high','critical')").fetchone()[0],
                "notifications_sent": db.execute(
                    "SELECT COUNT(*) FROM issues WHERE notification_status='sent'").fetchone()[0],
                "category": category, "severity": severity}
