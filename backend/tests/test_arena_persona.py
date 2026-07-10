"""Persona Lift/Harm AC (§4-2·§5-5, 문서 ③ §4-3).

- Lift = persona 덕에 맞춘 비율, Harm = persona 탓에 틀린 비율 (§4-2 문구 그대로)
- ★ LLM 재호출 0 — prior를 LLM 밖에서 곱하는 §5-5 설계가 이것을 가능하게 한다
- ★ 재정렬 prior는 **run에 stamp된** state_version의 것 (오늘 prior로 과거 run을 채점하지 않는다)
- ★ Arena는 persona_state를 절대 변이하지 않는다 — Harm>Lift여도 '제안 플래그'만 (§8-2 격리)
- 클러스터 없음 → null (0%가 아니다)
"""
import pytest
from sqlalchemy import delete

from app.arena.persona import ItemActivation, clusters_with_prior, persona_lift_harm
from app.core.config import get_config
from app.core.ontology import load_ontology
from app.models.persona import PersonaCluster, PersonaStateVersion, PopulationPrior

CFG = get_config()


@pytest.fixture(autouse=True)
def _empty(db_session):
    for model in (PopulationPrior, PersonaCluster, PersonaStateVersion):
        db_session.execute(delete(model))
    db_session.flush()


def _intents(n=3):
    return [i.intent_id for i in load_ontology().intents if i.domain][:n]


def _seed_cluster(db, cluster_id, state_version, priors: dict[str, float]) -> None:
    if db.get(PersonaStateVersion, state_version) is None:
        seq = 1 if state_version.endswith("1") else 2
        db.add(PersonaStateVersion(version=state_version, seq=seq, reason="test"))
    if db.get(PersonaCluster, cluster_id) is None:
        db.add(PersonaCluster(cluster_id=cluster_id, method="test", axes={},
                              member_count=9, version="pv-1"))
    db.flush()
    for intent, p in priors.items():
        db.add(PopulationPrior(cluster_id=cluster_id, intent_id=intent, prior=p,
                               state_version=state_version))
    db.flush()


def _cfg(**gate_over):
    return CFG.model_copy(update={"gate": CFG.gate.model_copy(update=gate_over)})


def test_null_without_clusters(db_session) -> None:
    """Persona Discovery 미실행 → null. 분포를 지어내지 않는다."""
    a, b, _ = _intents()
    items = [ItemActivation(a, {a: 0.6, b: 0.5})]
    assert persona_lift_harm(db_session, items, "ps-1", CFG) is None


def test_lift_counts_miss_to_hit_flips(db_session) -> None:
    """★ §4-2 'persona 덕에 맞춘 비율' — neutral 오답 → persona 정답 플립만 센다."""
    a, b, _ = _intents()
    # neutral: b(0.6) > a(0.5) → 오답. prior가 a를 밀어주면 정답으로 뒤집힌다.
    _seed_cluster(db_session, "PC_1", "ps-1", {a: 1.0, b: 0.0})
    items = [ItemActivation(a, {a: 0.5, b: 0.6})]

    out = persona_lift_harm(db_session, items, "ps-1", _cfg(persona_eval_min_items=1))
    assert out["PC_1"]["lift"] == 1.0 and out["PC_1"]["harm"] == 0.0
    assert out["PC_1"]["net"] == 1.0
    assert out["PC_1"]["deactivate_recommended"] is False


def test_harm_counts_hit_to_miss_flips_and_recommends_deactivation(db_session) -> None:
    """★ §4-2 'persona 탓에 틀린 비율' + 'Harm > Lift인 클러스터는 prior 비활성화'."""
    a, b, _ = _intents()
    # neutral: a(0.6) > b(0.5) → 정답. prior가 b를 밀어주면 오답으로 뒤집힌다.
    _seed_cluster(db_session, "PC_1", "ps-1", {a: 0.0, b: 1.0})
    items = [ItemActivation(a, {a: 0.6, b: 0.5})]

    out = persona_lift_harm(db_session, items, "ps-1", _cfg(persona_eval_min_items=1))
    assert out["PC_1"]["harm"] == 1.0 and out["PC_1"]["lift"] == 0.0
    assert out["PC_1"]["deactivate_recommended"] is True   # 제안일 뿐 — 아래 테스트 참조


