"""LLM provider 추상화. 공개 인터페이스는 app.llm.client.

실 provider는 여기서 지연 팩토리로 등록한다(SDK import는 build 시점까지 미룬다 — mock 전용
오프라인 환경은 벤더 패키지가 없어도 import된다). 선택은 env(LLM_PROVIDER)로만 — 벤더 하드코딩
은 이 등록 지점(주입 seam)에만 있고 파이프라인/러너 코드엔 없다.
"""
from app.llm.client import register_provider


def _anthropic_factory():
    from app.llm.anthropic_provider import AnthropicProvider

    return AnthropicProvider()


register_provider("anthropic", _anthropic_factory)
