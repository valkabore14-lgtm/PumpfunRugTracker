from fastapi import FastAPI, Request
from db import DB
from tracker import process_helius_event

app = FastAPI()
db = DB("db.sqlite")

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/webhook/helius")
async def helius_webhook(req: Request):
    payload = await req.json()
    process_helius_event(db, payload)
    return {"received": True}

@app.post("/seed/{address}")
def add_seed(address: str):
    db.upsert_seed(address)
    return {"seed_added": address}
