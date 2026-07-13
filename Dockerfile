# Kinder Intent Lab — 백엔드(FastAPI) 컨테이너.
#
# 빌드 컨텍스트 = **저장소 루트** (backend/ 아님). 코드가 config/·seeds/·db/를 repo_root
# 기준(Path(__file__).parents[3])으로 읽으므로 소스 트리 레이아웃을 그대로 유지하고,
# editable 설치로 __file__ 위치를 소스에 고정해 그 경로 계산이 깨지지 않게 한다.
#
# 비밀키(DATABASE_URL·LLM_API_KEY 등)는 이미지에 굽지 않는다 — 런타임 env로만 주입.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 소스 + 런타임 자산(전부 repo_root 기준으로 읽힘)
COPY backend/ ./backend/
COPY config/ ./config/
COPY seeds/ ./seeds/
COPY db/ ./db/

# editable 설치: 의존성 + 실 provider(anthropic/openai) extras. provider는 env로 선택하되,
# 패키지는 미리 깔아둬 LLM_PROVIDER=anthropic 등으로 바꿔도 재빌드가 필요 없게 한다.
RUN pip install -e "./backend[anthropic,openai]"

# 호스트가 주입하는 $PORT를 따른다(기본 8000). 기동 시 마이그레이션 후 서버 실행.
# 단일 인스턴스 가정 — 다중 인스턴스면 마이그레이션을 릴리즈 단계로 분리(docs/10-deploy).
EXPOSE 8000
CMD ["sh", "-c", "cd /app/backend && alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
