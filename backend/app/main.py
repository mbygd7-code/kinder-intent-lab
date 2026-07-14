"""Kinder Intent Lab — FastAPI 엔트리포인트.

실행: cd backend && uvicorn app.main:app --reload
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.arena_ops import router as arena_ops_router
from app.api.dashboard import router as dashboard_router
from app.api.gym import router as gym_router
from app.api.infer import router as infer_router
from app.api.observatory import router as observatory_router

app = FastAPI(title="Kinder Intent Lab", version="0.1.0")

# 교차 출처 배포용(프론트·백엔드 도메인이 다를 때). CORS_ALLOW_ORIGINS(쉼표구분)가 있을 때만
# 활성화 — 동일출처(Vercel rewrite로 /v1 프록시)면 비워두면 되고 기본 동작은 불변이다.
# 배포 편의 config일 뿐 서빙/live rollout 경로를 여는 게 아니다(문서 §10-2 HOLD).
_cors = os.environ.get("CORS_ALLOW_ORIGINS", "")
_cors_origins = [o.strip() for o in _cors.split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(infer_router)
app.include_router(observatory_router)
app.include_router(dashboard_router)
app.include_router(arena_ops_router)
app.include_router(gym_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
