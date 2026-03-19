# TODO — My Agent System

> 기준일: **2026-03-19**
> 
> 목표: v0.2 핵심 기능을 안전하게 구현하고, 매 단계마다 바로 검증 가능하게 유지

---

## 현재 스냅샷

- 코어 MVP 동작 중 (`intent_router`, `model_router`, `workflow_engine`)
- 단위 테스트 상태: **20 passed / 0 failed**
- 다음 구현 시작점: **PHASE 1 (Blocker)**

---

## 이번 스프린트 (우선순위 순)

## 1) PHASE 1-1 CostGuard 구현

- [x] `src/core/cost_guard.py` 생성
- [x] `CostGuard.PRICE_PER_1K` 모델 단가 테이블 정의
- [x] `record(model, input_tokens, output_tokens)` 구현
- [x] `is_over_limit()` 구현
- [x] `summary()` 구현
- [x] `tests/test_cost_guard.py` 추가

완료 기준 (DoD):
- [x] 비용/토큰 누적 계산이 정확히 동작
- [x] 상한선 초과 시 `True` 반환
- [x] 테스트 통과

검증 명령:
```bash
.venv/bin/python3 -m pytest tests/test_cost_guard.py -v
```

## 2) PHASE 1-3 AgentState v2 반영

- [x] `src/core/workflow_engine.py`의 `AgentState`에 v2 필드 추가
- [x] `completed_tasks`, `failed_tasks`, `workflow_trace`를 `Annotated[..., operator.add]`로 변경
- [x] `should_continue_loop()`에 비용/토큰 상한 조건 추가
- [x] 초기 상태 생성 시 신규 필드 기본값 반영 (`make_initial_state`)
- [x] 기존 테스트 호환성 유지

완료 기준 (DoD):
- [x] 기존 라우팅/루프 테스트 모두 통과
- [x] 신규 비용 필드가 상태에 안전하게 포함됨

검증 명령:
```bash
.venv/bin/python3 -m pytest tests/test_core.py -v
```

## 3) PHASE 1-2 Checkpointer 연결

- [x] `build_orchestration_graph(checkpointer=None)` 형태로 수정
- [x] `main.py`에 `SqliteSaver` 연결
- [x] `thread_id=session_id` config 적용
- [x] 중단 후 재개(`Command(resume=...)`) 흐름 추가

완료 기준 (DoD):
- [x] 동일 `session_id`로 워크플로우 재개 가능
- [x] 기본 실행(체크포인터 없음/있음) 둘 다 정상 동작

검증 명령:
```bash
.venv/bin/python3 -m pytest tests/test_core.py -v
.venv/bin/python3 main.py
```

---

## 다음 스프린트

## 4) PHASE 4 Model Routing 고도화

- [ ] `ComplexityLevel` Enum 추가
- [ ] `MODEL_MATRIX[(category, complexity)]` 추가
- [ ] `estimate_complexity()` 규칙 기반 구현
- [ ] `get_model_v2(category, task_description)` 적용
- [ ] `tests/test_core.py`에 matrix 테스트 추가

## 5) PHASE 2 Agent 클래스 분리

- [ ] `src/agents/base_agent.py` 추상 클래스
- [ ] Worker 4종(`researcher/coder/writer/analyst`) 구현
- [ ] `executor_node()` 인라인 호출 제거
- [ ] `AGENT_REGISTRY` 적용

## 6) PHASE 3 Dynamic Tool Discovery

- [ ] `src/tools/registry.py` 구현
- [ ] 도구 1차 세트(`web_search`, `code_executor`, `file_read`, `file_write`) 구현
- [ ] `executor_node()`에 `find_relevant(task)` 연동

---

## 테스트 루틴 (개발 중 반복)

아래 3단계를 기본 루틴으로 사용:

1. 빠른 회귀 확인
```bash
.venv/bin/python3 -m pytest -v
```

2. 수동 시나리오 확인 (실제 LLM)
```bash
.venv/bin/python3 test_manual.py
```

3. 전체 워크플로우 E2E 확인
```bash
.venv/bin/python3 test_manual.py --workflow
```

실패 시 자주 쓰는 옵션:
```bash
# 실패한 테스트만 재실행
.venv/bin/python3 -m pytest --lf

# 첫 실패에서 중단
.venv/bin/python3 -m pytest -x
```

---

## 백로그 (후순위)

- [ ] PHASE 5: HITL (`interrupt`, 승인/수정/취소)
- [ ] PHASE 6: LangFuse observability
- [ ] PHASE 7: 병렬 실행 (`Send`, merge)
- [ ] PHASE 8: 메모리 (Redis + ChromaDB)
- [ ] PHASE 9: FastAPI + SSE
- [ ] PHASE 10: 테스트 스위트 확장 (`test_agents`, `test_tools`, `test_memory`, `test_e2e`)
