from __future__ import annotations

from typing import Optional, Tuple

from starkware.cairo.lang.compiler.ast.cairo_types import (
    CairoType,
    TypePointer,
    TypeStruct,
    TypeTuple,
)
from starkware.cairo.lang.compiler.ast.expr import (
    ExprCast,
    ExprConst,
    ExprDeref,
    ExprDot,
    Expression,
    ExprIdentifier,
    ExprOperator,
    ExprReg,
    ExprSubscript,
    ExprTuple,
)
from starkware.cairo.lang.compiler.expression_simplifier import ExpressionSimplifier
from starkware.cairo.lang.compiler.identifier_definition import (
    ConstDefinition,
    NamespaceDefinition,
    StructDefinition,
)
from starkware.cairo.lang.compiler.identifier_manager import (
    IdentifierManager,
    MissingIdentifierError,
)
from starkware.cairo.lang.compiler.identifier_utils import get_struct_definition
from starkware.cairo.lang.compiler.instruction import Register
from starkware.cairo.lang.compiler.preprocessor.preprocessor import Preprocessor
from starkware.cairo.lang.compiler.preprocessor.preprocessor_error import (
    PreprocessorError,
)
from starkware.cairo.lang.compiler.resolve_search_result import resolve_search_result
from starkware.cairo.lang.compiler.scoped_name import ScopedName
from starkware.cairo.lang.compiler.substitute_identifiers import substitute_identifiers
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
        accessible_scopes: list[ScopedName] = None,
        identifiers: Optional[IdentifierManager] = None,
        logical_identifiers: dict[str, CairoType] = {},
    ):
        super().__init__(identifiers)
        self.accessible_scopes = accessible_scopes
        self.identifiers = identifiers
        self.logical_identifiers = logical_identifiers

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

    def visit_ExprCast(self, expr: ExprCast) -> Tuple[Expression, CairoType]:
        if isinstance(expr.dest_type, TypeStruct):
            assert self.identifiers is not None
            search_result = self.identifiers.search(
                self.accessible_scopes, expr.dest_type.scope
            )
            definition = resolve_search_result(search_result, self.identifiers)

            if isinstance(definition, NamespaceDefinition):
                try:
                    self.identifiers.search(
                        self.accessible_scopes, expr.dest_type.scope + "read"
                    )
                    self.identifiers.search(
                        self.accessible_scopes, expr.dest_type.scope + "write"
                    )

                    ret_struct_def = get_struct_definition(
                        search_result.canonical_name + "read" + "Return",
                        self.identifiers,
                    )
                    assert isinstance(ret_struct_def, StructDefinition)

                    if len(ret_struct_def.members) != 1:
                        raise CairoTypeError(
                            "Storage maps with return tuple of length higher than 1 are not supported yet",
                            location=expr.location,
                        )

                    return expr, next(iter(ret_struct_def.members.values())).cairo_type
                except MissingIdentifierError:
                    # Failed to find the storage variable stuff.
                    raise CairoTypeError(
                        "Function calls are not allowed in assertions",
                        location=expr.location,
                    )

        return super().visit_ExprCast(expr)  # type: ignore


def get_return_variable(name: str, preprocessor: Preprocessor):
    definition = get_struct_definition(
        preprocessor.current_scope + "Return", preprocessor.identifiers
    )
    assert isinstance(definition, StructDefinition)
    return_type = TypeStruct(definition.full_name, is_fully_resolved=True)

    return_struct = ExprCast(
        expr=ExprOperator(ExprReg(Register.AP), "-", ExprConst(definition.size)),
        dest_type=TypePointer(return_type),
    )

    result = return_struct
    for member_name in name.split("."):
        result = ExprDot(result, ExprIdentifier(member_name))

    return result


def simplify_and_get_type(
    expr: Expression,
    preprocessor: Preprocessor,
    logical_identifiers: dict[str, CairoType],
    is_post: bool,
) -> tuple[Expression, CairoType]:
    def get_identifier(expr: ExprIdentifier):
        if is_post:
            definition = get_struct_definition(
                preprocessor.current_scope + "ImplicitArgs", preprocessor.identifiers
            )

            if definition.members.get(expr.name.split(".")[0]) is not None:
                implicit_args_type = TypeStruct(
                    definition.full_name, is_fully_resolved=True
                )
                return_def = get_struct_definition(
                    preprocessor.current_scope + "Return", preprocessor.identifiers
                )

                implicit_args_struct = ExprCast(
                    expr=ExprOperator(
                        ExprReg(Register.AP),
                        "-",
                        ExprConst(definition.size + return_def.size),
                    ),
                    dest_type=TypePointer(implicit_args_type),
                )

                result = implicit_args_struct
                for member_name in expr.name.split("."):
                    result = ExprDot(result, ExprIdentifier(member_name))

                return result

        if expr.name.startswith("$Return."):
            return get_return_variable(expr.name[len("$Return.") :], preprocessor)

        search_result = preprocessor.identifiers.search(
            preprocessor.accessible_scopes,
            ScopedName.from_string(expr.name),
        )
        definition = resolve_search_result(search_result, preprocessor.identifiers)

        if isinstance(definition, ConstDefinition):
            return ExprConst(definition.value)
        else:
            return definition.eval(
                preprocessor.flow_tracking.reference_manager,
                preprocessor.flow_tracking.data,
            )

    return HorusTypeChecker(
        preprocessor.accessible_scopes,
        preprocessor.identifiers,
        logical_identifiers,
    ).visit(substitute_identifiers(expr, get_identifier))


def simplify(
    expr: Expression,
    preprocessor: Preprocessor,
    logical_identifiers: dict[str, CairoType],
    is_post: bool,
) -> Expression:
    return simplify_and_get_type(expr, preprocessor, logical_identifiers, is_post)[0]
