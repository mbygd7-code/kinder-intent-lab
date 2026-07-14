# 배포 가이드 (풀스택)

> 이 저장소를 실제로 띄우는 방법. **설정 파일은 준비돼 있고, 비밀키·DB 연결·실행은 당신이**
> 각 플랫폼에서 합니다 — 자격증명은 코드/AI가 대신 넣지 않습니다.

---

## ⚠️ 먼저 읽기

- **비밀키는 직접.** `DATABASE_URL`, `LLM_API_KEY`, `EMBEDDING_API_KEY`는 각 호스트의 환경변수
  UI에 **당신이** 넣습니다. 저장소·이미지에 굽지 않습니다(`.env`는 gitignore, `.dockerignore` 제외).
- **아직 실험 단계.** 브레인은 미검증입니다(KTIB 0·GOLD 0). live rollout(Suggest/Assist/Auto)은
  설계상 **PARTIAL HOLD**라 이 배포는 **추론·관측(Observatory) 서비스**를 띄우는 것이지 자동
  실행 서비스를 여는 게 아닙니다. 배포 후 화면은 정상적으로 "대부분 어두운 뇌 + 커버리지 0"입니다.
- 배포는 이 문서의 config만 추가하며 서빙/롤아웃 코드는 건드리지 않습니다.

## 아키텍처

```
[브라우저] → Vercel (프론트 정적 + /v1/* 리라이트) → 백엔드(FastAPI 컨테이너) → Supabase(Postgres+pgvector)
```

프론트는 API를 **상대경로 `/v1/...`** 로 부릅니다(코드 변경 불필요). Vercel이 `/v1/*`를 백엔드로
리라이트하므로 브라우저 입장에선 **동일 출처** → CORS가 필요 없습니다. (프론트·백엔드를 다른
도메인에 직접 노출하려면 아래 "대안: CORS" 참고.)

---

## 1) 백엔드 — Docker 컨테이너

포터블 `Dockerfile`(저장소 루트)이 있습니다. Render·Railway·Fly·Cloud Run 등 아무 곳이나 됩니다.

**중요 — 빌드 컨텍스트는 저장소 루트**(backend/ 아님). 코드가 `config/`·`seeds/`·`db/`를
repo_root 기준으로 읽기 때문입니다. 호스트 설정에서 Dockerfile 경로 `./Dockerfile`, 컨텍스트
루트 `.` 로 둡니다.

**주입할 환경변수** (`.env.example` 참고):

| 변수 | 예 | 비고 |
|---|---|---|
| `DATABASE_URL` | `postgresql://...supabase...` | Supabase → Connect → **Session pooler** URI |
| `LLM_PROVIDER` | `anthropic` 또는 `mock` | mock이면 오프라인 합성 |
| `LLM_API_KEY` | `sk-ant-...` | provider가 실제일 때만 |
| `LLM_MODEL` | `claude-opus-4-8` | 선택 |
| `EMBEDDING_PROVIDER` | `openai` 또는 `mock` | DB vector(1536)와 차원 일치 |
| `EMBEDDING_API_KEY` | `sk-...` | 실제 임베딩일 때만 |
| `ARENA_PIN` | `2341`(기본) | 웹 "채점 실행" 버튼 비밀번호 — 오클릭 방지용, 배포 시 변경 권장 |
| `PORT` | (호스트가 주입) | 없으면 8000 |

컨테이너는 **uvicorn만** 실행합니다(마이그레이션은 부팅에 묶지 않음 — 아래 참고). 헬스체크는
`GET /healthz` → `{"status":"ok"}`.

로컬 확인:

```bash
docker build -t kinder-backend .
docker run --rm -p 8000:8000 \
  -e DATABASE_URL='postgresql://...' \
  -e LLM_PROVIDER=mock -e EMBEDDING_PROVIDER=mock \
  kinder-backend
# → http://localhost:8000/healthz
```

> **마이그레이션은 별도 단계(부팅에 안 묶음).** 공유 Supabase DB는 이미 스키마가 있으니 평소엔
> 아무것도 안 해도 됩니다. 부팅마다 alembic을 돌리면 접속·드리프트 실패가 서비스 전체를 죽이기
> 때문에 CMD는 uvicorn만 실행합니다. 스키마를 바꾸는 마이그레이션을 추가했을 때만, 배포와
> 분리해 한 번 실행하세요:
> `cd backend && DATABASE_URL='<supabase pooler>' alembic upgrade head` (로컬 또는 일회성 잡).
> **완전히 빈 새 DB**라면 첫 사용 전에 이 명령을 한 번 돌려야 합니다.

## 2) 프론트 — Vercel

1. Vercel에서 이 저장소를 임포트하고 **Root Directory = `frontend`** 로 설정합니다.
   (`frontend/vercel.json`이 빌드·리라이트를 정의합니다.)
2. `frontend/vercel.json`의 `YOUR-BACKEND-HOST`를 **1)에서 배포한 백엔드 도메인**으로 바꿉니다:
   ```json
   { "source": "/v1/:path*", "destination": "https://kinder-backend.onrender.com/v1/:path*" }
   ```
   (Vercel 리라이트는 env 치환을 지원하지 않아 값이 파일에 직접 들어갑니다.)
3. 배포. 빌드는 `npm run build`(= `tsc --noEmit && vite build`)로 타입체크까지 돕니다.

## 3) 첫 배포 후 점검

- 백엔드: `GET /healthz` 200.
- 프론트: 3D 뇌가 뜨고 우측 상단 "💬 즉석 문답" 버튼이 보임(라이브 연결됨).
- **어두운 뇌 + 커버리지 0은 정상**입니다 — 아직 시험(KTIB)도 검증(GOLD)도 없으니까요.
  진척은 `python scripts/ktib_coverage.py` / `scripts/train_coverage.py`로 확인.

---

## 대안: 리라이트 대신 CORS

프론트와 백엔드를 **각각 다른 도메인에 직접** 노출(리라이트 미사용)하려면 백엔드에
`CORS_ALLOW_ORIGINS`(쉼표구분 프론트 출처)를 주면 됩니다. 예: `https://kinder.vercel.app`.
비워두면 CORS는 비활성이고, 위의 동일출처(리라이트) 방식이면 설정할 필요가 없습니다.

## 배포하지 않는 것

- **채점·훈련·생성 러너**(`run_arena`·`run_campaign` 등)는 웹 서비스가 아니라 **운영자가
  수동/스케줄로** 돌리는 배치입니다. 같은 이미지로 `docker run ... <명령>` 하거나 로컬에서
  실행하세요 — 웹 요청 경로에 두지 않습니다.
- 시험지 등록(GOLD·BENCHMARK_HOLDOUT) 같은 사람-검수 경로도 서비스가 아닌 절차입니다.
