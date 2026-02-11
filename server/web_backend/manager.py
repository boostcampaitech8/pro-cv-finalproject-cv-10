from __future__ import annotations

import os
from datetime import datetime, time
from typing import Any, Dict, List, Optional

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from pymongo.errors import DuplicateKeyError

load_dotenv()

URI = os.environ.get("URI")
DB_NAME = os.environ.get("DB_NAME", "data_metadata")


class DBManager:
    def __init__(
        self,
        *,
        files_collection: str = "files",
        events_collection: str = "events",
        client_status_collection: str = "client_status",
    ):
        if not URI:
            raise ValueError("URI is empty. Set env URI.")

        self.client = MongoClient(URI, server_api=ServerApi("1"))
        self.client.admin.command("ping")

        self.db = self.client[DB_NAME]
        self.files = self.db[files_collection]
        self.events = self.db[events_collection]
        self.client_status = self.db[client_status_collection]

        self._create_indexes()

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass

    def _create_indexes(self) -> None:
        self.files.create_index([("remote_file_path", 1)], unique=True)
        self.files.create_index([("client_id", 1), ("created_at", -1)])
        self.files.create_index([("created_at", -1)])

        self.events.create_index([("processed", 1), ("created_at", 1)])
        self.events.create_index([("client_id", 1), ("processed", 1), ("created_at", 1)])
        self.events.create_index([("file_id", 1)], unique=True)

        self.client_status.create_index([("client_id", 1)], unique=True)
        self.client_status.create_index([("updated_at", -1)])

    # ---------------------------
    # outbox / events
    # ---------------------------
    def read_unprocessed_events(self, *, limit: int = 50) -> List[Dict[str, Any]]:
        return list(self.events.find({"processed": False}).sort("created_at", 1).limit(int(limit)))

    def mark_event_processed(self, *, event_id: str, processed_at: Optional[datetime] = None) -> None:
        processed_at = processed_at or datetime.utcnow()
        self.events.update_one(
            {"_id": ObjectId(event_id)},
            {"$set": {"processed": True, "processed_at": processed_at}},
        )

    def create_event_for_file(
        self,
        *,
        file_doc: Dict[str, Any],
        processed: bool = False,
    ) -> Optional[Dict[str, Any]]:
        fid = file_doc.get("_id")
        if fid is None:
            return None

        now = datetime.utcnow()
        created_at = file_doc.get("created_at")
        if not isinstance(created_at, datetime):
            created_at = now

        ev = {
            "file_id": fid,
            "client_id": file_doc.get("client_id"),
            "processed": bool(processed),
            "created_at": created_at,
        }
        if processed:
            ev["processed_at"] = now

        try:
            res = self.events.insert_one(ev)
            ev["_id"] = res.inserted_id
            return ev
        except DuplicateKeyError:
            return None

    # ---------------------------
    # client_status
    # ---------------------------
    def get_client_status_list(self, *, limit: int = 200) -> List[Dict[str, Any]]:
        return list(self.client_status.find().sort("updated_at", -1).limit(int(limit)))

    # ---------------------------
    # files helpers
    # ---------------------------
    def read_files_by_ids(self, *, file_ids: List[str]) -> List[Dict[str, Any]]:
        oids = []
        for fid in file_ids:
            try:
                oids.append(ObjectId(fid))
            except Exception:
                pass
        if not oids:
            return []
        return list(self.files.find({"_id": {"$in": oids}}))

    # ---------------------------
    # HISTORY (date-only, created_at is datetime)
    # ---------------------------
    def read_history_events_by_date(
        self,
        *,
        start_date: str,   # "YYYY-MM-DD"
        end_date: str,     # "YYYY-MM-DD"
        client_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        sd = datetime.strptime(start_date, "%Y-%m-%d").date()
        ed = datetime.strptime(end_date, "%Y-%m-%d").date()

        start_dt = datetime.combine(sd, time.min)
        end_dt = datetime.combine(ed, time.max)

        q: Dict[str, Any] = {"created_at": {"$gte": start_dt, "$lte": end_dt}}
        if client_id:
            q["client_id"] = client_id

        file_docs = list(self.files.find(q).sort("created_at", -1).limit(int(limit)))
        if not file_docs:
            return []

        file_oids = [f["_id"] for f in file_docs if f.get("_id") is not None]

        ev_q: Dict[str, Any] = {"file_id": {"$in": file_oids}}
        if client_id:
            ev_q["client_id"] = client_id

        event_docs = list(self.events.find(ev_q).sort("created_at", -1))
        event_by_fid = {str(e["file_id"]): e for e in event_docs if e.get("file_id")}

        out: List[Dict[str, Any]] = []
        for f in file_docs:
            fid = str(f["_id"])
            e = event_by_fid.get(fid)
            if e:
                out.append(e)
            else:
                out.append(
                    {
                        "_id": ObjectId(),
                        "file_id": f["_id"],
                        "client_id": f.get("client_id"),
                        "processed": True,
                        "created_at": f.get("created_at") or datetime.utcnow(),
                        "__virtual": True,
                    }
                )

        return out
