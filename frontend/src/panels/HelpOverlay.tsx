/**
 * 도움말 오버레이 — 교사용 서비스 설명서 + 사용설명서 + 시험 문항 만들기.
 *
 * 원문: docs/09-teacher-guide/{service-overview,user-manual,exam-authoring}.md — 함께 갱신.
 * 다운로드 파일은 frontend/public/(시작 YAML·PDF 3종). 화면 용어는 실제 UI와 일치.
 * 쉬운 문장·큰 글씨.
 */
import { useMemo, useState } from 'react'

import { useBrainStore } from '../brain3d/store'
import { ExamUpload } from './ExamUpload'
import { labelOf } from './intentLabels'

type Tab = 'service' | 'manual' | 'exam' | 'study'

function ServiceGuide() {
  return (
    <div className="help-doc">
      <h3>🌟 왜 이 뇌를 키워야 하나요?</h3>
      <p className="help-note">
        <strong>선생님이 가르친 만큼, 킨더버스가 "말귀 알아듣는 서비스"로 바뀝니다.</strong>{' '}
        하루 수십 번의 메뉴 찾기·반복 클릭이 <strong>평소 말투 한마디</strong>로 줄어드는 것 —
        그 미래는 선생님의 답 없이는 오지 않아요.
      </p>

      <h3>장면으로 보면 — 하원 30분 전</h3>
      <p>
        오늘 물감놀이 사진 30장을 학부모께 보내야 해요. 잘 나온 컷 고르고, 다른 반 아이
        얼굴 가리고, 알림장 쓰고, 발송까지.
      </p>
      <table className="help-table">
        <tbody>
          <tr>
            <td>지금</td>
            <td>사진첩 → 잘 나온 것 고르기 → 편집 → 얼굴 가리기 → 알림장 쓰기 → 첨부 →
              대상 선택 → 발송… <b>메뉴 4곳, 수십 번 클릭</b></td>
          </tr>
          <tr>
            <td>뇌가 자라면</td>
            <td>🗣 <b>"오늘 물감놀이 사진 잘 나온 것만 얼굴 가려서 부모님들께 보내줘"</b> —
              뇌가 순서대로 준비하고, 선생님은 <b>마지막 확인만</b></td>
          </tr>
        </tbody>
      </table>
      <p className="help-note">
        같은 방식으로 — 🗣 "지우 오늘 병결로 해줘"(출결 기록) · "작년 운동회 계획안 어디
        있지?"(자료 검색) · "이 알림장 내일 아침에 나가게 해줘"(예약 발송) · "방금 그 상황
        기록해줘"(관찰 기록). 이 화면의 <strong>점 63개가 전부 이런 업무 하나씩</strong>이에요.
      </p>

      <h3>선생님께 돌아오는 것</h3>
      <table className="help-table">
        <tbody>
          <tr>
            <td>⏱ 시간</td>
            <td>위 장면처럼 여러 단계 업무가 한마디로. 줄어든 잔업 시간은{' '}
              <b>아이들 곁으로</b> 돌아가요</td>
          </tr>
          <tr>
            <td>🙋 내게 맞춤</td>
            <td>같은 "알림장 정리해줘"도 A선생님껜 <b>문장 다듬기</b>, B선생님껜{' '}
              <b>사진 배치</b>일 수 있죠 — 쓸수록 <b>내 뜻</b>으로 알아들어요 (영향엔
              상한선이 있어 치우치지 않아요)</td>
          </tr>
          <tr>
            <td>🛡 실수 방지</td>
            <td>학부모 전송·출결 기재·자료 삭제 같은 <b>되돌릴 수 없는 7가지</b>는 확신이
              없으면 실행하지 않고 되물어요 — "지우 가정에만 보낼까요, 반 전체에
              보낼까요?" 실수 대신 확인.</td>
          </tr>
          <tr>
            <td>⭐ 내 기여</td>
            <td>오늘 가르친 "우리끼린 가정통신문이라고 해요" 하나가, 내일{' '}
              <b>모든 선생님</b>의 킨더버스를 그 말로 알아듣게 만들어요</td>
          </tr>
        </tbody>
      </table>

      <h3>다른 방법으로 만들면 안 되나요? — 룰베이스·챗봇과의 차이</h3>
      <p>
        <strong>① 라우터식 룰베이스</strong> — "키워드가 보이면 그 기능으로 보낸다"는 규칙을
        쌓는 방식이에요. 명령이 열 개쯤일 땐 싸고 예측 가능해서 훌륭하죠. 그런데 현장의
        말에는 <b>키워드가 없는 경우</b>가 많아요: 🗣{' '}
        <b>"다온이 할머니가 데려가셔서 조퇴야"</b> — '기록'도 '출결'도 없지만 뜻은 출결
        기록이에요. 결국 교사가 기계용 "마법의 단어"를 외워야 해요. 반대로 키워드가{' '}
        <b>배신</b>하기도 해요: "지워 → 자료 삭제" 규칙을 만들면, 반에 <b>'지우'</b>가 있는
        순간 🗣 "지우 사진 좀 보여줘"가 <b>삭제로 오발</b>돼요. 63개 업무 × 수천 가지
        말투를 규칙으로 덮으면 규칙끼리 충돌하는 스파게티가 되는데 전체 정확도는{' '}
        <b>잴 방법이 없고</b>, 규칙은 항상 100% 확신이라 <b>"애매하면 되묻기"가 구조적으로
        불가능</b>해요 — 위험한 7가지엔 제일 치명적이죠. 그리고 아무리 써도 데이터가
        자산으로 <b>쌓이지 않아요</b>.
      </p>
      <p>
        <strong>② 범용 챗봇(LLM 그대로)</strong> — 말은 잘 알아듣는 것 같지만, 화면 맥락
        없이 <b>"이거 좀 정리해줘"</b>가 사진 정리인지 자료함 정리인지 문장 다듬기인지
        구별 못 하고, 정확도를 <b>증명 못 하고</b>, 위험한 순간에도 자신만만하게 실행해요.
      </p>
      <table className="help-table">
        <tbody>
          <tr>
            <td></td>
            <td><b>① 룰베이스</b></td>
            <td><b>② 범용 챗봇</b></td>
            <td><b>③ 킨더브레인</b></td>
          </tr>
          <tr>
            <td>키워드 없는 말</td>
            <td>못 잡음</td>
            <td>대충 추측</td>
            <td>말+화면+행동+말버릇으로 추론</td>
          </tr>
          <tr>
            <td>키워드 충돌 ('지우'=이름)</td>
            <td>오발 사고</td>
            <td>복불복</td>
            <td>맥락으로 구별, 애매하면 되물음</td>
          </tr>
          <tr>
            <td>새 말투 대응</td>
            <td>개발자가 규칙 추가</td>
            <td>운에 맡김</td>
            <td><b>선생님이 가르치면 학습</b></td>
          </tr>
          <tr>
            <td>전체 정확도</td>
            <td>측정 불가</td>
            <td>증명 못 함</td>
            <td>주 1회 시험 (목표 80%)</td>
          </tr>
          <tr>
            <td>위험한 순간</td>
            <td>걸리면 무조건 실행</td>
            <td>자신만만 실행</td>
            <td>확신 없으면 되물음 (오발률 2% 기준)</td>
          </tr>
          <tr>
            <td>쓸수록 쌓이는 것</td>
            <td>규칙 부채</td>
            <td>없음</td>
            <td><b>현장 데이터 = 해자</b></td>
          </tr>
        </tbody>
      </table>
      <p className="help-note">
        참고로 킨더브레인은 규칙을 버리지 않아요 — 명백한 패턴 규칙은 <b>여러 증거 중
        하나</b>로 흡수하되(규칙 혼자 결정하지 않음), 최종 판단은 학습된 뇌가 하고 그
        실력은 시험으로 검증받아요.
      </p>

      <h3>이게 왜 서비스 경쟁력이 되나요?</h3>
      <ol>
        <li>
          <strong>현장 데이터 해자</strong> — 실제 선생님들이 가르친 발화·의도 데이터는
          돈 주고도 못 사요. 쓰는 교사가 늘수록 데이터가 쌓이고 → 서비스가 편해지고 →
          더 많이 쓰게 되는 <b>선순환</b>은 경쟁사가 복제할 수 없어요.
        </li>
        <li>
          <strong>증명하는 정확도</strong> — "저희 AI 똑똑해요"가 아니라{' '}
          <b>"전문가 출제 시험에서 기준을 넘긴 버전만 내보냅니다"</b>라고 말할 수 있어요.
          원장님·학부모를 설득하는 언어가 달라져요.
        </li>
        <li>
          <strong>안전을 숫자로</strong> — 되돌릴 수 없는 행동(학부모 전송·출결·삭제)은
          별도 안전 시험을 통과해야만 서비스에 연결돼요. 유아 데이터를 다루는 서비스에선
          이 신뢰가 곧 선택의 이유예요.
        </li>
      </ol>

      <p className="help-note">
        🌱 컴퓨터 연습문제는 뼈대일 뿐, 진짜 교과서는 선생님의 답뿐이에요.{' '}
        <strong>강화하기 한 판 = 문제 6개 = 교과서 6줄.</strong> 오늘의 5분이 내일 모든
        선생님의 몇 시간이 되어 돌아옵니다.
      </p>

      <h3>한 문장으로 말하면</h3>
      <p className="help-note">
        선생님의 <strong>말귀를 알아듣는 뇌</strong>(인공지능)를 키우고, 그 뇌가{' '}
        <strong>얼마나 자랐는지</strong> 눈으로 보여주는 화면이에요.
      </p>
      <p>
        🗣️ "어제 민준이 관찰한 거 정리해서 알림장에 넣어줘" → 🧠 "관찰 기록 찾고 → 문서로
        정리하고 → 학부모께 보내려는 거구나!" — 이런 <strong>속뜻 알아차리기</strong>를
        배우는 중입니다.
      </p>
      <p>
        🌱 뇌는 <strong>배우는 중인 아이</strong>와 같아요. 처음엔 어둡고(잠자는 뇌), 배우면
        알록달록해지고, 시험을 보면 성적만큼 빛나요.{' '}
        <strong>화면이 어두운 건 고장이 아니라 "공부 중"</strong>이라는 뜻!
      </p>

      <h3>뇌의 7개 영역 — 색깔 업무 지도</h3>
      <table className="help-table">
        <tbody>
          <tr><td>🟢 놀이</td><td>"이 놀이 더 넓혀줘" · 활동 전환</td></tr>
          <tr><td>🔵 관찰</td><td>"민준이 오늘 어땠어?" · 관찰 요약</td></tr>
          <tr><td>🟠 문서</td><td>알림장 초안 · 맞춤법</td></tr>
          <tr><td>🟣 시각</td><td>사진 정리 · 자르기 · 꾸미기</td></tr>
          <tr><td>🩷 소통</td><td>학부모 안내 · 회신 모으기</td></tr>
          <tr><td>🟡 운영</td><td>자료 검색 · 일정 · 정리</td></tr>
          <tr><td>🩵 성찰</td><td>하루 돌아보기 · 도움 필요한 아이 찾기</td></tr>
        </tbody>
      </table>
      <p>
        영역 속 <strong>점 하나 = 배우는 "의도" 하나</strong>예요. 지금은 모두 63개.
      </p>

      <h3>뇌는 어떻게 배우나요? — 4가지 길</h3>
      <ol>
        <li>
          <strong>① 컴퓨터 연습문제 (자동)</strong> — 현장에서 나올 법한 말을 컴퓨터가 많이
          지어내요. 여러 인공지능의 교차 검토를 통과해야 저장되고, "컴퓨터 생성" 등급으로
          낮게 취급해요.
        </li>
        <li>
          <strong>② 선생님이 직접 가르치기 ⭐</strong> — [🚀 강화하기]로 문제를 풀면{' '}
          <strong>선생님의 답이 그대로 뇌의 교과서</strong>가 돼요. 제일 귀한 데이터!
        </li>
        <li>
          <strong>③ 2인 검증 GOLD</strong> — 두 명 이상이 따로 검토해 일치해야만 금(GOLD)
          등급. 화면의 <strong>금색 반짝임</strong>이 이 데이터예요.
        </li>
        <li>
          <strong>④ 전문가 시험지</strong> — 전문가가 실력 측정용 시험지를 만들어요.{' '}
          <strong>시험 문제로는 절대 공부시키지 않아요</strong> (미리 보고 외우면 실력이
          아니니까요).
        </li>
      </ol>

      <h3>이 화면의 약속 — 모르면 모른다고 말해요</h3>
      <table className="help-table">
        <tbody>
          <tr><td>빛남</td><td><strong>시험 성적만.</strong> 공부량은 점을 키울 뿐, 시험을 봐야 빛나요</td></tr>
          <tr><td>"—"</td><td>아직 안 잰 점수 (0%가 아니에요)</td></tr>
          <tr><td>MOCK</td><td>데모(가짜) 데이터 딱지</td></tr>
        </tbody>
      </table>

      <h3>성장 6단계</h3>
      <p>
        💤 잠듦 → ✨ 첫 시험 → 영역 절반 측정 → 영역 평균 70% → 영역 간 혼동 개선 → 🎉{' '}
        <strong>전체 80% 달성(최종 목표)</strong>. 바닥 동심원이 단계마다 하나씩 켜지고,
        바깥 호가 전체 점수예요.
      </p>

      <h3>내 정보는 안전한가요?</h3>
      <ul>
        <li>답변은 뇌 교육에만 쓰이고, 이름 대신 <strong>암호화된 표식</strong>으로 저장돼요</li>
        <li>성향 분석은 개인이 아닌 <strong>여러 명 묶음 단위</strong>로만 해요</li>
        <li>성향이 뇌에 주는 영향에는 <strong>상한선</strong>이 있어요</li>
      </ul>
    </div>
  )
}

