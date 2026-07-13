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

      <h3>그냥 챗봇(범용 AI)을 붙이면 안 되나요?</h3>
      <p>
        현장의 말은 짧고 애매해요. <strong>"이거 좀 정리해줘"</strong> — 사진첩을 보며
        말하면 <b>사진 정리</b>, 자료함에서면 <b>자료함 정리</b>, 글을 쓰다 말하면{' '}
        <b>문장 다듬기</b>죠. 범용 챗봇은 이 구별을 못 해요. 킨더브레인은{' '}
        <strong>말 + 화면 맥락 + 직전 행동 + 말버릇</strong>을 묶어 속뜻을 알아내도록
        훈련되고, 그 실력을 시험으로 확인받아요.
      </p>
      <ul>
        <li>범용 챗봇 — 정확도를 <b>증명 못 함</b>("잘 되는 것 같아요") · 위험한 순간에도
          자신만만하게 실행 · 누구에게나 똑같이 답함</li>
        <li>킨더브레인 — <b>주 1회 전문가 시험</b>으로 채점(목표 80%) · 위험한 7가지는{' '}
          <b>오발률 2% 이하</b> 기준을 통과해야만 연결 · 확신 없으면 멈추고 되물음</li>
      </ul>

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
      <h3>화면 4부분</h3>
      <p>
        <b>왼쪽</b> 전체 점수·영역 목록 / <b>가운데</b> 3D 뇌 / <b>오른쪽</b> 도구 카드·점
        상세 / <b>하단 중앙</b> [2D 지도로 보기]
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

      <h3>뇌 가르치기 — 강화하기 ⭐</h3>
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

      <h3>내 답은 어디로 가나요?</h3>
      <p>
        답 1개 → "문장+상황+선택"으로 저장 → 등급: 컴퓨터 생성 &lt; 행동 신호 &lt;{' '}
        <b>⭐내 답(사람 확인)</b> &lt; GOLD(2인 검증) &lt; 전문가 → 크기·입자 즉시 반영 →
        다음 시험에서 실력 측정. 함정 문제 답은 따로 보관돼 통계를 흐리지 않아요.
      </p>

      <h3>자주 묻는 질문</h3>
      <ul className="help-faq">
        <li><b>뇌가 어두워요.</b> 정상! 빛=시험 성적뿐인데 아직 시험 전이에요.</li>
        <li><b>"—%"가 떠요.</b> "아직 안 재봤다"는 뜻. 0%가 아니에요.</li>
        <li><b>훈련해도 안 빛나요.</b> 훈련=커짐+고리, 시험=빛남. 다음 시험 후 반영!</li>
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
      <h3>시험 문항이란?</h3>
      <p>
        문항 하나 = <strong>문제(교사 발화)</strong> + <strong>정답(63개 의도 중 하나)</strong>.
        뇌가 문제만 보고 정답을 맞히면 득점이에요.
      </p>

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
        ⚠️ <b>되돌릴 수 없는 위험 의도 7개</b>(부모 전송·출결·삭제)부터 채우는 걸 권장해요 — 안전
        게이트가 이 7개에 각 30문항을 요구합니다. 양식의 <b>'혼동 주의'</b> 칸에 헷갈리는 이웃이
        적혀 있으니, 그것과 <b>구별되게</b> 질문을 쓰면 좋은 문항이 돼요.
      </p>
      <p className="help-note">
        엑셀은 파일을 더블클릭하면 열려요. 구글 시트는 시트 → 파일 → 가져오기 → 업로드.
      </p>

      <h3>양식 채우는 법 — 3칸만 손대면 돼요</h3>
      <p>
        양식에는 <strong>63개 의도마다 10줄씩</strong> 미리 그려져 있어요(총 630칸). 다 채울
        필요 없어요 — 만들 수 있는 만큼만 채우면 됩니다.
      </p>
      <table className="help-table">
        <tbody>
          <tr><td>의도 id · 의도(뜻)</td><td>🔒 <b>그대로 두세요</b> (정답 카테고리 — 수정 금지)</td></tr>
          <tr><td>시험 질문</td><td>✍️ 그 의도에 맞는 <b>교사 말투 질문</b>을 씁니다</td></tr>
          <tr><td>검수자 A 판정</td><td>첫 번째 검수자: 질문이 맞으면 <b>O</b>, 아니면 <b>X</b></td></tr>
          <tr><td>검수자 B 판정</td><td>두 번째 검수자: 똑같이 <b>O / X</b></td></tr>
        </tbody>
      </table>
      <p className="help-note">
        👉 <b>일치도(kappa)를 직접 계산할 필요 없어요.</b> 두 분의 O/X만 보고 시스템이 자동으로
        점수를 매기고, <b>둘 다 O</b>인 질문만 시험지로 등록돼요. 검수자 이름은 올릴 때 입력합니다.
      </p>

      <ExamUpload />

      <h3>꼭 지킬 규칙 (어기면 자동 거부)</h3>
      <ul>
        <li><b>의도는 절대 바꾸지 않기</b> — 63개 정답 카테고리는 고정</li>
        <li><b>사람이 쓴 진짜 질문</b> — LLM이 지어낸 문장 금지</li>
        <li><b>검수자는 서로 다른 두 사람</b> (같은 사람 두 번은 무효)</li>
        <li><b>공부용에 이미 있는 질문 금지</b> (겹치면 "암기 측정"이 됨)</li>
      </ul>

      <h3>몇 문항을 만들어야 하나?</h3>
      <p className="help-note">
        문항은 <b>재는 도구</b>예요. 문항이 많다고 점수가 오르는 게 아니라, 더 많은 노드를
        잴 수 있게 돼요.
      </p>
      <table className="help-table">
        <tbody>
          <tr><td>한 노드 측정</td><td>그 의도에 <b>1문항 이상</b> → 어둠에서 벗어남</td></tr>
          <tr><td>점수 안정</td><td>의도당 <b>5~10문항</b> (1문항이면 0/100%로 튐)</td></tr>
          <tr><td>전 노드 측정</td><td>63개 전부 (최소 63, <b>권장 ~500문항</b>)</td></tr>
          <tr><td>혼동선 확정</td><td>같은 혼동 <b>3번 이상</b> → 실선 깜빡임</td></tr>
        </tbody>
      </table>

      <h3>언제·얼마나 하면 점수가 오르나?</h3>
      <p>
        <b>문항을 늘린다고 점수(%)가 오르지 않아요.</b> 점수는 뇌가 실제로 맞혀야 올라요.
      </p>
      <ul>
        <li>문항 ↑ → 더 많은 노드가 <b>측정됨</b>(어둠 → 밝음, 그 노드 실력만큼)</li>
        <li>점수 ↑ → <b>강화하기로 공부</b>시킨 뒤 → <b>주 1회 시험(재채점)</b> → 실력 오르면 상승</li>
        <li>최종 목표: 전체 정확도 <b>80%</b>(성장 5단계 "뇌 전체 공명")</li>
      </ul>

      <h3>실행 순서 (운영자)</h3>
      <ol>
        <li>시작 양식 받기 (위 버튼) → 전문가가 문항 채우기</li>
        <li>등록: <code>ingest_expert_episodes.py --file ... --commit</code></li>
        <li>시험지 확정: <code>run_ktib_build.py --commit</code></li>
        <li>채점: <code>run_arena.py --commit</code> ← 여기서 노드가 밝아짐</li>
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
      <h3>공부 문항이란?</h3>
      <p>
        뇌에게 "이런 말 = 이런 뜻"을 알려주는 <strong>연습 데이터</strong>예요. 시험지와 달리
        정해진 63개가 아니라, 의도마다 <strong>수십~수백 개씩 계속 쌓이는 풀</strong>이에요.
      </p>

      <div className="help-download">
        <a className="view-toggle help-dl-btn" href="/study_pool_snapshot.csv" download>
          ⬇ 현재 공부 문항 전체 내려받기 (CSV · Excel)
        </a>
      </div>
      <p className="help-note">
        지금 공부 풀은 대부분 <strong>시나리오 공장이 자동 생성한 예시</strong>라서 아직
        "이거 좀 해줄 수 있어?" 같은 뼈대 문장이 많아요. 선생님들이 강화하기로 가르칠수록
        진짜 표현이 채워집니다.
      </p>

      <h3>이 숫자는 공부·시험을 하면 자동으로 늘어나나요?</h3>
      <table className="help-table">
        <tbody>
          <tr><td>📚 시나리오 공장</td><td><b>자동으로 늘어남</b> — 운영자가 생성 배치를 돌리면 대량 추가</td></tr>
          <tr><td>📚 선생님 강화하기</td><td><b>자동으로 늘어남</b> — 선생님이 문제를 풀면 그 답이 새 공부 문항이 됨 ⭐</td></tr>
          <tr><td>📝 시험(Arena)</td><td><b>늘지 않음</b> — 시험은 재기만 함, 공부 문항을 만들지 않음</td></tr>
        </tbody>
      </table>
      <p>
        정리하면, <strong>"공부"를 하면(공장·강화하기) 문항 수가 자동으로 늘고, "시험"을 봐도
        공부 문항은 늘지 않아요.</strong> 강화하기 제출 → 그 점의 숫자가 즉시 커지는 게
        이 때문이에요.
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
