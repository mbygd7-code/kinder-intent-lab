# S5 — Situation Builder 프롬프트 계약 (§1-S5)

## 역할
situation_frame → **canonical scenario**. 여기서 처음으로 "화면"이 생긴다 —
workspace 상태(사진 n장, 텍스트 m개, 선택 상태)와 직전 행동을 프레임에 결합한다.

## 입력 컨텍스트
- Situation Frame (domain, summary, materials, teacher_concern)
- vs-1.0 통제 어휘 목록 (scene_type / activity_types / materials / observed_actions /
  interaction_pattern / group_size_band / spatial_pattern)

## 출력 스키마 (변형 k개 = config.foundry.scenario_variants)
같은 frame에서 workspace 변형 k개를 생성한다 — 선택 유무 × 직전 행동 × 오브젝트 구성.
각 변형:
```json
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
```

## 금지사항 (계약 대칭 — runtime §3-1)
- `visual_semantics`는 vs-1.0 통제 어휘 밖 값을 쓰지 않는다. 자유 서술 금지.
- `identity_removed`는 반드시 true (비식별).
- 합성 생성분은 `extractor_version`을 `SYNTH_BUILDER_*`로 표기해 실측 extractor와 구분한다.
- 변형 수는 정확히 config.foundry.scenario_variants개.
