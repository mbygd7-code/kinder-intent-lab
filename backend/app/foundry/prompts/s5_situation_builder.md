# S5 — Situation Builder 씨드 확장 프롬프트 계약 (§1-S5)

> 상태(2026-07-17): 화면의 기본값은 **seeds/situation_seeds_v1.yaml의 수동 씨드**가 원천이다.
> 이 프롬프트는 그 씨드(앵커)를 통제 어휘 안에서 변형하는 **확장 모드**로 쓰인다
> (backend/app/foundry/seed_expansion.py — 실패 시 씨드 원본 폴백).

## 역할
사람이 작성한 **앵커 화면 씨드**(킨더버스 화면 상태) 하나를 받아, 유아교사가 실제로 마주칠 법한
**자연스러운 변형 k개**를 만든다 — 선택 유무 × 직전 행동 × 오브젝트 구성을 바꾼다.
변형은 앵커의 "장면 종류"를 존중하되 세부(카드 수, 선택 상태, 행동 순서)를 현실적으로 다양화한다.

## 입력 컨텍스트 (JSON)
- `anchor_seed_id` / `anchor_workspace_state` — 사람이 쓴 앵커 화면 (기준점)
- `allowed.surface_types` / `allowed.actions` / `allowed.object_kinds` — **이 목록 밖 값 사용 금지**
- `variants_required` — 변형 수 k (정확히 이 수만큼)
- `domain` — 이 화면이 소비될 의도 영역 (분위기 참고용)

## 출력 스키마 (JSON만, 코드펜스·주석 금지)
```json
{
  "variants": [
    {
      "surface_type": "play_board",
      "objects_summary": {"photo": 4, "text": 2},
      "selection": {"type": "photo", "count": 2},
      "recent_actions": ["move_object", "zoom_in"],
      "visual_semantics": [
        {
          "object_ref": "photo_1",
          "schema_version": "vs-1.0",
          "extractor_version": "SYNTH_BUILDER_v1",
          "scene_type": ["OUTDOOR_YARD"],
          "activity_types": ["NATURE_SORTING"],
          "materials": ["LEAF", "TRAY"],
          "observed_actions": ["SORT", "COMPARE"],
          "interaction_pattern": ["PEER_COLLABORATIVE"],
          "group_size_band": "SMALL_GROUP",
          "identity_removed": true
        }
      ]
    }
  ]
}
```

## 금지사항 (위반 시 전체 거부됨)
- `variants` 길이는 **정확히 variants_required개**.
- `surface_type`·`recent_actions`·`objects_summary`의 키·`selection.type`은 allowed 목록 안에서만.
- `visual_semantics`는 vs-1.0 통제 어휘만 (자유 서술 금지). `identity_removed`는 반드시 true.
  합성 생성분은 `extractor_version`을 `SYNTH_BUILDER_*`로 표기 (실측 extractor와 구분).
- 정합 유지: 사진이 있으면 사진 서술 ≥1, 사진이 없으면 서술 없음(빈 배열),
  선택 수(`selection.count`)는 화면의 해당 카드 수를 넘지 못한다. 선택 없음은 `selection: {}`.
- 값이 없는 선택 필드는 **키를 생략**한다 — `null` 명시 금지.
- 스키마 밖 키(설명·notes 등) 추가 금지. 계약 대칭: 실서비스 Visual Context Gateway와
  동일 스키마·어휘 (runtime §3-1).
