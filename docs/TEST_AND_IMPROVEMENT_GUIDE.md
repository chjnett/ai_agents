# TEST_AND_IMPROVEMENT_GUIDE

목표는 "기능 추가 -> 즉시 검증 -> 안전하게 개선" 사이클을 짧게 반복하는 것입니다.

## 0. 시작 전 체크

```bash
cd /Users/cheonhyeonjun/workspace/06ai_aiagents/my-agent-system
.venv/bin/python3 -m pytest -q
```

- 기준선이 깨져 있으면 새 기능 작업 전에 먼저 복구합니다.
- 현재처럼 Anthropic 크레딧 이슈가 있으면 `.env`에서 `OPENAI_API_KEY` 중심으로 테스트합니다.

## 1. 작업 단위를 작게 쪼개기

한 번에 큰 변경 대신 아래 단위로 나눕니다.

- 타입/상수 추가
- 라우팅 로직 연결
- 상태(`AgentState`) 필드 반영
- 테스트 추가
- 회귀 테스트

각 단계마다 테스트를 돌려 실패 지점을 좁힙니다.

## 2. 권장 테스트 루프

### 루프 A: 코드 변경 직후

```bash
.venv/bin/python3 -m pytest tests/test_core.py -q
```

### 루프 B: Cost/Guard 관련 변경 시

```bash
.venv/bin/python3 -m pytest tests/test_cost_guard.py -q
```

### 루프 C: 병합 전 전체 회귀

```bash
.venv/bin/python3 -m pytest -v
```

## 3. 실패했을 때 처리 순서

1. 실패한 테스트만 재실행

```bash
.venv/bin/python3 -m pytest --lf -v
```

2. 첫 실패에서 멈춰 원인 집중

```bash
.venv/bin/python3 -m pytest -x -v
```

3. 최근 변경 파일만 점검

- `src/core/model_router.py`
- `src/core/workflow_engine.py`
- `src/core/cost_guard.py`
- `tests/test_core.py`
- `tests/test_cost_guard.py`

4. 상태 필드 누락 여부 확인

- `make_initial_state()`와 `AgentState`가 같은 필드 세트를 가지는지 확인

## 4. 수동 테스트 시나리오

```bash
.venv/bin/python3 main.py
```

권장 입력 시나리오:

- `rag가 뭐야?` -> research/direct 흐름 확인
- `FastAPI 인증 API 구현해줘` -> plan_execute 흐름 확인
- `500 에러 고쳐줘` -> fix 의도 분류 확인
- 모호한 입력(`dd`) -> ask_clarification 가드레일 확인

확인 포인트:

- `workflow_trace`가 기대한 노드 순서인지
- `total_cost_usd`, `total_tokens`, `cost_by_model`이 증가/유지되는지
- 중단(`Ctrl+C`) 시 스택트레이스 없이 종료되는지

## 5. TODO 기반 실행 순서 (현재 권장)

1. PHASE 2: Agent 클래스 분리
2. PHASE 3: Dynamic Tool Discovery
3. PHASE 5+: HITL, Observability, 병렬 실행

각 단계는 "구현 + 테스트 추가 + 회귀 통과"를 완료 기준으로 처리합니다.

## 6. 완료 체크 템플릿

아래 항목이 모두 만족되면 해당 작업을 완료로 체크합니다.

- 기능 테스트 통과
- 회귀 테스트 통과
- TODO 반영
- 문서(가이드/아키텍처) 갱신

