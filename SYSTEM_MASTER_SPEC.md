# 🚀 AI Agent Orchestration System: Master Specification v0.2

본 문서는 프로젝트의 모든 안내서, 아키텍처, 로드맵을 통합한 단일 소스(Single Source of Truth)입니다.

---

## 1. 프로젝트 개요 & 철학
- **목표**: 사용자의 의도를 파악하고 최적의 모델과 에이전트를 조합하여 목표를 완수하는 자율 오케스트레이션 시스템.
- **핵심 원칙**:
    - **Intent First**: 텍스트 그대로가 아닌 실제 의도를 분류하여 워크플로우 결정.
    - **Right Model, Right Job**: 작업 복잡도에 따라 모델(Opus, Sonnet, Haiku, GPT-4o 등)을 지능적으로 배정.
    - **Ralph Loop**: 완료 조건을 만족할 때까지 검증과 수정을 반복.

---

## 2. 시스템 아키텍처

### 2.1 워크플로우 엔진 (LangGraph)
- **Phase 0: Intent Gate**: 의도 분류 (`IntentRouter`) 및 워크플로우 분기.
- **Phase 1: Planner**: 전체 임무를 원자적 태스크(`TaskItem`)로 분해.
- **Phase 2: Executor**: 모델 라우터의 결정에 따라 개별 에이전트 실행.
- **Phase 3: Reviewer**: 결과 품질 검증 및 재계획/수정 결정.
- **Phase 4: Finalizer**: 최종 응답 합성.

### 2.2 핵심 컴포넌트
- **Intent Router**: `claude-haiku-4-5` 기반 고속 의도 분류.
- **Model Router**: `OrchestrationMode`(Economy/Balanced/Powerful)와 복잡도 매트릭스 기반 모델 선택.
- **CostGuard**: 세션당 예산($) 및 토큰 상한 관리.
- **Checkpointer**: `SqliteSaver`를 통한 세션 저장 및 재개.

---

## 3. 기능 명세 및 로드맵

### 현재 구현 상태 (v0.2)
- [x] 모델 라우팅 고도화 (복잡도/카테고리 매트릭스)
- [x] 비용 가드레일 (`CostGuard`) 및 상태 반영
- [x] 체크포인터를 이용한 세션 재개 흐름
- [x] CLI 인터랙티브 승인 프로세스 (`Y/n/change`)

### 향후 로드맵
- **PHASE 2**: 에이전트 클래스 분리 (`researcher`, `coder`, `writer`, `analyst`)
- **PHASE 3**: Dynamic Tool Discovery (벡터 검색 기반 도구 할당)
- **PHASE 5**: HITL (Human-In-The-Loop) 중단점 강화
- **PHASE 6**: LangFuse 관찰 가능성(Observability) 통합
- **PHASE 8**: 에피소딕 메모리 (벡터 DB 기반 과거 경험 회상)

---

## 4. 테스트 가이드

### 테스트 루틴
1. **단위 테스트**: `.venv/bin/python3 -m pytest tests/ -v` (Mock 기반)
2. **수동 검증**: `.venv/bin/python3 test_manual.py` (실제 LLM 호출)
3. **E2E 워크플로우**: `.venv/bin/python3 test_manual.py --workflow`

---

## 5. 개발 컨벤션
- **언어/프레임워크**: Python 3.11+, LangGraph, Pydantic v2.
- **함수**: 모든 비동기 로직은 `async/await` 준수.
- **구조**: 단일 모듈은 200줄 이내 유지 권장.

---

## 6. (중요) 오케스트레이터 인터뷰 (USER 답변 필요)
1. **에이전트 확장**: 에이전트 추가 시 코드 수정 방식 vs YAML 설정 기반 동적 생성 중 선호하는 방식은?
2. **병렬 실행**: 의존성 없는 태스크 동시 실행 시 로그 출력 방식(프로그레스 바 vs 실시간 텍스트 나열) 선호도는?
3. **예산 소진 시**: 예산 도달 시 즉시 중단 vs 가장 저렴한 모델로 강제 전환하여 답변 시도 중 선택은?
4. **메모리 저장**: 사용자 개인화(코딩 스타일 등) 정보를 어디까지 영구 저장할까요?
5. **재시도 정책**: 리뷰 실패 시 최대 몇 번까지 루프를 허용할까요? (현재 5회)

---

## 7. CLI 와이어프레임
```text
+------------------------------------------------------------+
|  MY AGENT SYSTEM v0.2                                      |
+------------------------------------------------------------+
|  You > FastAPI 기반 쇼핑몰 백엔드 구조 잡아줘              |
+------------------------------------------------------------+
|  [Decision] Intent: implement | Complexity: HIGH | Mode: B |
|  Proceed? [Y/n/change] > y                                 |
+------------------------------------------------------------+
|  Thinking... [intent_gate -> planner]                      |
|  Plan: 1.구축 설계 2.코드 생성 3.검증                      |
|  Running Task 1... (Cost: $0.002)                          |
+------------------------------------------------------------+
|  Final Answer: 프로젝트 구조 파일 생성을 완료했습니다...   |
+------------------------------------------------------------+
```
