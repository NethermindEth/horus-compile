from dataclasses import dataclass
from typing import Union

Check = Union(Precondition, Postcondition, Assertion)

# Each Check should also have an SMT representation of the
# assumption. We've agreed that it would be of some type from the
# Python Z3 lib Julian's using, but we don't know which one yet.

@dataclass
class Precondition:
    function_pc: int

@dataclass
class Postcondition:
    return_pcs: list[int]

@dataclass
class Assertion:
    pass
