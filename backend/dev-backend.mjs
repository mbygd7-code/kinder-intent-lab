/**
 * 크로스 플랫폼 backend dev 런처 — launch.json의 mac/win venv 경로 전쟁 종결용.
 *
 * launch.json의 backend-dev가 이걸 node로 실행한다(양쪽 머신 모두 node는 있다 —
 * frontend-dev가 npm으로 돈다). OS에 맞는 venv python을 골라 uvicorn을 띄우고
 * stdio·종료 신호를 그대로 전달한다. venv가 없으면 만들라는 안내와 함께 실패한다.
 */
import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'

const py = process.platform === 'win32' ? '.venv\\Scripts\\python.exe' : '.venv/bin/python'

if (!existsSync(py)) {
  console.error(`venv python이 없습니다: backend/${py}`)
  console.error('만들기: python3 -m venv backend/.venv && backend/.venv/bin/pip install -e "backend[dev]"')
  process.exit(1)
}

const child = spawn(py, ['-m', 'uvicorn', 'app.main:app', '--port', '8000'], {
  stdio: 'inherit',
})
child.on('exit', (code) => process.exit(code ?? 1))
for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => child.kill(sig))
}
