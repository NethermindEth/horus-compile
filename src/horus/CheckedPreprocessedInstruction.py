from __future__ import annotations

import dataclasses
from typing import Iterable

from starkware.cairo.lang.compiler.preprocessor import PreprocessedInstruction

from horus.Check import Check


@dataclasses.dataclass
class CheckedPreprocessedInstruction(PreprocessedInstruction):
    checks: tuple[Check, ...]


def wrap(
    instr: PreprocessedInstruction, checks: Iterable[Check]
) -> CheckedPreprocessedInstruction:
    if isinstance(instr, CheckedPreprocessedInstruction):
        return instr.replace(checks=(*instr.checks, *checks))
    else:
        return CheckedPreprocessedInstruction(dataclasses.asdict(instr), checks=checks)