function ManualGuide() {
  return (
    <div className="help-doc">
      <h3>🧭 처음이라면 — 순서는 이렇게</h3>
      <table className="help-table">
        <tbody>
          <tr>
            <td>① 시험지 만들기</td>
            <td>검수자 두 분이 <b>시험 문항</b>을 만들어요 — 상단 <b>[📄 시험지 검수]</b>{' '}
              또는 도움말 → 시험 문항 만들기. <b>위험 의도 7개부터</b> 권장</td>
          </tr>
          <tr>
            <td>② 채점 (주 1회)</td>
            <td>운영자가 채점을 돌리면 → <b>뇌가 처음으로 밝아져요</b> (지금 실력만큼)</td>
          </tr>
          <tr>
            <td>③ 가르치기 (상시)</td>
            <td>모든 선생님이 <b>강화하기·즉석 문답</b>으로 가르치고 → 다음 채점 때 더 밝게</td>
          </tr>
        </tbody>
      </table>
      <p className="help-note">
        외울 건 한 줄: <b>공부 = 점이 커짐 · 시험 = 점이 빛남.</b> 시험지가 없으면 아무리
        가르쳐도 빛나지 않아요(고장 아님) — 그래서 ①이 먼저예요.
      </p>

      <h3>화면 한눈에</h3>
      <p>
        <b>상단 바</b> — 가운데 전체 점수("—%"면 시험 전) · 오른쪽{' '}
        <b>[📄 시험지 검수] [💬 즉석 문답] [❔ 도움말]</b>
        <br />
        <b>왼쪽</b> 전체 점수·영역 목록 / <b>가운데</b> 3D 뇌 / <b>오른쪽</b> 점 상세·진단 /{' '}
        <b>하단 중앙</b> [2D 지도로 보기]
      </p>

      <h3>뇌 읽는 법 — 이 표 하나면 끝!</h3>
      <table className="help-table">
        <tbody>
          <tr><td>점이 크다</td><td>공부를 많이 했어요</td></tr>
          <tr><td>점이 빛난다</td><td>시험 성적이 좋아요 — <b>시험 전엔 모두 어두움(정상!)</b></td></tr>
          <tr><td>흰 고리</td><td>새로 공부함 — 재시험 대기 중</td></tr>
          <tr><td>입자 구름</td><td>공부한 만큼 선명·풍성해져요</td></tr>
          <tr><td>금색 반짝임</td><td>2인 검증 GOLD·전문가 데이터</td></tr>
          <tr><td>점선 연결</td><td>"헷갈릴 수 있다"는 예상 (측정 전)</td></tr>
          <tr><td>실선+깜빡임</td><td>시험에서 진짜 헷갈린 것</td></tr>
          <tr><td>바닥 동심원·호</td><td>성장 단계 · 전체 점수</td></tr>
        </tbody>
      </table>

      <h3>기본 조작 — 30초면 배워요</h3>
      <ul>
        <li><b>드래그</b> 돌리기 · <b>휠</b> 확대축소 · <b>빈 곳 클릭</b> 선택 취소</li>
        <li><b>영역에 마우스 올리기</b> → 그 영역만 반짝 살아나요</li>
        <li><b>점 클릭</b> → 오른쪽 상세 + 점선 부채꼴 + "왜 연결됐는지" 카드</li>
        <li>"헷갈리는 의도 연결" 카드 <b>[전체 보기]</b> → 예상 연결 전부 보기</li>
      </ul>

      <h3>💬 즉석 문답 — 아무 말이나 시켜보세요</h3>
      <ol>
        <li>상단 <b>[💬 즉석 문답]</b> → 평소 말 그대로 입력 — "지우 오늘 병결로 해줘"</li>
        <li>뇌가 <b>후보 3~4개</b>로 추측해요</li>
        <li>맞으면 그 후보 선택(=확인) · 틀리면 정답 고르기(=교정 — <b>제일 귀한 가르침</b>)</li>
        <li>후보에 없으면 <b>전체 의도 검색</b>으로 정답 지정 · 진짜 새로운 일이면 "새 의도
          제안"</li>
      </ol>
      <p className="help-note">
        내 판정은 바로 교과서가 돼요(점 커짐 + 흰 고리). 단 <b>점수(빛)는 안 변해요</b> —
        그건 시험만 바꿔요. <b>"시험 문제로 출제"</b> 토글을 켜면 훈련에 안 쓰고{' '}
        <b>검수 대기열</b>로 가요 — 같은 문장을 공부·시험 양쪽에 쓸 수 없거든요.
      </p>

      <h3>🚀 강화하기 — 약한 점 집중 과외</h3>
      <ol>
        <li>약한 점 찾기 — 왼쪽 <b>TOP WEAK NODES</b> 또는 작고 어두운 점 클릭</li>
        <li><b>[🚀 강화하기]</b> 클릭 → 훈련 브리핑 확인</li>
        <li>
          방식 고르기: <b>의도 알아맞히기</b> / <b>알맞은 의미 고르기</b> /{' '}
          <b>바로잡기 연습</b>
        </li>
        <li>문제 풀고 <b>[제출하기]</b></li>
      </ol>
      <p className="help-note">
        제출하면: 내 답이 교과서로 저장(⭐사람 확인 등급) → 점이 <b>즉시 커지고</b> 흰 고리
        점등 → <b>다음 시험 후</b> 성적만큼 빛나요. <br />
        ⚠️ 제출 직후 안 빛나는 건 정상! 공부=커짐, 시험=빛남.
      </p>

      <h3>📄 시험 문항 만들기 — 두 가지 방법</h3>
      <table className="help-table">
        <tbody>
          <tr>
            <td>웹에서 바로</td>
            <td><b>[📄 시험지 검수]</b> → 문항 작성 탭에서 질문 + 1~5점 제출 → 다른 분이{' '}
              <b>검수 대기</b> 탭에서 점수 안 보고(blind) 1~5점 → 일치도 통과 시 [등록]</td>
          </tr>
          <tr>
            <td>엑셀로 한꺼번에</td>
            <td>도움말 → <b>시험 문항 만들기</b>에서 양식 받기(⭐CRITICAL 7개 먼저) →
              질문 쓰고 두 분이 O/X → 업로드</td>
          </tr>
        </tbody>
      </table>
      <p className="help-note">
        규칙은 둘 다 같아요: <b>서로 다른 2인</b> · 사람이 쓴 진짜 질문만 · 공부용과 안
        겹치게. 일치도(kappa)는 자동 계산돼요.
      </p>

      <h3>내 답은 어디로 가나요?</h3>
      <p>
        답 1개 → "문장+상황+선택"으로 저장 → 등급: 컴퓨터 생성 &lt; 행동 신호 &lt;{' '}
        <b>⭐내 답(사람 확인)</b> &lt; GOLD(2인 검증) &lt; 전문가 → 크기·입자 즉시 반영 →
        다음 시험에서 실력 측정. 함정 문제 답은 따로 보관돼 통계를 흐리지 않아요.
      </p>

      <h3>자주 묻는 질문</h3>
      <ul className="help-faq">
        <li><b>뭐부터 해야 해요?</b> 시험지부터! 맨 위 "처음이라면" 순서(①→②→③)대로.</li>
        <li><b>뇌가 어두워요.</b> 정상! 빛=시험 성적뿐인데 아직 시험 전이에요.</li>
        <li><b>"—%"가 떠요.</b> "아직 안 재봤다"는 뜻. 0%가 아니에요.</li>
        <li><b>훈련해도 안 빛나요.</b> 훈련=커짐+고리, 시험=빛남. 다음 시험 후 반영!</li>
        <li><b>즉석 문답 답이 점수에 반영되나요?</b> 공부량(크기·고리)엔 즉시, 점수(빛)는
          다음 시험에서만.</li>
        <li>
          <b>"백엔드 미연결"이 떠요.</b> 서버가 꺼진 상태 — 관리자에게 알려주세요. [데모
          노드 보기]는 구경용(MOCK 딱지).
        </li>
        <li><b>이름이 저장되나요?</b> 아니요 — 암호화된 표식으로만 저장돼요.</li>
        <li><b>3D가 느려요.</b> 하단 [2D 지도로 보기]로 전환하세요. 기능은 같아요.</li>
      </ul>

      <h3>좋은 답 요령 🌱</h3>
      <p>
        평소 말투로 · 모르면 넘어가기 · 헷갈릴수록 신중히 · 짧게 자주(5분). 선생님의 답
        하나하나가 뇌의 교과서가 됩니다 💛
      </p>
    </div>
  )
}

