from __future__ import annotations

import os
import json
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import unquote

import boto3
from bson import ObjectId  
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from dotenv import load_dotenv

from manager import DBManager

# -----------------------------
# Config
# -----------------------------
load_dotenv()

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:8080")
EVENT_POLL_INTERVAL_SEC = float(os.getenv("EVENT_POLL_INTERVAL_SEC", "1.0"))
EVENT_BATCH = int(os.getenv("EVENT_BATCH", "50"))
STATUS_POLL_INTERVAL_SEC = float(os.getenv("STATUS_POLL_INTERVAL_SEC", "15.0"))

FILE_WATCH_INTERVAL_SEC = float(os.getenv("FILE_WATCH_INTERVAL_SEC", "0.5"))
FILE_WATCH_BATCH = int(os.getenv("FILE_WATCH_BATCH", "50"))

MAX_EVENTS = int(os.getenv("MAX_EVENTS", "50"))

BUCKET = os.getenv("BUCKET", "pro-cv-finalproject-cv-10-ehekafhr")
AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-2")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

app = FastAPI(title="Control Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# SSE Pub/Sub
# -----------------------------
subscribers: List[asyncio.Queue] = []


async def broadcast(payload: dict) -> None:
    dead = []
    for q in subscribers:
        try:
            q.put_nowait(payload)
        except Exception:
            dead.append(q)
    for q in dead:
        if q in subscribers:
            subscribers.remove(q)


EVENTS: List[Dict[str, Any]] = []          
EVENT_BY_ID: Dict[str, Dict[str, Any]] = {}
CLIENT_STATUS: List[Dict[str, Any]] = []


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _push_event_cache(ev: Dict[str, Any]) -> None:
    EVENTS.insert(0, ev)
    EVENT_BY_ID[ev["event_id"]] = ev

    if len(EVENTS) > MAX_EVENTS:
        for old in EVENTS[MAX_EVENTS:]:
            EVENT_BY_ID.pop(old["event_id"], None)
        del EVENTS[MAX_EVENTS:]


def _normalize_event(event_doc: Dict[str, Any], file_doc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    event_id = str(event_doc.get("_id"))
    file_id = event_doc.get("file_id")
    client_id = event_doc.get("client_id")

    ts = _now_iso()
    created_at = event_doc.get("created_at")
    if isinstance(created_at, datetime):
        ts = created_at.isoformat() + "Z"

    remote_file_path = None
    location_name = None
    metadata: Dict[str, Any] = {}
    caption = None
    report = None
    file_created_at = None
    file_updated_at = None

    if file_doc:
        remote_file_path = file_doc.get("remote_file_path")
        location_name = file_doc.get("location_name")
        metadata = file_doc.get("metadata") or {}
        caption = file_doc.get("caption")
        report = file_doc.get("report")

        fc = file_doc.get("created_at")
        fu = file_doc.get("updated_at")
        if isinstance(fc, datetime):
            file_created_at = fc.isoformat() + "Z"
        else:
            file_created_at = fc
        if isinstance(fu, datetime):
            file_updated_at = fu.isoformat() + "Z"
        else:
            file_updated_at = fu

    out = {
        "event_id": event_id,
        "file_id": str(file_id) if file_id is not None else None,
        "client_id": client_id,
        "timestamp": ts,
        "processed": bool(event_doc.get("processed", False)),
        "processed_at": (event_doc.get("processed_at").isoformat() + "Z")
        if isinstance(event_doc.get("processed_at"), datetime)
        else None,
        "file": {
            "created_at": file_created_at,
            "updated_at": file_updated_at,
            "location_name": location_name,
            "remote_file_path": remote_file_path,
            "caption": caption,
            "report": report,
        },
        "location_name": location_name,
        "metadata": metadata,
        "caption": caption,
        "report": report,
        "__virtual": bool(event_doc.get("__virtual", False)),
    }

    rfp = (out.get("file") or {}).get("remote_file_path")
    if rfp:
        out["image_url"] = f"/files/{rfp}"

    return out


def _parse_date(s: str) -> str:
    s = (s or "").strip()
    try:
        datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        raise HTTPException(status_code=400, detail="start/end must be YYYY-MM-DD")
    return s


# -----------------------------
# Endpoints
# -----------------------------
@app.get("/events")
async def get_events(limit: int = 50):
    lim = min(int(limit), int(MAX_EVENTS))
    return EVENTS[:lim]


@app.get("/events/history")
async def history_events(
    start: str,
    end: str,
    client_id: str = "ALL",
    limit: int = 200,
):
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end must be >= start")

    cid: Optional[str] = None if (not client_id or client_id == "ALL") else client_id

    db = DBManager()
    try:
        ev_docs = db.read_history_events_by_date(
            start_date=start_date,
            end_date=end_date,
            client_id=cid,
            limit=int(limit),
        )

        file_ids: List[str] = []
        for e in ev_docs:
            fid = e.get("file_id")
            if fid is None:
                continue
            file_ids.append(str(fid))

        files = db.read_files_by_ids(file_ids=file_ids) if file_ids else []
        file_by_id = {str(f["_id"]): f for f in files if f.get("_id")}

        out: List[Dict[str, Any]] = []
        for e in ev_docs:
            fid = e.get("file_id")
            fdoc = file_by_id.get(str(fid)) if fid is not None else None
            out.append(_normalize_event(e, fdoc))

        out.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
        return out
    finally:
        db.close()


@app.get("/events/{event_id}")
async def get_event_detail(event_id: str):
    ev = EVENT_BY_ID.get(event_id)
    if ev:
        return ev

    db = DBManager()
    try:
        try:
            oid = ObjectId(event_id)
        except Exception:
            raise HTTPException(status_code=404, detail="event not found")

        ev_doc = db.events.find_one({"_id": oid})
        if not ev_doc:
            raise HTTPException(status_code=404, detail="event not found")

        file_doc = None
        fid = ev_doc.get("file_id")
        if fid is not None:
            file_doc = db.files.find_one({"_id": fid})

        ui_event = _normalize_event(ev_doc, file_doc)

        return ui_event
    finally:
        db.close()


@app.get("/client_status")
async def get_client_status():
    return CLIENT_STATUS


# -----------------------------
# files proxy (S3)
# -----------------------------
@app.get("/files/{path:path}")
async def get_file(path: str):
    if not (AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY):
        raise HTTPException(status_code=500, detail="AWS creds missing")

    s3 = boto3.client(
        "s3",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )

    key = unquote(path)
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=key)
        body = obj["Body"].read()
        ctype = obj.get("ContentType", "application/octet-stream")
        return Response(content=body, media_type=ctype)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"file not found: {e}")


