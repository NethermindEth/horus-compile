from __future__ import annotations

import dataclasses
from typing import Dict, List, Optional, Tuple

from starkware.cairo.lang.compiler.ast.arguments import IdentifierList
from starkware.cairo.lang.compiler.ast.cairo_types import (
    CairoType,
    TypeFelt,
    TypeIdentifier,
    TypePointer,
    TypeStruct,
    TypeTuple,
)
from starkware.cairo.lang.compiler.ast.expr import (
    ExprAssignment,
    ExprCast,
    ExprConst,
    ExprDeref,
    ExprDot,
    Expression,
    ExprIdentifier,
    ExprOperator,
    ExprReg,
    ExprSubscript,
)
from starkware.cairo.lang.compiler.ast.expr_func_call import (
    ExprFuncCall,
    RvalueFuncCall,
)
from starkware.cairo.lang.compiler.expression_simplifier import ExpressionSimplifier
from starkware.cairo.lang.compiler.identifier_definition import (
    ConstDefinition,
    FunctionDefinition,
    NamespaceDefinition,
    ReferenceDefinition,
    TypeDefinition,
)
from starkware.cairo.lang.compiler.identifier_manager import (
    IdentifierManager,
    MissingIdentifierError,
)
from starkware.cairo.lang.compiler.identifier_utils import (
    get_struct_definition,
    get_type_definition,
)
from starkware.cairo.lang.compiler.instruction import Register
from starkware.cairo.lang.compiler.offset_reference import OffsetReferenceDefinition
from starkware.cairo.lang.compiler.preprocessor.preprocessor import Preprocessor
from starkware.cairo.lang.compiler.resolve_search_result import resolve_search_result
from starkware.cairo.lang.compiler.scoped_name import ScopedName
from starkware.cairo.lang.compiler.substitute_identifiers import (
    GetIdentifierCallback,
    GetStructMembersCallback,
    ResolveTypeCallback,
    SubstituteIdentifiers,
)
from starkware.cairo.lang.compiler.type_casts import CairoTypeError
from starkware.cairo.lang.compiler.type_system_visitor import TypeSystemVisitor
from starkware.crypto.signature.signature import FIELD_PRIME

