"""Kinder Intent Lab — FastAPI 엔트리포인트.

실행: cd backend && uvicorn app.main:app --reload
"""
from fastapi import FastAPI

from app.api.infer import router as infer_router
from app.api.observatory import router as observatory_router

app = FastAPI(title="Kinder Intent Lab", version="0.1.0")
app.include_router(infer_router)
app.include_router(observatory_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
