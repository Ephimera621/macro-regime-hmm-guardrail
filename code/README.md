# Code Map

이 폴더에는 최종 발표의 결론을 구성하는 연구 경로만 포함되어 있습니다.

## Core modules

- `stage9_simplified.py`: 경제축 구성과 생산형 모니터링 로직
- `stage12_hmm_comparison.py`: 공통 2/3-state HMM 및 성과평가 함수

## Selected experiments

- `run_stage14_2state_rebuild.py`: canonical 2-state HMM 재구축
- `run_stage21_2state_overlay_redesign.py`: 2-state posterior 기반 overlay
- `run_stage24_walkforward_oos_overlay.py`: walk-forward OOS 검증
- `run_stage25_oos_failure_diagnostics.py`: OOS 실패 원인 진단
- `run_stage26_refit_stability_tests.py`: 재학습 주기 안정성 비교
- `run_stage29_filtered_rebalance_overlay.py`: hysteresis 및 리밸런싱 빈도
- `run_stage30_realistic_benchmark_accounting.py`: drift-aware 벤치마크
- `run_stage31_base_allocation_sensitivity.py`: 기준 포트폴리오 민감도
- `run_stage32_final_guardrail_robustness.py`: 임계값 및 거래비용 검증
- `run_stage34_no_ted_sensitivity.py`: TEDRATE 제거 검증

Stage 33 DAG allocation stress test는 별도의 Stage 18~20 산출물에 의존하므로 재현 스크립트에서는 제외했습니다. 최종 비교 결과는 `results/tables/`와 연구 경로 문서에 포함되어 있습니다.

저장소 루트에서 다음 명령으로 선별된 실행 순서를 재현할 수 있습니다.

```bash
python run_reproduction.py
```
