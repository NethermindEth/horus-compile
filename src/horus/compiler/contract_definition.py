from dataclasses import dataclass, field
from typing import Dict

import marshmallow.fields as mfields
import marshmallow_dataclass
import z3
from marshmallow.exceptions import ValidationError
from starkware.starknet.services.api.contract_definition import ContractDefinition

from horus.compiler.var_names import *
from horus.utils import get_decls, make_declare_funs


@dataclass
class Assertion:
    """
    A check with an additional constraint which must be
    added to solver's goal in a positive way.
    For now `axiom` is either `True` or a multiplicative inverse
    condition for some variable.
    """

    bool_ref: z3.BoolRef
    axiom: z3.BoolRef


class AssertionField(mfields.Field):
    def _serialize(self, value: Assertion, attr, obj, **kwargs):
        decls = get_decls(value.bool_ref)
        for var in HORUS_DECLS.keys():
            decls.pop(var, None)
        v = {
            "axiom": value.axiom.sexpr().split("\n"),
            "bool_ref": value.bool_ref.sexpr().split("\n"),
            "decls": decls,
        }
        if not decls:
            del v["decls"]
        if z3.is_true(value.axiom):
            del v["axiom"]
        return super()._serialize(v, attr, obj, **kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        v = super()._deserialize(value, attr, data, **kwargs)
        declare_funs = make_declare_funs(v.get("decls", {}))
        axiom_str = "\n".join(v.get("axiom", ["true"]))
        bool_ref_str = "\n".join(v["bool_ref"])
        axiom_full = f"{declare_funs}\n(assert {axiom_str})"
        bool_ref_full = f"{declare_funs}\n(assert {bool_ref_str})"
        axioms = z3.parse_smt2_string(axiom_full, decls=HORUS_DECLS)
        bool_refs = z3.parse_smt2_string(bool_ref_full, decls=HORUS_DECLS)
        if len(axioms) != 1:
            raise ValidationError(f"Can't deserialize '{axiom_full}'")
        if len(bool_refs) != 1:
            raise ValidationError(f"Can't deserialize '{bool_ref_full}'")
        return Assertion(bool_ref=bool_refs[0], axiom=axioms[0])  # type: ignore


@marshmallow_dataclass.dataclass(frozen=True)
class HorusChecks:
    asserts: Dict[int, Assertion] = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(keys=mfields.Int(), values=AssertionField())
        ),
        default_factory=dict,
    )
    requires: Dict[int, Assertion] = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(keys=mfields.Int(), values=AssertionField())
        ),
        default_factory=dict,
    )
    pre_conds: Dict[str, Assertion] = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(keys=mfields.Str(), values=AssertionField())
        ),
        default_factory=dict,
    )
    post_conds: Dict[str, Assertion] = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(keys=mfields.Str(), values=AssertionField())
        ),
        default_factory=dict,
    )
    invariants: Dict[str, Assertion] = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(keys=mfields.Str(), values=AssertionField())
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
    ret_map: Dict[int, str] = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(keys=mfields.Int(), values=mfields.Str())
        ),
        default_factory=dict,
    )
    logical_variables: Dict[str, Dict[str, str]] = field(
        metadata=dict(
            marshmallow_field=mfields.Dict(
                mfields.Str(), mfields.Dict(keys=mfields.Str(), values=mfields.Str())
            )
        ),
        default_factory=dict,
    )
    smt: str = ""
