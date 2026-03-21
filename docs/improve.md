### 목표: AI 오케스트레이션 모델 선택 로직 확장 (모드 도입 및 인터랙티브 UI)

현재 `MODEL_MATRIX`를 기반으로 태스크별 모델을 할당하는 로직이 있습니다. 여기에 두 가지 핵심 기능을 추가해 주세요.

#### 1. '오케스트레이션 모드' 기능 추가
사용자가 `--mode` 플래그를 통해 전체적인 비용/성능 밸런스를 조절할 수 있어야 합니다.
- **Enum 추가**: `OrchestrationMode { ECONOMY, BALANCED, POWERFUL }`
- **로직 반영**: 
  - `ECONOMY`: `ComplexityLevel`을 한 단계 낮추어 모델 할당 (LOW 이하는 LOW 유지)
  - `BALANCED`: 현재 `MODEL_MATRIX` 정의대로 할당 (기본값)
  - `POWERFUL`: `ComplexityLevel`을 한 단계 높여서 모델 할당 (HIGH 이상은 HIGH 유지)
- **함수 작성**: `TaskCategory`, `ComplexityLevel`, `OrchestrationMode`를 인자로 받아 최종 모델명을 반환하는 `get_orchestrated_model()` 함수를 작성하세요.

#### 2. CLI 인터랙티브 확인(Confirmation) 단계 추가
모델이 최종 결정된 후, 실제 API를 호출하기 전에 사용자에게 확인을 받는 과정을 추가해 주세요.
- **출력 정보**: 선택된 카테고리, 난이도, 모드, 그리고 '할당된 모델명'을 리치하게 출력합니다.
- **사용자 입력 대기**: `[Y/n/change]` 입력을 받습니다.
  - `Y` (또는 Enter): 그대로 진행
  - `n`: 실행 취소 및 종료
  - `change`: 현재 카테고리 내에서 선택 가능한 다른 모델 리스트(동일 카테고리의 LOW, MEDIUM, HIGH 모델들)를 번호로 보여주고 사용자가 직접 선택하게 함.

#### 3. 기존 코드 참조 (Context)
아래의 기존 매트릭스 구조를 유지하면서 위 로직을 통합해 주세요.
(여기에 질문에 올리신 MODEL_MATRIX 코드를 붙여넣으세요)
