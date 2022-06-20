from __future__ import annotations

from dataclasses import field

import marshmallow.fields as mfields
import marshmallow_dataclass
import z3
from marshmallow.exceptions import ValidationError
from starkware.starknet.services.api.contract_definition import ContractDefinition

from horus.compiler.var_names import *


class Z3BoolRefField(mfields.Field):
    def _serialize(self, value: z3.BoolRef, attr, obj, **kwargs):
        # The purpose of creating a solver instance here
        # is to have variable declarations at the resulting smtlib expressions.
        solver = z3.Solver()
        solver.add(value)
        return super()._serialize(solver.sexpr(), attr, obj, **kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        parsed = z3.parse_smt2_string(value)
        if len(parsed) != 1:
            raise ValidationError("Can't deserialize z3.BoolRef")
        return parsed[0]


@marshmallow_dataclass.dataclass(frozen=True)
class BoolRefWithAxiom:
    """
    A check with an additional constraint which must be
    added to solver's goal in a positive way.
    For now `axiom` is either `True` or a multiplicative inverse
    condition for some variable.
    """

    bool_ref: z3.BoolRef = field(metadata=dict(marshmallow_field=Z3BoolRefField()))
    axiom: z3.BoolRef = field(metadata=dict(marshmallow_field=Z3BoolRefField()))


@marshmallow_dataclass.dataclass(frozen=True)
class HorusChecks:
    asserts: dict[int, BoolRefWithAxiom] = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(
                keys=mfields.Int(),
                values=mfields.Nested(
                    marshmallow_dataclass.class_schema(BoolRefWithAxiom)
                ),
            )
        ),
        default_factory=dict,
    )
    requires: dict[int, BoolRefWithAxiom] = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(
                keys=mfields.Int(),
                values=mfields.Nested(
                    marshmallow_dataclass.class_schema(BoolRefWithAxiom)
                ),
            )
        ),
        default_factory=dict,
    )
    pre_conds: dict[str, BoolRefWithAxiom] = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(
                keys=mfields.Str(),
                values=mfields.Nested(
                    marshmallow_dataclass.class_schema(BoolRefWithAxiom)
                ),
            )
        ),
        default_factory=dict,
    )
    post_conds: dict[str, BoolRefWithAxiom] = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(
                keys=mfields.Str(),
                values=mfields.Nested(
                    marshmallow_dataclass.class_schema(BoolRefWithAxiom)
                ),
            )
        ),
        default_factory=dict,
    )
    invariants: dict[str, BoolRefWithAxiom] = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(
                keys=mfields.Str(),
                values=mfields.Nested(
                    marshmallow_dataclass.class_schema(BoolRefWithAxiom)
                ),
            )
        ),
        default_factory=dict,
    )


@marshmallow_dataclass.dataclass(frozen=True)
class HorusDefinition(ContractDefinition):
    checks: HorusChecks = field(
        metadata=dict(
            marshmallow_field=mfields.Nested(
                marshmallow_dataclass.class_schema(HorusChecks)
            )
        ),
        default=HorusChecks(),
    )
    ret_map: dict[int, str] = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(keys=mfields.Int(), values=mfields.Str())
        ),
        default_factory=dict,
    )
    logical_variables: dict[str, dict[str, str]] = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(
                mfields.Str(), mfields.Dict(keys=mfields.Str(), values=mfields.Str())
            )
        ),
        default_factory=dict,
    )
