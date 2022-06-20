from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Any, Callable, Optional, Union

import lark
import z3
from starkware.cairo.lang.compiler.ast.cairo_types import CairoType, TypeFelt
from starkware.cairo.lang.compiler.ast.expr import (
    ExprCast,
    ExprConst,
    ExprDeref,
    Expression,
    ExprOperator,
    ExprReg,
)
from starkware.cairo.lang.compiler.identifier_definition import (
    IdentifierDefinition,
    ReferenceDefinition,
)
from starkware.cairo.lang.compiler.identifier_manager import (
    IdentifierError,
    IdentifierManager,
)
from starkware.cairo.lang.compiler.instruction import Register
from starkware.cairo.lang.compiler.offset_reference import OffsetReferenceDefinition
from starkware.cairo.lang.compiler.preprocessor.flow import FlowTracking
from starkware.cairo.lang.compiler.preprocessor.preprocessor import Preprocessor
from starkware.cairo.lang.compiler.preprocessor.preprocessor_error import (
    PreprocessorError,
)
from starkware.cairo.lang.compiler.resolve_search_result import resolve_search_result
from starkware.cairo.lang.compiler.scoped_name import ScopedName
from starkware.crypto.signature.signature import FIELD_PRIME

from horus.compiler.var_names import *
from horus.horus_error import HorusError


