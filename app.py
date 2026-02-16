import os
import re
import requests
from datetime import date as dt_date
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_VERSION = "2022-06-28"
NOTION_SESSIONS_DB_ID = os.getenv("NOTION_SESSIONS_DB_ID")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

def normalize_id(s: str) -> str:
    return re.sub(r"[^0-9a-fA-F]", "", s or "")

def rt(text: str):
    return [{"type": "text", "text": {"content": (text or "")[:2000]}}]

class Extraction(BaseModel):
    session_title: str
    date: Optional[str] = None
    domain: Optional[str] = None
    thesis: Optional[str] = None
    antithesis: Optional[str] = None
    synthesis: Optional[str] = None
    open_tensions: Optional[str] = None
    behavioral_commitment: Optional[str] = None
    follow_up_date: Optional[str] = None

app = FastAPI(title="OpenClaw → Notion Webhook")

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/ingest")
def ingest(
    x: Extraction,
    x_webhook_secret: str = Header(default="", alias="X-Webhook-Secret"),
):
    # Protect public endpoint
    if WEBHOOK_SECRET and x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Validate configuration
    if not NOTION_TOKEN:
        raise HTTPException(status_code=500, detail="Missing NOTION_TOKEN")
    if not NOTION_SESSIONS_DB_ID:
        raise HTTPException(status_code=500, detail="Missing NOTION_SESSIONS_DB_ID")

    db_id = normalize_id(NOTION_SESSIONS_DB_ID)
    if len(db_id) < 32:
        raise HTTPException(status_code=500, detail="NOTION_SESSIONS_DB_ID looks invalid")

    # Map to your Notion DB property names (must match exactly)
    props = {
        "Name": {"title": rt(x.session_title)},
        "date": {"date": {"start": (x.date or dt_date.today().isoformat())}},  # lowercase 'date'
    }

    if x.domain:
        props["Domain"] = {"select": {"name": x.domain}}

    if x.thesis is not None:
        props["Thesis"] = {"rich_text": rt(x.thesis)}
    if x.antithesis is not None:
        props["Antithesis"] = {"rich_text": rt(x.antithesis)}
    if x.synthesis is not None:
        props["Synthesis"] = {"rich_text": rt(x.synthesis)}
    if x.open_tensions is not None:
        props["Open Tensions"] = {"rich_text": rt(x.open_tensions)}
    if x.behavioral_commitment is not None:
        props["Behavioral Commitment"] = {"rich_text": rt(x.behavioral_commitment)}
    if x.follow_up_date:
        props["Follow-up Date"] = {"date": {"start": x.follow_up_date}}

    payload = {"parent": {"database_id": db_id}, "properties": props}

    r = requests.post(
        "https://api.notion.com/v1/pages",
        headers=notion_headers(),
        json=payload,
        timeout=20,
    )

    if r.status_code >= 300:
        raise HTTPException(status_code=502, detail={"notion_status": r.status_code, "notion_body": r.text})

    return {"ok": True, "page_id": r.json().get("id")}
