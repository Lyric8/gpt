"""Explicit conditional forecasts; none of these values is a runtime limit."""
from __future__ import annotations
import json

BASELINE = 475_300_000  # User's rounded baseline, not the older 443.9M.
TARGET = BASELINE // 5
SCENARIOS = {
    "conservative_near_boundary": [(1219, 48_000), (282, 16_000), (325, 48_000)],
    "target": [(1084, 32_000), (235, 12_000), (260, 32_000)],
    "stress_not_fivefold": [(1354, 64_000), (376, 24_000), (325, 64_000)],
}


def projection() -> dict:
    result = {}
    for name, groups in SCENARIOS.items():
        inputs = sum(calls * mean for calls, mean in groups)
        # 16M is an explicit placeholder for ALL output + auxiliary/compaction
        # prompts and retries outside the listed groups. Replace with real
        # measurements. It is not a claim about the missing baseline breakdown.
        total = inputs + 16_000_000
        result[name] = {"main_inbox_other_calls_and_mean_input": groups,
                        "other_output_auxiliary_reserve": 16_000_000,
                        "gross": total, "retained_ratio": total / BASELINE,
                        "reduction_percent": 100 * (1 - total / BASELINE),
                        "fivefold": total <= TARGET, "target_headroom": TARGET - total}
    return {"baseline": BASELINE, "target": TARGET, "scenarios": result,
            "assumptions": ["No baseline task-success counts or no-event rate were supplied.",
                            "47 polling runs are NOT 47 unique business events.",
                            "282 inbox calls is a hypothetical matched-work result, not an enforced cap.",
                            "Group means, call reductions and 16M reserve all require measurement."]}


if __name__ == "__main__":
    print(json.dumps(projection(), ensure_ascii=False, indent=2))
