from __future__ import annotations

from typing import Optional

from starkware.cairo.lang.compiler.ast.cairo_types import (
    CairoType,
    TypeStruct,
    TypeTuple,
)
from starkware.cairo.lang.compiler.ast.expr import (
    ExprConst,
    ExprDeref,
    ExprDot,
    Expression,
    ExprSubscript,
)
from starkware.cairo.lang.compiler.expression_simplifier import ExpressionSimplifier
from starkware.cairo.lang.compiler.identifier_manager import IdentifierManager
from starkware.cairo.lang.compiler.identifier_utils import get_struct_definition
from starkware.cairo.lang.compiler.type_casts import CairoTypeError
from starkware.cairo.lang.compiler.type_system_visitor import TypeSystemVisitor

from horus.compiler.code_elements import ExprLogicalIdentifier


def get_expr_addr(expr: Expression):
    if isinstance(expr, ExprLogicalIdentifier):
        return expr

    if not isinstance(expr, ExprDeref):
        raise CairoTypeError("Expression has no address.", location=expr.location)
    return expr.addr


class HorusTypeChecker(TypeSystemVisitor):
    def __init__(
        self,
        identifiers: Optional[IdentifierManager] = None,
        logical_identifiers: dict[str, CairoType] = {},
    ):
        self.logical_identifiers = logical_identifiers
        super().__init__(identifiers)

    def visit(self, expr: Expression) -> tuple[Expression, CairoType]:
        return super().visit(expr)  # type: ignore

    def visit_ExprLogicalIdentifier(
        self, expr: ExprLogicalIdentifier
    ) -> tuple[ExprLogicalIdentifier, CairoType]:
        return (expr, self.logical_identifiers[expr.name])

    def visit_ExprDot(self, expr: ExprDot):
        inner_expr, inner_type = self.visit(expr.expr)
        if isinstance(inner_expr, ExprLogicalIdentifier):
            if not isinstance(inner_type, (TypeStruct, TypeTuple)):
                raise CairoTypeError("wrong type", location=expr.location)

            struct_def = get_struct_definition(
                struct_name=inner_type.resolved_scope,
                identifier_manager=self.identifiers,
            )
            if expr.member.name not in struct_def.members:
                raise CairoTypeError(
                    f"Member '{expr.member.name}' does not appear in definition of struct "
                    f"'{inner_type.format()}'.",
                    location=expr.location,
                )

            return (
                ExprLogicalIdentifier(
                    f"{inner_expr.name}.{expr.member.name}", location=expr.location
                ),
                struct_def.members[expr.member.name].cairo_type,
            )
        else:
            return super().visit_ExprDot(expr)

    def visit_ExprSubscript(self, expr: ExprSubscript):
        inner_expr, inner_type = self.visit(expr.expr)
        offset_expr, offset_type = self.visit(expr.offset)

        if isinstance(inner_type, TypeTuple):
            if isinstance(inner_expr, ExprLogicalIdentifier):
                self.verify_offset_is_felt(offset_type, offset_expr.location)
                offset_expr = ExpressionSimplifier().visit(offset_expr)
                if not isinstance(offset_expr, ExprConst):
                    raise CairoTypeError(
                        "Subscript-operator for tuples supports only constant offsets, found "
                        f"'{type(offset_expr).__name__}'.",
                        location=offset_expr.location,
                    )
                offset_value = offset_expr.val

                tuple_len = len(inner_type.members)
                if not 0 <= offset_value < tuple_len:
                    raise CairoTypeError(
                        f"Tuple index {offset_value} is out of range [0, {tuple_len}).",
                        location=expr.location,
                    )
                logical_identifier_name = f"{inner_expr.name}.{offset_value}"
                return (
                    ExprLogicalIdentifier(logical_identifier_name),
                    self.logical_identifiers[logical_identifier_name],
                )

        return super().visit_ExprSubscript(expr)
