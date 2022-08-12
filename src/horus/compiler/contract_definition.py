from __future__ import annotations

from dataclasses import field

import marshmallow.fields as mfields
import marshmallow_dataclass
import z3
from marshmallow.exceptions import ValidationError
from starkware.cairo.lang.compiler.ast.cairo_types import CairoType
from starkware.cairo.lang.compiler.fields import CairoTypeAsStr
from starkware.cairo.lang.compiler.scoped_name import ScopedName, ScopedNameAsStr
from starkware.starknet.services.api.contract_definition import ContractDefinition

from horus.compiler.var_names import *


class IntNumRefAsStr(mfields.Field):
    def _serialize(self, value: z3.IntNumRef, attr, obj, **kwargs):
        return super()._serialize(value.sexpr(), attr, obj, **kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        return z3.parse_smt2_string(value)


@marshmallow_dataclass.dataclass
class StateAnnotation:
    arguments: "list[z3.IntNumRef]" = field(
        metadata=dict(marshmallow_field=mfields.List(IntNumRefAsStr())),
        default_factory=list,
    )
    value: z3.IntNumRef = field(
        metadata=dict(marshmallow_field=IntNumRefAsStr()), default=z3.IntVal(0)
    )


class AssertionField(mfields.Field):
    def _serialize(self, value: z3.BoolRef, attr, obj, **kwargs):
        return super()._serialize(value.sexpr().split("\n"), attr, obj, **kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        v = super()._deserialize(value, attr, data, **kwargs)
        bool_ref_str = "\n".join(v)
        bool_refs = z3.parse_smt2_string(bool_ref_str, decls=HORUS_DECLS)
        if len(bool_refs) != 1:
            raise ValidationError(f"Can't deserialize '{bool_ref_str}'")
        return bool_refs[0]  # type: ignore


@marshmallow_dataclass.dataclass(frozen=False)
class FunctionAnnotations:
    pre: z3.BoolRef = field(
        metadata=dict(marshmallow_field=AssertionField()), default=z3.BoolVal(True)
    )
    post: z3.BoolRef = field(
        metadata=dict(marshmallow_field=AssertionField()), default=z3.BoolVal(True)
    )
    logical_variables: "dict[ScopedName, CairoType]" = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(ScopedNameAsStr(), CairoTypeAsStr())
        ),
        default_factory=dict,
    )
    decls: "dict[str, int]" = field(
        metadata=dict(marshmallow_field=mfields.Dict(mfields.Str(), mfields.Int())),
        default_factory=dict,
    )
    state: "dict[ScopedName, list[StateAnnotation]]" = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(
                ScopedNameAsStr(),
                mfields.List(
                    mfields.Nested(marshmallow_dataclass.class_schema(StateAnnotation))
                ),
            )
        ),
        default_factory=dict,
    )


@marshmallow_dataclass.dataclass(frozen=True)
class HorusDefinition(ContractDefinition):
    specifications: "dict[ScopedName, FunctionAnnotations]" = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(
                ScopedNameAsStr(),
                mfields.Nested(marshmallow_dataclass.class_schema(FunctionAnnotations)),
            )
        ),
        default_factory=dict,
    )
    invariants: "dict[ScopedName, z3.BoolRef]" = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(ScopedNameAsStr(), AssertionField())
        ),
        default_factory=dict,
    )
