#!/usr/bin/env python3
"""Virtual-first scenario runner for E1 Pure MAPE-K validation.

This script does not execute hardware commands. It only:
- builds baseline and fault contexts from given sensor values,
- runs candidate generation and DT scoring,
- reports the best adaptation decision.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List

from experiment_runner_refactored import E1CandidateSelectionRunner


SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "S1_TEMP_SPIKE_NO_MOTION",
        "intent": "Temperature dominant stress, no occupancy stress",
        "baseline": {"temperature": 25.0, "lux": 280.0, "pir": 0},
        "fault": {"temperature": 31.5, "lux": 260.0, "pir": 0},
        "physical_injection": "Increase room heat near board; keep lights on; no motion near PIR.",
    },
    {
        "id": "S2_TEMP_SPIKE_WITH_MOTION",
        "intent": "Temperature + occupancy stress",
        "baseline": {"temperature": 25.0, "lux": 280.0, "pir": 0},
        "fault": {"temperature": 31.0, "lux": 240.0, "pir": 1},
        "physical_injection": "Increase heat and introduce movement near PIR while keeping moderate light.",
    },
    {
        "id": "S3_LOW_LUX_WITH_MOTION",
        "intent": "Lux and occupancy dominant stress",
        "baseline": {"temperature": 25.0, "lux": 280.0, "pir": 0},
        "fault": {"temperature": 26.0, "lux": 70.0, "pir": 1},
        "physical_injection": "Switch lights off / darken room and create motion near PIR.",
    },
    {
        "id": "S4_LOW_LUX_NO_MOTION",
        "intent": "Lux-only stress",
        "baseline": {"temperature": 25.0, "lux": 300.0, "pir": 0},
        "fault": {"temperature": 25.5, "lux": 60.0, "pir": 0},
        "physical_injection": "Turn lights off or block light; keep no movement near PIR.",
    },
    {
        "id": "S5_OCCUPANCY_ONLY",
        "intent": "PIR-only stress",
        "baseline": {"temperature": 25.0, "lux": 260.0, "pir": 0},
        "fault": {"temperature": 25.5, "lux": 250.0, "pir": 1},
        "physical_injection": "Keep temp/light stable and only add movement near PIR.",
    },
    {
        "id": "S6_ALL_HIGH_STRESS",
        "intent": "Combined high stress: hot + dark + motion",
        "baseline": {"temperature": 25.0, "lux": 290.0, "pir": 0},
        "fault": {"temperature": 32.0, "lux": 40.0, "pir": 1},
        "physical_injection": "Heat up environment, reduce light strongly, and keep motion active.",
    },
    {
        "id": "S7_RECOVERY_CHECK",
        "intent": "Mild residual stress to test stable control",
        "baseline": {"temperature": 25.5, "lux": 260.0, "pir": 0},
        "fault": {"temperature": 28.0, "lux": 180.0, "pir": 0},
        "physical_injection": "Apply only mild heat and light reduction; no motion.",
    },
    {
        "id": "S8_NIGHT_OCCUPIED",
        "intent": "Night-like occupancy condition",
        "baseline": {"temperature": 24.5, "lux": 180.0, "pir": 0},
        "fault": {"temperature": 27.0, "lux": 25.0, "pir": 1},
        "physical_injection": "Dark room and active movement with slight temperature increase.",
    },
]


def _build_fault_state(
    runner: E1CandidateSelectionRunner,
    baseline_values: Dict[str, float],
    fault_values: Dict[str, float],
) -> Dict[str, float]:
    baseline_ctx = runner._build_context(baseline_values)
    runner._last_baseline_context = baseline_ctx

    fault_ctx = runner._build_context(fault_values, baseline_ctx)
    return {
        "temperature": fault_ctx["temperature"],
        "lux": fault_ctx["lux"],
        "pir": fault_ctx["pir"],
        "risk_score": fault_ctx["risk_score"],
        "temp_stress": fault_ctx["temp_stress"],
        "lux_stress": fault_ctx["lux_stress"],
        "pir_stress": fault_ctx["pir_stress"],
    }


def evaluate_scenario(scenario: Dict[str, Any]) -> Dict[str, Any]:
    runner = E1CandidateSelectionRunner(trials=1)
    fault_state = _build_fault_state(runner, scenario["baseline"], scenario["fault"])

    candidates = runner._generate_candidates(fault_state)
    ranked: List[Dict[str, Any]] = []

    for candidate in candidates:
        result = runner._simulate_candidate_effect(candidate, fault_state)
        if not result:
            continue

        ranked.append(
            {
                "id": candidate["id"],
                "name": candidate["name"],
                "fan_speed": round(float(candidate.get("fan_speed", 0.0)), 3),
                "led_level": round(float(candidate.get("led_level", 0.0)), 3),
                "buzzer_enabled": bool(candidate.get("buzzer_enabled", False)),
                "sampling_interval_seconds": round(float(candidate.get("sampling_interval_seconds", 10.0)), 3),
                "impact_score": round(float(result.get("impact_score", 0.0)), 6),
                "predicted_risk_after": round(float(result.get("predicted_risk_after", 0.0)), 6),
                "reasoning": result.get("reasoning", ""),
            }
        )

    ranked.sort(key=lambda item: item["impact_score"], reverse=True)
    best = ranked[0] if ranked else None

    return {
        "scenario_id": scenario["id"],
        "intent": scenario["intent"],
        "physical_injection": scenario["physical_injection"],
        "baseline": scenario["baseline"],
        "fault": scenario["fault"],
        "computed_fault_state": {
            "risk_score": round(float(fault_state["risk_score"]), 6),
            "temp_stress": round(float(fault_state["temp_stress"]), 6),
            "lux_stress": round(float(fault_state["lux_stress"]), 6),
            "pir_stress": round(float(fault_state["pir_stress"]), 6),
        },
        "best_decision": best,
        "ranked_candidates": ranked,
    }


def _print_human(results: List[Dict[str, Any]]) -> None:
    for result in results:
        print("=" * 90)
        print(f"Scenario: {result['scenario_id']}")
        print(f"Intent:   {result['intent']}")
        print(f"Inject:   {result['physical_injection']}")
        print(f"Fault risk score: {result['computed_fault_state']['risk_score']:.3f}")

        best = result.get("best_decision")
        if best:
            print(
                "Best decision: "
                f"{best['id']} {best['name']} | score={best['impact_score']:.4f} "
                f"| pred_risk={best['predicted_risk_after']:.4f} "
                f"| fan={best['fan_speed']:.2f} led={best['led_level']:.2f} "
                f"buzzer={int(best['buzzer_enabled'])} sample={best['sampling_interval_seconds']:.2f}s"
            )
        else:
            print("Best decision: none")

        print("Candidate ranking:")
        for idx, row in enumerate(result["ranked_candidates"], start=1):
            print(
                f"  {idx}. {row['id']} {row['name']} | score={row['impact_score']:.4f} "
                f"| pred_risk={row['predicted_risk_after']:.4f} "
                f"| fan={row['fan_speed']:.2f} led={row['led_level']:.2f} "
                f"buzzer={int(row['buzzer_enabled'])} sample={row['sampling_interval_seconds']:.2f}s"
            )
        print("")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run virtual E1 MAPE-K scenarios without hardware execution")
    parser.add_argument(
        "--scenario",
        default="all",
        help="Scenario id to run (default: all)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output",
    )
    args = parser.parse_args()

    selected = SCENARIOS
    if args.scenario != "all":
        selected = [item for item in SCENARIOS if item["id"] == args.scenario]
        if not selected:
            known = ", ".join(item["id"] for item in SCENARIOS)
            raise SystemExit(f"Unknown scenario '{args.scenario}'. Known: {known}")

    results = [evaluate_scenario(item) for item in selected]

    if args.json:
        print(json.dumps(results, indent=2))
        return

    _print_human(results)


if __name__ == "__main__":
    main()
