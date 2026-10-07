"""The steps shown on the live progress page, matching the engine's progress values."""

from dataclasses import dataclass

from bizzcheckup.engine.types import Category

# (progress % at which the step starts, label). See engine/runner.py.
STEPS: list[tuple[int, str]] = [
    (0, "Visiting your website"),
    (25, "Taking your website's vital signs"),
    *[(40 + 10 * index, f"Checking {category.label}") for index, category in enumerate(Category)],
    (95, "Preparing your report"),
]


@dataclass(frozen=True)
class Step:
    label: str
    state: str  # "done" | "active" | "pending"


def steps_for(progress: int) -> list[Step]:
    result = []
    for index, (start, label) in enumerate(STEPS):
        end = STEPS[index + 1][0] if index + 1 < len(STEPS) else 100
        if progress >= end:
            state = "done"
        elif progress >= start:
            state = "active"
        else:
            state = "pending"
        result.append(Step(label, state))
    return result
