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
        return super()._serialize(value.sexpr(), attr, obj, **kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        ap, fp, pc, prime = z3.Ints(
            f"{AP_VAR_NAME} {FP_VAR_NAME} {PC_VAR_NAME} {PRIME_CONST_NAME}"
        )
        memory = z3.Function(MEMORY_MAP_NAME, z3.IntSort(), z3.IntSort())

        parsed = z3.parse_smt2_string(
            f"(assert {value})",
            decls={
                AP_VAR_NAME: ap,
                FP_VAR_NAME: fp,
                PC_VAR_NAME: pc,
                PRIME_CONST_NAME: prime,
                MEMORY_MAP_NAME: memory,
            },
        )
        if len(parsed) != 1:
            raise ValidationError("Can't deserialize z3.BoolRef")
        return parsed[0]


@marshmallow_dataclass.dataclass(frozen=True)
class HorusChecks:
    asserts: dict[int, z3.BoolRef] = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(keys=mfields.Int(), values=Z3BoolRefField)
        ),
        default_factory=dict,
    )
    requires: dict[int, z3.BoolRef] = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(keys=mfields.Int(), values=Z3BoolRefField)
        ),
        default_factory=dict,
    )
    pre_conds: dict[str, z3.BoolRef] = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(keys=mfields.Str(), values=Z3BoolRefField)
        ),
        default_factory=dict,
    )
    post_conds: dict[str, z3.BoolRef] = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(keys=mfields.Str(), values=Z3BoolRefField)
        ),
        default_factory=dict,
    )
    invariants: dict[str, z3.BoolRef] = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(keys=mfields.Str(), values=Z3BoolRefField)
        ),
        default_factory=dict,
    )


@marshmallow_dataclass.dataclass(frozen=True)
class HorusDefinition(ContractDefinition):
    checks: HorusChecks = field(
        metadata=dict(
            marshmallow_field=mfields.Nested(
                marshmallow_dataclass.class_schema(HorusChecks)()
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
