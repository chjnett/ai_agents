# My Agent System

> oh-my-openagent 아키텍처를 학습해 Python + LangGraph로 구현한 멀티-에이전트 오케스트레이션 시스템

## 현재 상태

- 핵심 엔진(MVP) 구현 완료: `Intent Router`, `Model Router`, `Workflow Engine`, `Ralph Loop`
- 최신 단위 테스트 상태 (`2026-03-19`): **20 passed / 0 failed**
- 다음 우선순위: **PHASE 1 (CostGuard + Checkpointer + AgentState v2)**

## 빠른 시작

```bash
cd /Users/cheonhyeonjun/workspace/06ai_aiagents/my-agent-system

# 1) 의존성 설치
poetry install

# 2) 환경변수 설정
cp .env.example .env
# .env에 최소 1개 API 키 설정 (예: OPENAI_API_KEY 또는 ANTHROPIC_API_KEY)

# 3) 실행
poetry run python main.py

# 4) 옵션: 오케스트레이션 모드 설정 (기본값: balanced)
# - economy: 비용 절약형 (더 낮은 사양 모델 우선)
# - balanced: 균형 잡힌 모델 선택
# - powerful: 성능 중심 (고성능 모델 우선)
poetry run python main.py --mode economy

# 5) 데모 실행
poetry run python main.py --demo
```

## 주요 기능 (v0.2+)

### 1. 오케스트레이션 모드 (`--mode`)
시스템이 태스크의 복잡도를 분석한 후, 사용자가 선택한 모드에 따라 모델을 유동적으로 할당합니다.
- `ECONOMY`: 추정된 난이도보다 한 단계 낮은 성능의 모델을 사용하여 비용을 아낍니다.
- `BALANCED`: 최적의 성능/비용 가성비 모델을 선택합니다.
- `POWERFUL`: 비용보다는 성능과 정확도가 높은 모델을 우선적으로 할당합니다.

### 2. 인터랙티브 모델 확인 (Interactive Confirmation)
태스크 실행 전, 시스템이 판단한 의도(Intent)와 할당된 모델명을 사용자에게 보여주고 확인을 받습니다.
- `Y`: 승인 후 실행
- `n`: 중단
- `change`: 해당 카테고리 내의 다른 모델(LOW/MEDIUM/HIGH) 리스트를 보고 직접 모델 선택 가능

## 테스트

테스트는 아래 문서 하나만 보면 됩니다.

- [testing.md](./testing.md)

가장 자주 쓰는 명령:

```bash
# 전체 단위 테스트
.venv/bin/python3 -m pytest -v

# 수동(실제 LLM) 테스트
.venv/bin/python3 test_manual.py

# E2E 워크플로우 테스트
.venv/bin/python3 test_manual.py --workflow
```

## 아키텍처 요약

```text
사용자 요청
  -> Intent Gate
    -> research_only/direct: Executor
    -> plan_execute: Planner -> Executor -> Reviewer -> Loop Check
                                                 | continue -> Executor
                                                 | done     -> Finalizer
```

핵심 파일:

- `src/core/intent_router.py`: 의도 분류
- `src/core/model_router.py`: 카테고리 기반 모델 선택
- `src/core/workflow_engine.py`: LangGraph 오케스트레이션
- `main.py`: CLI 진입점

## 문서

- `docs/ARCHITECTURE.md`: v1 설계
- `docs/ARCHITECTURE_V2.md`: v2 고도화 설계
- `docs/CODE_DEEP_DIVE.md`: 코드 분석/개선 포인트
- `docs/TESTING_GUIDE.md`: 상세 테스트 가이드

## 로드맵

- [x] Intent Router
- [x] Model Router
- [x] LangGraph 기본 워크플로우
- [x] Ralph Loop
- [ ] PHASE 1: 안전장치 & 상태 영속성
- [ ] PHASE 2: 에이전트 클래스 분리
- [ ] PHASE 3: Dynamic Tool Discovery
- [ ] PHASE 4+: HITL, Observability, 병렬 실행, 메모리, API