function ExamGuide() {
  return (
    <div className="help-doc">
      <h3>시험 문항이 뭐예요?</h3>
      <p>
        문항 하나 = <strong>문제(선생님이 실제로 할 법한 말)</strong> +{' '}
        <strong>정답(63개 의도 중 하나)</strong>. 뇌가 문제만 보고 정답을 맞히면 득점이에요.
      </p>
      <table className="help-table">
        <tbody>
          <tr><td>문제 예</td><td>🗣 "지우 어머니한테 오늘 낮잠 못 잤다고 전해줘"</td></tr>
          <tr><td>정답 예</td><td>개별 학부모 메시지</td></tr>
        </tbody>
      </table>

      <h3>만드는 방법은 두 가지</h3>
      <table className="help-table">
        <tbody>
          <tr>
            <td>웹에서 바로</td>
            <td>상단 <b>[📄 시험지 검수]</b> — 자리에서 몇 문항씩. 질문+1~5점 제출 →
              다른 분이 점수 안 보고(blind) 검수 → 등록</td>
          </tr>
          <tr>
            <td>엑셀로 한꺼번에</td>
            <td>여럿이 나눠 대량으로 만들 때 — <b>아래 ①~④</b>를 따라 하세요</td>
          </tr>
        </tbody>
      </table>

      <h3>① 양식 받기</h3>
      <div className="help-download">
        <a className="view-toggle help-dl-btn" href="/ktib_critical7_template.csv" download>
          ⭐ CRITICAL 7개 먼저 받기 (권장 · 7×30칸)
        </a>
        <a className="view-toggle help-dl-btn" href="/ktib_exam_template.csv" download>
          ⬇ 전체 양식 받기 (63×10칸)
        </a>
        <a className="view-toggle help-dl-btn" href="/시험문항-안내서.pdf" download>
          ⬇ 안내서 PDF
        </a>
      </div>
      <p className="help-note">
        ⭐ <b>CRITICAL 7개부터</b> 권장해요 — 되돌릴 수 없는 위험 의도(부모 전송·출결·삭제)라
        안전 게이트가 이 7개에 <b>각 30문항</b>을 요구하거든요. 이 양식의 <b>'혼동 주의'</b>{' '}
        칸엔 헷갈리는 이웃 업무가 적혀 있어요 — 그것과 <b>구별되는</b> 질문이 좋은 문항이에요.
        <br />
        💻 엑셀은 더블클릭으로 열려요 · 구글 시트는 파일 → 가져오기 → 업로드.
        <br />
        ⚠️ 올릴 땐 <b>CSV로 저장</b>하세요 — 엑셀 형식(.xlsx)은 업로드가 안 돼요. 엑셀:
        파일 → 다른 이름으로 저장 → <b>CSV UTF-8(쉼표로 분리)</b> 권장 (일반 "CSV(쉼표로
        분리)"도 자동 인식돼요) · 구글 시트: 파일 → 다운로드 → 쉼표로 구분된 값.
      </p>

      <h3>② 질문 쓰기 — ✍️ 한 칸만 쓰면 돼요</h3>
      <p>
        의도마다 줄이 미리 그려져 있어요. <b>'시험 질문' 칸에만</b> 그 의도로 알아들어야 할
        말을 <b>평소 쓰는 그대로</b> 쓰세요 (의도 id·뜻 칸은 🔒 그대로 두기). 다 채울 필요
        없어요 — 되는 만큼만.
      </p>
      <p className="help-note">
        💡 실제 습관을 반영하세요: AI에게 시킬 땐 뜻을 <b>또렷이</b> 쓰는 편이고("~만들어줘",
        "그려줘"), 바쁘거나 이어서 말할 땐 <b>짧고 애매</b>해져요("아까 그거", "이거 좀").
        시험지엔 <b>둘 다 골고루</b> — 또렷한 문항만 있으면 점수가 부풀려지고, 애매한
        문항만 있으면 실제 사용 모습을 못 재요.
      </p>
      <table className="help-table">
        <tbody>
          <tr>
            <td>🟢 또렷한 요청형</td>
            <td>"물놀이 안전 프로젝트 수업 만들어줘" (활동계획안 쓰기) · "거북이 그려줘"
              (그림 만들기) — AI에게 시킬 때 실제로 이렇게 써요</td>
          </tr>
          <tr>
            <td>🟢 짧고 애매한 말</td>
            <td>"다온이 할머니가 데려가셔서 조퇴야" (출결 기록) — 뜻을 안 밝혀도 알아들어야
              하는 어려운 문제. 이런 것도 꼭 섞어주세요</td>
          </tr>
          <tr>
            <td>🟢 이웃과 구별</td>
            <td>"이건 서준이네만 따로 알려야 할 것 같은데" (개별 학부모 메시지) — 헷갈리는
              이웃(학급 알림장)과 확실히 갈려요</td>
          </tr>
          <tr>
            <td>🔴 정답이 갈림</td>
            <td>"거북이 만들어줘"를 '그림 만들기' 정답으로 — 그림인지 만들기 활동 준비인지
              사람도 확신 못 하면 X. "거북이 그림 그려줘"처럼 또렷하게 고쳐 쓰세요</td>
          </tr>
          <tr>
            <td>🔴 공부용과 중복</td>
            <td>강화하기·즉석 문답에서 봤던 문장 그대로 — 겹치면 자동 거부돼요</td>
          </tr>
        </tbody>
      </table>
      <p className="help-note">
        ⚠️ 위 예시들도 <b>그대로 베끼진 마세요</b> — 안내용 예문이라 대부분 이미 공부용에
        있어요. 스타일만 참고하고 <b>새 문장</b>을 써주세요.
      </p>

      <h3>③ 두 분이 O/X 체크</h3>
      <p className="help-note">
        "이 질문이 이 의도의 시험 문제로 적절한가?"를 <b>서로 상의 없이 각자</b> O/X로
        판정하세요. <b>둘 다 O</b>인 질문만 올라가고, 일치도(kappa)는 자동 계산돼요. 전부
        똑같이 매기면 일치도를 계산할 수 없어 등록이 안 돼요 — 따로 검수하면 자연히 몇
        개는 갈리니 걱정 마세요.
      </p>

      <h3>④ 올리기 — 검증 → 등록 확정</h3>
      <ExamUpload />

      <h3>꼭 지킬 규칙 (어기면 자동 거부)</h3>
      <ul>
        <li><b>의도는 절대 바꾸지 않기</b> — 63개 정답 카테고리는 고정</li>
        <li><b>사람이 쓴 진짜 질문</b> — AI가 지어낸 문장 금지 (점수가 무의미해져요)</li>
        <li><b>검수자는 서로 다른 두 사람</b> (같은 사람 두 번은 무효)</li>
        <li><b>공부용에 이미 있는 질문 금지</b> (겹치면 "암기 측정"이 됨)</li>
      </ul>

      <h3>몇 문항이면 되나요?</h3>
      <table className="help-table">
        <tbody>
          <tr><td>⭐ CRITICAL 7개</td><td>의도당 <b>30문항</b> — 안전 게이트가 판정을 시작하는 최소치</td></tr>
          <tr><td>한 노드 측정</td><td>그 의도에 <b>1문항 이상</b> → 어둠에서 벗어남</td></tr>
          <tr><td>점수 안정</td><td>의도당 <b>5~10문항</b> (1문항이면 0/100%로 튐)</td></tr>
          <tr><td>전 노드 측정</td><td>63개 전부 (<b>권장 ~500문항</b>)</td></tr>
          <tr><td>혼동선 확정</td><td>같은 혼동 <b>3번 이상</b> → 실선 깜빡임</td></tr>
        </tbody>
      </table>
      <p className="help-note">
        문항은 <b>재는 도구</b>예요 — 문항이 늘면 <b>측정 범위</b>가 넓어져요. 점수(%)는
        공부(강화하기·즉석 문답)를 시킨 뒤 <b>재시험</b>에서만 올라요. 최종 목표는 전체 80%.
      </p>

      <h3>올린 다음은? (운영자)</h3>
      <ol>
        <li>진척 확인: <code>ktib_coverage.py</code> — 의도별 등록 수·30까지 남은 갭</li>
        <li>시험지 확정: <code>run_ktib_build.py --commit</code></li>
        <li>채점: <code>run_arena.py --commit</code> ← 여기서 노드가 밝아져요</li>
      </ol>
    </div>
  )
}

