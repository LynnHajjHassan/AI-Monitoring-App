"""Standalone WSS gateway to let a Mac/Windows developer test without full app."""
from fastapi import FastAPI
from .routes import router

app = FastAPI(title="SceneSense Camera Protocol v1 Dev Gateway", version="1.0")
app.include_router(router)


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok", "protocol": "camera-v1", "note": "Standalone development gateway"}