# -----------------------------
# SSE
# -----------------------------
@app.get("/stream")
async def stream():
    q: asyncio.Queue = asyncio.Queue()
    subscribers.append(q)

    async def event_generator():
        try:
            while True:
                payload = await q.get()
                kind = payload.get("kind", "message")
                yield f"event: {kind}\n"
                yield f"data: {json.dumps(payload, default=str)}\n\n"
        finally:
            if q in subscribers:
                subscribers.remove(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# -----------------------------
# Background tasks
# -----------------------------
async def poll_outbox_forever() -> None:
    db = DBManager()
    print(f"[outbox] poller started interval={EVENT_POLL_INTERVAL_SEC}s batch={EVENT_BATCH}")

    while True:
        try:
            docs = db.read_unprocessed_events(limit=EVENT_BATCH)
            for ev in docs:
                try:
                    file_doc = db.files.find_one({"_id": ev.get("file_id")})
                    ui_event = _normalize_event(ev, file_doc)

                    _push_event_cache(ui_event)
                    await broadcast({"kind": "new_event", "event": ui_event})

                    db.mark_event_processed(event_id=str(ev["_id"]))

                except Exception as e:
                    print(f"[outbox] process error: {e}")
        except Exception as e:
            print(f"[outbox] poll error: {e}")

        await asyncio.sleep(EVENT_POLL_INTERVAL_SEC)


async def poll_files_to_events_forever() -> None:
    db = DBManager()
    print(f"[files->events] watcher started interval={FILE_WATCH_INTERVAL_SEC}s batch={FILE_WATCH_BATCH}")

    last_seen_id: Optional[ObjectId] = None
    try:
        last = list(db.files.find({}, {"_id": 1}).sort("_id", -1).limit(1))
        if last and last[0].get("_id"):
            last_seen_id = last[0]["_id"]
    except Exception:
        last_seen_id = None

    while True:
        try:
            q: Dict[str, Any] = {}
            if last_seen_id is not None:
                q = {"_id": {"$gt": last_seen_id}}

            new_files = list(
                db.files.find(q).sort("_id", 1).limit(int(FILE_WATCH_BATCH))
            )

            for fdoc in new_files:
                oid = fdoc.get("_id")
                if isinstance(oid, ObjectId):
                    last_seen_id = oid

                ev = db.create_event_for_file(file_doc=fdoc, processed=False)
                if not ev:
                    continue

                ui_event = _normalize_event(ev, fdoc)
                _push_event_cache(ui_event)
                await broadcast({"kind": "new_event", "event": ui_event})

                db.mark_event_processed(event_id=str(ev["_id"]))

        except Exception as e:
            print(f"[files->events] error: {e}")

        await asyncio.sleep(FILE_WATCH_INTERVAL_SEC)


async def poll_client_status_forever() -> None:
    db = DBManager()
    print(f"[status] poller started interval={STATUS_POLL_INTERVAL_SEC}s")

    while True:
        try:
            docs = db.get_client_status_list(limit=200)
            out = []
            for d in docs:
                dd = dict(d)
                if "_id" in dd:
                    dd["_id"] = str(dd["_id"])
                if isinstance(dd.get("updated_at"), datetime):
                    dd["updated_at"] = dd["updated_at"].isoformat() + "Z"
                out.append(dd)

            global CLIENT_STATUS
            CLIENT_STATUS = out
            await broadcast({"kind": "client_status", "clients": out})
        except Exception as e:
            print(f"[status] poll error: {e}")

        await asyncio.sleep(STATUS_POLL_INTERVAL_SEC)


@app.on_event("startup")
async def on_startup():
    asyncio.create_task(poll_outbox_forever())
    asyncio.create_task(poll_client_status_forever())
    asyncio.create_task(poll_files_to_events_forever())
