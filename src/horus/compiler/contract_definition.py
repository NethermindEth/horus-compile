from __future__ import annotations

from dataclasses import field

import marshmallow.fields as mfields
import marshmallow_dataclass
import z3
from marshmallow.exceptions import ValidationError
from starkware.cairo.lang.compiler.ast.cairo_types import CairoType
from starkware.cairo.lang.compiler.fields import CairoTypeAsStr
from starkware.cairo.lang.compiler.scoped_name import ScopedName, ScopedNameAsStr
from starkware.starknet.services.api.contract_class import ContractClass

from horus.compiler.var_names import *


class SexpField(mfields.Field):
    def _serialize(self, value: z3.ExprRef, attr, obj, **kwargs):
        return super()._serialize(value.sexpr().split("\n"), attr, obj, **kwargs)

    def _deserialize(self, value, attr, data, **kwargs) -> z3.ExprRef:
        v = super()._deserialize(value, attr, data, **kwargs)
        ref_str = "\n".join(v)
        refs = z3.parse_smt2_string(ref_str, decls=HORUS_DECLS)
        if len(refs) != 1:
            raise ValidationError(f"Can't deserialize '{ref_str}'")
        return refs[0]  # type: ignore


@marshmallow_dataclass.dataclass
class StorageUpdate:
    arguments: "list[z3.IntNumRef]" = field(
        metadata=dict(marshmallow_field=mfields.List(SexpField())),
        default_factory=list,
    )
    value: z3.IntNumRef = field(
        metadata=dict(marshmallow_field=SexpField()), default=z3.IntVal(0)
    )


@marshmallow_dataclass.dataclass(frozen=False)
class FunctionAnnotations:
    pre: z3.BoolRef = field(
        metadata=dict(marshmallow_field=SexpField()), default=z3.BoolVal(True)
    )
    post: z3.BoolRef = field(
        metadata=dict(marshmallow_field=SexpField()), default=z3.BoolVal(True)
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
    storage_update: "dict[ScopedName, list[StorageUpdate]]" = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(
                ScopedNameAsStr(),
                mfields.List(
                    mfields.Nested(marshmallow_dataclass.class_schema(StorageUpdate))
                ),
            )
        ),
        default_factory=dict,
    )


@marshmallow_dataclass.dataclass(frozen=True)
class HorusDefinition(ContractClass):
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
        metadata=dict(marshmallow_field=mfields.Dict(ScopedNameAsStr(), SexpField())),
        default_factory=dict,
    )
    storage_vars: "dict[ScopedName, int]" = field(
        metadata=dict(marshmallow_field=mfields.Dict(ScopedNameAsStr(), mfields.Int())),
        default_factory=dict,
    )
