"""The steps shown on the live progress page, matching the engine's progress values."""

from dataclasses import dataclass

from bizzcheckup.engine import runner
from bizzcheckup.engine.types import Category

# (progress % at which the step starts, label). Same milestones as engine/runner.py.
STEPS: list[tuple[int, str]] = [
    (0, "Visiting your website"),
    (runner.COLLECT_START, "Taking your website's vital signs"),
    *[
        (runner.CHECKS_START + runner.CHECKS_STEP * index, f"Checking {category.label}")
        for index, category in enumerate(Category)
    ],
    (runner.SHOTS_START, "Taking pictures of the problems"),
    (runner.REPORT_START, "Preparing your report"),
]


@dataclass(frozen=True)
class Step:
    label: str
    state: str  # "done" | "active" | "pending"
    start: int  # progress % where this step begins
    end: int  # progress % where the next one begins (the page animates between them)


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
        result.append(Step(label, state, start, end))
    return result
