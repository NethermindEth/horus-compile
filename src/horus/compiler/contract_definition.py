from __future__ import annotations

from dataclasses import field
from typing import Dict, List, Optional

import marshmallow.fields as mfields
import marshmallow_dataclass
import z3
from marshmallow.exceptions import ValidationError
from starkware.cairo.lang.compiler.ast.cairo_types import CairoType
from starkware.cairo.lang.compiler.fields import CairoTypeAsStr
from starkware.cairo.lang.compiler.scoped_name import ScopedName, ScopedNameAsStr

import horus
from horus.compiler.var_names import *
from horus.utils import z3And


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
    arguments: List[z3.IntNumRef] = field(
        metadata=dict(marshmallow_field=mfields.List(SexpField())),
        default_factory=list,
    )
    value: z3.IntNumRef = field(
        metadata=dict(marshmallow_field=SexpField()), default=z3.IntVal(0)
    )
    source: str = field(metadata=dict(marshmallow_field=mfields.String()), default="")


@marshmallow_dataclass.dataclass(frozen=False)
class Annotation:
    sexpr: z3.BoolRef = field(
        metadata=dict(marshmallow_field=SexpField()), default=z3.BoolVal(True)
    )
    source: List[str] = field(
        metadata=dict(marshmallow_field=mfields.List(mfields.String())),
        default_factory=list,
    )

    def __and__(self, other):
        return Annotation(
            sexpr=z3And(self.sexpr, other.sexpr), source=self.source + other.source
        )


@marshmallow_dataclass.dataclass(frozen=False)
class FunctionAnnotations:
    pre: Annotation = field(
        metadata=dict(
            marshmallow_field=mfields.Nested(
                marshmallow_dataclass.class_schema(Annotation)
            )
        ),
        default=Annotation(),
    )
    post: Annotation = field(
        metadata=dict(
            marshmallow_field=mfields.Nested(
                marshmallow_dataclass.class_schema(Annotation)
            )
        ),
        default=Annotation(),
    )
    logical_variables: Dict[ScopedName, CairoType] = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(ScopedNameAsStr(), CairoTypeAsStr())
        ),
        default_factory=dict,
    )
    decls: Dict[str, int] = field(
        metadata=dict(marshmallow_field=mfields.Dict(mfields.Str(), mfields.Int())),
        default_factory=dict,
    )
    storage_update: Dict[ScopedName, List[StorageUpdate]] = field(
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
class HorusDefinition:
    horus_version: Optional[str] = field(
        metadata=dict(marshmallow_field=mfields.String()), default=horus.__version__
    )
    specifications: Dict[ScopedName, FunctionAnnotations] = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(
                ScopedNameAsStr(),
                mfields.Nested(marshmallow_dataclass.class_schema(FunctionAnnotations)),
            )
        ),
        default_factory=dict,
    )
    invariants: Dict[ScopedName, Annotation] = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(
                ScopedNameAsStr(),
                mfields.Nested(marshmallow_dataclass.class_schema(Annotation)),
            )
        ),
        default_factory=dict,
    )
    storage_vars: Dict[ScopedName, int] = field(
        metadata=dict(marshmallow_field=mfields.Dict(ScopedNameAsStr(), mfields.Int())),
        default_factory=dict,
    )
