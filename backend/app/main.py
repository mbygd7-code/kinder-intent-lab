"""Kinder Intent Lab — FastAPI 엔트리포인트.

실행: cd backend && uvicorn app.main:app --reload
"""
from fastapi import FastAPI

app = FastAPI(title="Kinder Intent Lab", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