function StudyGuide() {
  const brain = useBrainStore((s) => s.brain)
  // 의도별 공부 문항 수 = 노드 evidence_total (실시간, brain API에서). 많은 순 정렬.
  const rows = useMemo(() => {
    if (!brain) return []
    return brain.nodes
      .map((n) => ({ intent: n.intent_id, total: n.evidence_total, gold: n.gold_count }))
      .sort((a, b) => b.total - a.total)
  }, [brain])
  const sum = rows.reduce((s, r) => s + r.total, 0)

  return (
    <div className="help-doc">
      <h3>공부 문항이 뭐예요?</h3>
      <p>
        뇌에게 "이런 말 = 이런 뜻"을 알려주는 <strong>연습 데이터</strong>예요. 한 건 ={' '}
        <b>문장 + 상황 + 정답</b>. 시험지(고정 문제집)와 달리 의도마다{' '}
        <strong>수십~수백 개씩 계속 쌓이는 풀</strong>이고, 시험 문제와는 <b>절대 겹치지
        않게</b> 관리돼요 (겹치면 암기 측정이 되니까).
      </p>

      <h3>어디서 늘어나요? — 3가지 길 + 안 늘어나는 1가지</h3>
      <table className="help-table">
        <tbody>
          <tr>
            <td>📚 시나리오 공장</td>
            <td>운영자가 생성 배치를 돌리면 <b>대량 자동 추가</b> — "컴퓨터 생성" 등급(낮게
              취급)</td>
          </tr>
          <tr>
            <td>🚀 강화하기</td>
            <td>선생님이 문제를 풀면 그 답이 새 문항 — <b>⭐사람 확인 등급</b>(귀함)</td>
          </tr>
          <tr>
            <td>💬 즉석 문답</td>
            <td>내가 입력한 문장 + 내 판정이 그대로 문항 — 뇌가 틀린 걸 바로잡은{' '}
              <b>교정이 제일 귀한 신호</b></td>
          </tr>
          <tr>
            <td>📝 시험(채점)</td>
            <td><b>늘지 않아요</b> — 시험은 재기만 하고, 공부 문항을 만들지 않아요</td>
          </tr>
        </tbody>
      </table>
      <p className="help-note">
        그래서 강화하기·즉석 문답을 제출하면 그 점의 크기가 <b>즉시</b> 커져요 — 빛(점수)은
        다음 시험에서만 바뀌고요.
      </p>

      <h3>"그중 GOLD"는 뭐예요?</h3>
      <p>
        문항엔 등급이 있어요: 컴퓨터 생성 &lt; 행동 신호 &lt; <b>⭐내 답(사람 확인)</b> &lt;{' '}
        <b>GOLD(2인 검증)</b> &lt; 전문가. GOLD는 <b>두 사람이 따로 검토해 일치</b>해야만
        붙어요 — 아래 표의 GOLD가 0이어도 고장이 아니라 <b>아직 검수 전</b>이라는 뜻이에요.
      </p>

      <h3>지금 쌓인 양 보기</h3>
      <div className="help-download">
        <a className="view-toggle help-dl-btn" href="/study_pool_snapshot.csv" download>
          ⬇ 현재 공부 문항 전체 내려받기 (CSV · Excel)
        </a>
      </div>
      <p className="help-note">
        지금 풀은 대부분 <strong>시나리오 공장이 자동 생성한 예시</strong>라 "이거 좀 해줄
        수 있어?" 같은 뼈대 문장이 많아요. 선생님들이 강화하기·즉석 문답으로 가르칠수록
        진짜 현장 표현으로 채워집니다.
      </p>

      <h3>의도별 공부 문항 수 {brain && <span className="help-live">(실시간 · 합계 {sum.toLocaleString('ko-KR')})</span>}</h3>
      {rows.length === 0 ? (
        <p className="help-note">
          뇌 데이터를 불러오지 못했어요(백엔드 미연결). 연결되면 여기서 63개 의도별 개수가
          많은 순으로 표시돼요. 전체 데이터는 위 CSV로 받을 수 있어요.
        </p>
      ) : (
        <div className="help-scroll">
          <table className="help-table help-count-table">
            <thead>
              <tr><th>의도</th><th>공부 문항</th><th>그중 GOLD</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.intent}>
                  <td>{labelOf(r.intent)}</td>
                  <td>{r.total.toLocaleString('ko-KR')}</td>
                  <td>{r.gold}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export function HelpOverlay({
  onClose,
  initialTab = 'service',
}: {
  onClose: () => void
  /** 진입 탭 — 시험지 모달의 "자세한 안내"가 'exam'으로 바로 열 때 사용 */
  initialTab?: Tab
}) {
  const [tab, setTab] = useState<Tab>(initialTab)
  return (
    <div className="gym-backdrop" role="dialog" aria-label="도움말">
      <div className="gym-modal help-modal">
        <div className="help-head">
          <strong className="help-title">도움말</strong>
          <div className="help-tabs">
            <button
              type="button"
              className={`view-toggle help-tab${tab === 'service' ? ' help-tab-active' : ''}`}
              aria-pressed={tab === 'service'}
              onClick={() => setTab('service')}
            >
              서비스 설명서
            </button>
            <button
              type="button"
              className={`view-toggle help-tab${tab === 'manual' ? ' help-tab-active' : ''}`}
              aria-pressed={tab === 'manual'}
              onClick={() => setTab('manual')}
            >
              사용설명서
            </button>
            <button
              type="button"
              className={`view-toggle help-tab${tab === 'exam' ? ' help-tab-active' : ''}`}
              aria-pressed={tab === 'exam'}
              onClick={() => setTab('exam')}
            >
              시험 문항 만들기
            </button>
            <button
              type="button"
              className={`view-toggle help-tab${tab === 'study' ? ' help-tab-active' : ''}`}
              aria-pressed={tab === 'study'}
              onClick={() => setTab('study')}
            >
              공부 문항 보기
            </button>
          </div>
          <button type="button" className="gym-close" onClick={onClose} aria-label="닫기">
            ✕
          </button>
        </div>
        <div className="help-body">
          {tab === 'service' && <ServiceGuide />}
          {tab === 'manual' && <ManualGuide />}
          {tab === 'exam' && <ExamGuide />}
          {tab === 'study' && <StudyGuide />}
        </div>
      </div>
    </div>
  )
}
