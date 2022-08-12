from __future__ import annotations

from typing import Optional

import z3

z3False = z3.BoolVal(False)
z3True = z3.BoolVal(True)


def get_decls(f: z3.ExprRef, rs: Optional[dict[str, int]] = None) -> dict[str, int]:
    if rs is None:
        rs = {}
    if z3.z3_debug():
        assert z3.is_expr(f)
    if z3.is_const(f):
        if not z3.z3util.is_expr_val(f):
            rs.setdefault(str(f), 0)
        return rs
    if f.decl().kind() == z3.Z3_OP_UNINTERPRETED:
        rs.setdefault(str(f.decl()), f.decl().arity())
    for f_ in f.children():
        get_decls(f_, rs)
    return rs


def make_declare_funs(structs: dict[str, list[z3.ArithSortRef]]) -> str:
    return "\n".join(make_declare_fun(name, arity) for name, arity in structs.items())


def make_declare_fun(name, arity) -> str:
    args = " ".join("Int" for _ in range(arity))
    return f"(declare-fun {name} ({args}) Int)"


def z3And(a: z3.BoolRef, b: z3.BoolRef) -> z3.BoolRef:
    if z3.is_false(a) or z3.is_false(b):
        return z3False
    if z3.is_true(a):
        return b
    if z3.is_true(b):
        return a
    return z3.And(a, b)