@lark.v_args(inline=True)
class Z3Transformer(lark.Transformer):
    def __init__(
        self,
        identifiers: IdentifierManager,
        accessible_scopes: list[ScopedName],
        flow_tracking: FlowTracking,
        preprocessor: Preprocessor,
    ):
        super().__init__()
        self.identifiers = identifiers
        self.accessible_scopes = accessible_scopes
        self.flow_tracking = flow_tracking
        self.preprocessor = preprocessor

        self.memory = z3.Function(MEMORY_MAP_NAME, z3.IntSort(), z3.IntSort())
        self.ap, self.fp, self.prime = z3.Ints(
            f"{AP_VAR_NAME} {FP_VAR_NAME} {PRIME_CONST_NAME}"
        )

    def expr_add(self, lhs, _, rhs):
        return (lhs + rhs) % self.prime

    def expr_sub(self, lhs, _, rhs):
        return (lhs - rhs) % self.prime

    def expr_mul(self, lhs, _, rhs):
        return (lhs * rhs) % self.prime

    def expr_div(self, lhs, _, rhs):
        return (lhs / rhs) % self.prime

    def unary_neg(self, v):
        return (-v) % self.prime

    def expr_pow(self, lhs, _, rhs):
        return z3.ToInt(lhs**rhs) % self.prime

    @lark.v_args(inline=False)
    def identifier(self, parts: list[lark.Token]) -> z3.ExprRef:
        full_name = ".".join(parts)
        definition = self._search_identifier(full_name)
        return self._smtify_definition(definition)

    def logical_identifier(self, name):
        return z3.Int(name)

    def atom_number(self, value):
        return z3.IntVal(value)

    def atom_hex_number(self, value):
        return int(value, base=16)

    def atom_reg(self, reg):
        return reg

    def atom_deref(self, _, index):
        return self.memory(index)

    def atom_tuple_or_parentheses(self, expr):
        return expr

    def reg_ap(self, _):
        return self.ap

    def reg_fp(self, _):
        return self.fp

    def bool_formula_impl(self, lhs, rhs):
        return z3.Implies(lhs, rhs)

    def bool_formula_or(self, lhs, rhs):
        return z3.Or(lhs, rhs)

    def bool_formula_and(self, lhs, rhs):
        return z3.And(lhs, rhs)

    def bool_unary_neg(self, formula):
        return z3.Not(formula)

    def bool_expr_true(self):
        return z3.BoolVal(True)

    def bool_expr_false(self):
        return z3.BoolVal(False)

    def bool_expr_eq(self, lhs, rhs):
        return lhs == rhs

    def bool_expr_ne(self, lhs, rhs):
        return lhs != rhs

    def bool_expr_le(self, lhs, rhs):
        return lhs <= rhs

    def bool_expr_lt(self, lhs, rhs):
        return lhs < rhs

    def bool_expr_ge(self, lhs, rhs):
        return lhs >= rhs

    def bool_expr_gt(self, lhs, rhs):
        return lhs > rhs

    def bool_expr_parentheses(self, formula):
        return formula

    def precond_annotation(self, expr):
        return PreprocessedCheck(CheckKind.PRE_COND, expr)

    def postcond_annotation(self, expr):
        return PreprocessedCheck(CheckKind.POST_COND, expr)

    def assert_annotation(self, expr):
        return PreprocessedCheck(CheckKind.ASSERT, expr)

    def require_annotation(self, expr):
        return PreprocessedCheck(CheckKind.REQUIRE, expr)

    def invariant_annotation(self, expr):
        return PreprocessedCheck(CheckKind.INVARIANT, expr)

    def declare_annotation(self, identifier):
        return LogicalVariableDeclaration(identifier, TypeFelt)

    def transform(
        self, tree: lark.Tree
    ) -> Union[PreprocessedCheck, LogicalVariableDeclaration]:
        # The nodes of the tree imported from cairo.ebnf appear with
        # prefix starkware__cairo__lang__compiler__cairo__ which we remove here.
        for node in tree.iter_subtrees():
            node.data = node.data.replace(
                "starkware__cairo__lang__compiler__cairo__", ""
            )

        result: Union[
            PreprocessedCheck, LogicalVariableDeclaration
        ] = super().transform(tree)

        return result

    def _search_identifier(self, name: str) -> IdentifierDefinition:
        """
        Searches for the given identifier in self.identifiers and returns the corresponding
        IdentifierDefinition.
        """
        try:
            result = self.identifiers.search(
                self.accessible_scopes, ScopedName.from_string(name)
            )
            return resolve_search_result(result, identifiers=self.identifiers)
        except IdentifierError as exc:
            # TODO add location within the hint
            raise PreprocessorError(str(exc), location=None)

    def _smtify_definition(self, definition: IdentifierDefinition) -> z3.ExprRef:
        if isinstance(definition, (ReferenceDefinition, OffsetReferenceDefinition)):
            expr = self.preprocessor.simplify_expr_as_felt(
                definition.eval(
                    self.flow_tracking.reference_manager, self.flow_tracking.data
                )
            )
            return self._smtify_expression(expr)
        else:
            raise HorusError(f"Unsupported definition for smtification: {definition}")

    def _smtify_expression(self, expr: Expression) -> z3.ExprRef:
        if isinstance(expr, ExprConst):
            return z3.IntVal(expr.val)
        elif isinstance(expr, ExprDeref):
            return self.memory(self._smtify_expression(expr.addr))
        elif isinstance(expr, ExprCast):
            return self._smtify_expression(expr.expr)
        elif isinstance(expr, ExprOperator):
            lhs = self._smtify_expression(expr.a)
            rhs = self._smtify_expression(expr.b)
            op = str2op(expr.op)
            return op(lhs, rhs) % self.prime
        elif isinstance(expr, ExprReg):
            if expr.reg is Register.AP:
                return self.ap
            else:
                assert expr.reg is Register.FP
                return self.fp
        else:
            raise HorusError(
                f"Unsupported expression for smtification of type {type(expr)}: '{expr.format()}'"
            )


def str2op(s: str) -> Callable:
    if s == "+":
        return lambda a, b: a + b
    elif s == "-":
        return lambda a, b: a - b
    elif s == "*":
        return lambda a, b: a * b
    else:
        raise NotImplementedError(f"Unsupported operator '{s}")


class CheckKind(Enum):
    ASSERT = auto()
    REQUIRE = auto()
    POST_COND = auto()
    PRE_COND = auto()
    INVARIANT = auto()


@dataclasses.dataclass
class LogicalVariableDeclaration:
    name: str
    type: Optional[CairoType]


@dataclasses.dataclass
class PreprocessedCheck:
    kind: CheckKind
    expr: z3.BoolRef
