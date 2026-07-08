"""Label State Machine + Label Aggregator (§3-6).

label_state(워크플로 상태)와 reliability_tier(품질)는 서로 다른 축이다 — 혼용 금지(절대 규칙 8).
state_machine은 label_state 전이만, aggregator는 분포·게이트·tier 추천만 담당한다.
"""