def test_arena_never_mutates_persona_state(db_session) -> None:
    """★ §8-2 격리: KTIB 수치가 추론 상태(prior)로 역류하지 않는다 — 플래그만 남는다."""
    a, b, _ = _intents()
    _seed_cluster(db_session, "PC_1", "ps-1", {a: 0.0, b: 1.0})
    before = {(p.cluster_id, p.intent_id, p.state_version, float(p.prior))
              for p in db_session.query(PopulationPrior).all()}
    versions_before = db_session.query(PersonaStateVersion).count()

    out = persona_lift_harm(db_session, [ItemActivation(a, {a: 0.6, b: 0.5})], "ps-1",
                            _cfg(persona_eval_min_items=1))
    assert out["PC_1"]["deactivate_recommended"] is True

    after = {(p.cluster_id, p.intent_id, p.state_version, float(p.prior))
             for p in db_session.query(PopulationPrior).all()}
    assert after == before                                        # prior 불변
    assert db_session.query(PersonaStateVersion).count() == versions_before  # 새 버전 미발급


def test_rerank_uses_run_stamped_state_version(db_session) -> None:
    """★ 오늘의 prior로 과거 run을 채점하지 않는다 — replay 무결성(결함 D3)."""
    a, b, _ = _intents()
    _seed_cluster(db_session, "PC_1", "ps-1", {a: 1.0, b: 0.0})   # 과거: a를 밀어줌
    _seed_cluster(db_session, "PC_1", "ps-2", {a: 0.0, b: 1.0})   # 현재: b를 밀어줌
    items = [ItemActivation(a, {a: 0.5, b: 0.6})]
    cfg = _cfg(persona_eval_min_items=1)

    old = persona_lift_harm(db_session, items, "ps-1", cfg)
    new = persona_lift_harm(db_session, items, "ps-2", cfg)
    assert old["PC_1"]["lift"] == 1.0 and old["PC_1"]["harm"] == 0.0   # 과거 prior가 구해줌
    assert new["PC_1"]["lift"] == 0.0                                   # 현재 prior는 안 구해줌


def test_no_flip_counts_neither_lift_nor_harm(db_session) -> None:
    """예측이 뒤집히지 않으면 lift도 harm도 아니다 (cap 안에서 prior가 무력한 경우 포함)."""
    a, b, _ = _intents()
    _seed_cluster(db_session, "PC_1", "ps-1", {a: 0.55, b: 0.45})  # 미세 prior, cap 0.2
    items = [ItemActivation(a, {a: 0.9, b: 0.1})]                   # 격차가 커서 안 뒤집힘
    out = persona_lift_harm(db_session, items, "ps-1", _cfg(persona_eval_min_items=1))
    assert out["PC_1"]["lift"] == 0.0 and out["PC_1"]["harm"] == 0.0
    assert out["PC_1"]["deactivate_recommended"] is False  # vacuous prior는 안전하다


def test_sample_below_floor_flagged_and_never_recommends(db_session) -> None:
    """표본이 하한 미만이면 Harm>Lift여도 '비활성화 권고'를 내지 않는다 — 대신 게이트가 FAIL한다."""
    a, b, _ = _intents()
    _seed_cluster(db_session, "PC_1", "ps-1", {a: 0.0, b: 1.0})
    out = persona_lift_harm(db_session, [ItemActivation(a, {a: 0.6, b: 0.5})], "ps-1",
                            _cfg(persona_eval_min_items=99))
    assert out["PC_1"]["sample_below_floor"] is True
    assert out["PC_1"]["deactivate_recommended"] is False
    assert out["PC_1"]["harm"] == 1.0  # 원값은 정직하게 남는다


def test_clusters_with_prior_is_version_scoped(db_session) -> None:
    a, _b, _c = _intents()
    _seed_cluster(db_session, "PC_1", "ps-1", {a: 0.7})
    assert clusters_with_prior(db_session, "ps-1") == ["PC_1"]
    assert clusters_with_prior(db_session, "ps-2") == []
