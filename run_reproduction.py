from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CODE = ROOT / "code"
STAGE7 = ROOT / "data" / "processed" / "stage7_mixed_frequency"
STAGE9 = ROOT / "data" / "processed" / "stage9_simplified"


STAGES: list[tuple[str, list[str]]] = [
    (
        "run_stage14_2state_rebuild.py",
        ["--stage7-dir", str(STAGE7), "--stage9-dir", str(STAGE9)],
    ),
    (
        "run_stage21_2state_overlay_redesign.py",
        ["--stage7-dir", str(STAGE7), "--stage9-dir", str(STAGE9)],
    ),
    (
        "run_stage24_walkforward_oos_overlay.py",
        ["--stage7-dir", str(STAGE7), "--stage9-dir", str(STAGE9)],
    ),
    ("run_stage25_oos_failure_diagnostics.py", []),
    (
        "run_stage26_refit_stability_tests.py",
        ["--stage7-dir", str(STAGE7), "--stage9-dir", str(STAGE9)],
    ),
    (
        "run_stage29_filtered_rebalance_overlay.py",
        ["--stage7-dir", str(STAGE7), "--stage9-dir", str(STAGE9)],
    ),
    (
        "run_stage30_realistic_benchmark_accounting.py",
        ["--stage7-dir", str(STAGE7), "--stage9-dir", str(STAGE9)],
    ),
    (
        "run_stage31_base_allocation_sensitivity.py",
        ["--stage7-dir", str(STAGE7), "--stage9-dir", str(STAGE9)],
    ),
    (
        "run_stage32_final_guardrail_robustness.py",
        ["--stage7-dir", str(STAGE7), "--stage9-dir", str(STAGE9)],
    ),
    (
        "run_stage34_no_ted_sensitivity.py",
        ["--stage7-dir", str(STAGE7)],
    ),
]


def validate_inputs() -> None:
    required = [
        STAGE7 / "mixed_frequency_observations.csv",
        STAGE9 / "economic_axis_scores.csv",
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        formatted = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(f"Required processed inputs are missing:\n{formatted}")


def main() -> None:
    validate_inputs()
    for script, arguments in STAGES:
        command = [sys.executable, str(CODE / script), *arguments]
        print(f"\n[RUN] {' '.join(command)}", flush=True)
        subprocess.run(command, cwd=ROOT, check=True)
    print("\nReproduction pipeline completed. See outputs/ for generated artifacts.")


if __name__ == "__main__":
    main()