from horus.compiler.allowed_syscalls import allowed_syscalls
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
        accessible_scopes: Optional[List[ScopedName]] = None,
        identifiers: Optional[IdentifierManager] = None,
        logical_identifiers: Dict[str, CairoType] = {},
        storage_vars: Dict[ScopedName, IdentifierList] = {},
    ):
        super().__init__(identifiers)
        self.accessible_scopes = accessible_scopes
        self.identifiers = identifiers
        self.logical_identifiers = logical_identifiers
        self.storage_vars = storage_vars

    def visit(self, expr: Expression) -> tuple[Expression, CairoType]:
        return super().visit(expr)  # type: ignore

    def visit_ExprLogicalIdentifier(
        self, expr: ExprLogicalIdentifier
    ) -> tuple[ExprLogicalIdentifier, CairoType]:
        try:
            return (expr, self.logical_identifiers[expr.name])
        except KeyError:
            raise MissingIdentifierError(expr.name)

    def visit_ExprDot(self, expr: ExprDot):
        inner_expr, inner_type = self.visit(expr.expr)
        inner_type = self.resolve_type(inner_type)
        if isinstance(inner_expr, ExprLogicalIdentifier):
            if not isinstance(inner_type, (TypeStruct, TypeTuple)):
                raise CairoTypeError("wrong type", location=expr.location)

            struct_def = get_struct_definition(
                struct_name=inner_type.scope,
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

                    ret_type_def = get_type_definition(
                        search_result.canonical_name + "read" + "Return",
                        self.identifiers,
                    )
                    assert isinstance(ret_type_def, TypeDefinition)
                    assert isinstance(ret_type_def.cairo_type, TypeTuple)

                    if len(ret_type_def.cairo_type.members) != 1:
                        raise CairoTypeError(
                            "Storage maps with return tuple of length higher than 1 are not supported yet",
                            location=expr.location,
                        )

                    return expr, ret_type_def.cairo_type.members[0].typ
                except MissingIdentifierError:
                    # Failed to find the storage variable stuff.
                    raise CairoTypeError(
                        "Function calls are not allowed in assertions",
                        location=expr.location,
                    )
            elif isinstance(definition, FunctionDefinition):
                if search_result.canonical_name in allowed_syscalls:
                    return expr, TypeFelt(expr.location)

        return super().visit_ExprCast(expr)  # type: ignore

    def visit_ExprFuncCall(self, expr: ExprFuncCall) -> Tuple[ExprFuncCall, CairoType]:
        assert self.identifiers is not None
        search_result = self.identifiers.search(
            self.accessible_scopes, ScopedName.from_string(expr.rvalue.func_ident.name)
        )
        definition = resolve_search_result(search_result, self.identifiers)

        if search_result.canonical_name in allowed_syscalls:
            return expr, TypeFelt(expr.location)

        if isinstance(definition, NamespaceDefinition):
            try:
                self.identifiers.search(
                    self.accessible_scopes,
                    ScopedName.from_string(expr.rvalue.func_ident.name) + "read",
                )
                self.identifiers.search(
                    self.accessible_scopes,
                    ScopedName.from_string(expr.rvalue.func_ident.name) + "write",
                )

                ret_type_def = get_type_definition(
                    search_result.canonical_name + "read" + "Return",
                    self.identifiers,
                )
                assert isinstance(ret_type_def, TypeDefinition)
                assert isinstance(ret_type_def.cairo_type, TypeTuple)

                if len(ret_type_def.cairo_type.members) != 1:
                    raise CairoTypeError(
                        "Storage maps with return tuple of length higher than 1 are not supported yet",
                        location=expr.location,
                    )

                if len(expr.rvalue.arguments.args) != len(
                    self.storage_vars[search_result.canonical_name].identifiers
                ):
                    raise CairoTypeError(
                        f"Storage var {search_result.canonical_name} has {len(self.storage_vars[search_result.canonical_name].identifiers)} arguments. Provided {len(expr.rvalue.arguments.args)}",
                        location=expr.location,
                    )

                args_signature = self.storage_vars[
                    search_result.canonical_name
                ].identifiers.copy()
                is_named = False
                for arg in expr.rvalue.arguments.args:
                    assert isinstance(arg, ExprAssignment)

                    if arg.identifier is None:
                        if is_named:
                            raise CairoTypeError(
                                "Unnamed argument cannot follow named ones",
                                location=arg.location,
                            )

                        found_arg = args_signature.pop(0)
                    else:
                        is_named = True
                        found_arg = next(
                            (
                                x
                                for x in args_signature
                                if arg.identifier.name == x.identifier.name
                            ),
                            None,
                        )
                        if found_arg is None:
                            raise CairoTypeError(
                                f"Unknown argument {arg.identifier.name}",
                                location=arg.identifier.location,
                            )

                        args_signature.remove(found_arg)

                    _, arg_type = self.visit(arg.expr)

                    if arg_type != found_arg.expr_type:
                        raise CairoTypeError(
                            f"The argument is expected to have type {found_arg.expr_type}",
                            location=arg.expr.location,
                        )

                return expr, ret_type_def.cairo_type.members[0].typ
            except MissingIdentifierError as e:
                # Failed to find the storage variable stuff.
                raise CairoTypeError(
                    "Function calls are not allowed in assertions",
                    location=expr.location,
                ) from e

        raise CairoTypeError(
            "Function calls are not allowed in assertions",
            location=expr.location,
        )


def get_return_variable(name: str, preprocessor: Preprocessor):
    definition = get_type_definition(
        preprocessor.current_scope + "Return", preprocessor.identifiers
    )
    assert isinstance(definition, TypeDefinition)

    return_tuple = ExprCast(
        expr=ExprOperator(
            ExprReg(Register.AP),
            "-",
            ExprConst(preprocessor.get_size(definition.cairo_type)),
        ),
        dest_type=TypePointer(definition.cairo_type),
    )

    result = return_tuple
    for member_name in name.split("."):
        result = ExprDot(result, ExprIdentifier(member_name))

    return result


class HorusSubstituteIdentifiers(SubstituteIdentifiers):
    """
    Since storage vars are handled slightly different on the side of Horus
    we need to redefine the behaviour of substitution, which is done by
    this class.
    """

    def __init__(
        self,
        get_identifier_callback: GetIdentifierCallback,
        resolve_type_callback: ResolveTypeCallback = None,
        get_struct_members_callback: GetStructMembersCallback = None,
        identifiers: Optional[IdentifierManager] = None,
    ):
        super().__init__(
            get_identifier_callback, resolve_type_callback, get_struct_members_callback
        )
        self.identifiers = identifiers

    def visit_ExprFuncCall(self, expr: ExprFuncCall):
        try:
            rvalue = expr.rvalue
            _ = self.get_identifier_callback(rvalue.func_ident)

            new_args = []
            for arg in rvalue.arguments.args:
                assert isinstance(arg, ExprAssignment)
                new_expr = self.visit(arg.expr)
                new_args.append(dataclasses.replace(arg, expr=new_expr))

            expr.rvalue.arguments = dataclasses.replace(
                expr.rvalue.arguments, args=new_args
            )

            return expr
        except CairoTypeError:
            return super().visit_ExprFuncCall(expr)


def substitute_identifiers(
    expr: Expression,
    get_identifier_callback: GetIdentifierCallback,
    resolve_type_callback: ResolveTypeCallback = None,
    get_struct_members_callback: GetStructMembersCallback = None,
    identifiers: Optional[IdentifierManager] = None,
) -> Expression:
    """
    Replaces identifiers by other expressions according to the given callback.
    """
    return HorusSubstituteIdentifiers(
        get_identifier_callback=get_identifier_callback,
        resolve_type_callback=resolve_type_callback,
        get_struct_members_callback=get_struct_members_callback,
        identifiers=identifiers,
    ).visit(expr)


def simplify_and_get_type(
    expr: Expression,
    preprocessor: Preprocessor,
    logical_identifiers: Dict[str, CairoType],
    storage_vars: Dict[ScopedName, IdentifierList],
    is_post: bool,
) -> tuple[Expression, CairoType]:
    def get_identifier(expr: ExprIdentifier):
        if is_post:
            definition = get_struct_definition(
                preprocessor.current_scope + "ImplicitArgs", preprocessor.identifiers
            )

            if definition.members.get(expr.name.split(".")[0]) is not None:
                implicit_args_type = TypeStruct(
                    definition.full_name,
                )
                return_def = get_type_definition(
                    preprocessor.current_scope + "Return", preprocessor.identifiers
                )

                implicit_args_struct = ExprCast(
                    expr=ExprOperator(
                        ExprReg(Register.AP),
                        "-",
                        ExprConst(
                            definition.size
                            + preprocessor.get_size(return_def.cairo_type)
                        ),
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

        if isinstance(definition, (ReferenceDefinition, OffsetReferenceDefinition)):
            return definition.eval(
                preprocessor.flow_tracking.reference_manager,
                preprocessor.flow_tracking.data,
            )

        if isinstance(definition, NamespaceDefinition):
            try:
                preprocessor.identifiers.get_by_full_name(
                    search_result.canonical_name + "read"
                )
                preprocessor.identifiers.get_by_full_name(
                    search_result.canonical_name + "write"
                )

                ret_type_def = get_type_definition(
                    search_result.canonical_name + "read" + "Return",
                    preprocessor.identifiers,
                )
                assert isinstance(ret_type_def, TypeDefinition)
                assert isinstance(ret_type_def.cairo_type, TypeTuple)

                if len(ret_type_def.cairo_type.members) != 1:
                    raise CairoTypeError(
                        "Storage maps with return tuple of length higher than 1 are not supported yet",
                        location=expr.location,
                    )

                return expr
            except MissingIdentifierError as e:
                # Failed to find the storage variable stuff.
                raise CairoTypeError(
                    "Function calls are not allowed in assertions",
                    location=expr.location,
                ) from e

        raise CairoTypeError(
            f'Cannot obtain identifier "{expr.name}". Expected a reference but got "{definition.TYPE}"',
            location=expr.location,
            notes=[
                "\033[33mhint: Did you try to reference a local variable in a '@pre' condition?",
                "hint: Local variables cannot be referenced in '@pre' or '@post'.",
                "hint:",
                "hint: Try using an '@assert' within the function body.\033[0m",
            ],
        )

    expr = substitute_identifiers(
        expr,
        get_identifier,
        preprocessor.resolve_type,
        identifiers=preprocessor.identifiers,
    )
    expr, expr_type = HorusTypeChecker(
        preprocessor.accessible_scopes,
        preprocessor.identifiers,
        logical_identifiers,
        storage_vars,
    ).visit(expr)
    expr_type = preprocessor.resolve_type(expr_type)
    expr = ExpressionSimplifier(prime=FIELD_PRIME).visit(expr)

    return (expr, expr_type)


def simplify(
    expr: Expression,
    preprocessor: Preprocessor,
    logical_identifiers: Dict[str, CairoType],
    storage_vars: Dict[ScopedName, IdentifierList],
    is_post: bool,
) -> Expression:
    return simplify_and_get_type(
        expr, preprocessor, logical_identifiers, storage_vars, is_post
    )[0]
