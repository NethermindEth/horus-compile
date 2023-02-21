from __future__ import annotations

from typing import Optional

import z3
from starkware.cairo.lang.compiler.ast.bool_expr import BoolEqExpr
from starkware.cairo.lang.compiler.ast.cairo_types import (
    CairoType,
    TypeFelt,
    TypeIdentifier,
    TypePointer,
    TypeStruct,
    TypeTuple,
)
from starkware.cairo.lang.compiler.ast.expr import (
    ArgList,
    ExprAddressOf,
    ExprCast,
    ExprConst,
    ExprDeref,
    ExprDot,
    Expression,
    ExprFutureLabel,
    ExprHint,
    ExprIdentifier,
    ExprNeg,
    ExprNewOperator,
    ExprOperator,
    ExprParentheses,
    ExprPow,
    ExprReg,
    ExprSubscript,
    ExprTuple,
)
from starkware.cairo.lang.compiler.ast.expr_func_call import (
    ExprFuncCall,
    RvalueFuncCall,
)
from starkware.cairo.lang.compiler.error_handling import Location
from starkware.cairo.lang.compiler.identifier_definition import (
    FunctionDefinition,
    MemberDefinition,
    NamespaceDefinition,
    StructDefinition,
    TypeDefinition,
)
from starkware.cairo.lang.compiler.identifier_manager import IdentifierManager
from starkware.cairo.lang.compiler.identifier_utils import (
    get_struct_definition,
    get_struct_member_offsets,
)
from starkware.cairo.lang.compiler.instruction import Register
from starkware.cairo.lang.compiler.preprocessor.identifier_aware_visitor import (
    IdentifierAwareVisitor,
)
from starkware.cairo.lang.compiler.preprocessor.preprocessor import Preprocessor
from starkware.cairo.lang.compiler.preprocessor.preprocessor_error import (
    PreprocessorError,
)
from starkware.cairo.lang.compiler.resolve_search_result import resolve_search_result
from starkware.cairo.lang.compiler.scoped_name import ScopedName
from starkware.cairo.lang.compiler.type_casts import CairoTypeError
from starkware.cairo.lang.compiler.type_system_visitor import *

from horus.compiler.allowed_syscalls import allowed_syscalls
from horus.compiler.code_elements import (
    BoolConst,
    BoolExprAtom,
    BoolExprCompare,
    BoolFormula,
    BoolNegation,
    BoolOperation,
    ExprLogicalIdentifier,
)
from horus.compiler.storage_info import StorageVarInfo
from horus.compiler.type_checker import (
    simplify,
    simplify_and_get_type,
    try_get_storage_type,
)
from horus.compiler.var_names import *
from horus.utils import z3And, z3True


class Z3ExpressionTransformer(IdentifierAwareVisitor):
    def __init__(
        self,
        identifiers: Optional[IdentifierManager] = None,
        z3_transformer: Optional[Z3Transformer] = None,
    ):
        self.prime = z3.Int(PRIME_CONST_NAME)
        self.memory = z3.Function(MEMORY_MAP_NAME, z3.IntSort(), z3.IntSort())
        self.z3_transformer = z3_transformer
        if z3_transformer is not None:
            self.storage_vars = z3_transformer.storage_vars
        super().__init__(identifiers)

    def visit_ExprConst(self, expr: ExprConst):
        return z3.IntVal(expr.val)

    def visit_ExprHint(self, expr: ExprHint):
        raise PreprocessorError(
            "Usage of hints in assertions is not allowed", location=expr.location
        )

    def visit_ExprLogicalIdentifier(self, expr: ExprLogicalIdentifier):
        return z3.Int(expr.name)

    def visit_ExprIdentifier(self, expr: ExprIdentifier):
        return ExprIdentifier(name=expr.name, location=expr.location)

    def visit_ExprFutureLabel(self, expr: ExprFutureLabel):
        raise PreprocessorError(
            "Usage of labels in assertions is not allowed", location=expr.location
        )

    def visit_ExprReg(self, expr: ExprReg):
        if expr.reg == Register.AP:
            return z3.Int(AP_VAR_NAME)
        else:
            return z3.Int(FP_VAR_NAME)

    def visit_ExprOperator(self, expr: ExprOperator):
        a = self.visit(expr.a)
        b = self.visit(expr.b)

        if expr.op == "+":
            return a + b
        elif expr.op == "-":
            return a - b
        elif expr.op == "*":
            return a * b
        elif expr.op == "/":
            return a / b

    def visit_ExprPow(self, expr: ExprPow):
        raise PreprocessorError("Non-constant powers in assertions are not supported.")

    def visit_ExprNeg(self, expr: ExprNeg):
        return -self.visit(expr.val)

    def visit_ExprParentheses(self, expr: ExprParentheses):
        return self.visit(expr.val)

    def visit_ExprDeref(self, expr: ExprDeref):
        return self.memory(self.visit(expr.addr))

    def visit_ExprSubscript(self, expr: ExprSubscript):
        raise PreprocessorError(
            "This was supposed to be unreachable.",
            location=expr.location,
        )

    def visit_ExprDot(self, expr: ExprDot):
        raise PreprocessorError(
            "This was supposed to be unreachable.",
            location=expr.location,
        )

    def visit_ExprAddressOf(self, expr: ExprAddressOf):
        raise PreprocessorError(
            "This was supposed to be unreachable.",
            location=expr.location,
        )

    def get_deep_member_offset(
        self, member: ScopedName, typ: CairoType, location: Optional[Location] = None
    ) -> int:
        offset = 0
        for mem_name in member.path:
            if isinstance(typ, TypeIdentifier):
                assert self.z3_transformer is not None
                self.z3_transformer.preprocessor.accessible_scopes.append(ScopedName())
                typ = self.z3_transformer.preprocessor.resolve_type(typ)
                self.z3_transformer.preprocessor.accessible_scopes.pop()

            if isinstance(typ, TypeTuple):
                mem_with_name = [mem for mem in typ.members if mem.name == mem_name]

                if not mem_with_name:
                    raise CairoTypeError(
                        f"There is no member with name {mem_name} in type {typ.format()}",
                        location=location,
                    )

                ind = typ.members.index(mem_with_name[0])
                assert self.z3_transformer is not None
                offset += sum(
                    map(
                        lambda m: self.z3_transformer.preprocessor.get_size(m.typ),  # type: ignore
                        typ.members[0:ind],
                    )
                )
                typ = mem_with_name[0].typ
            elif isinstance(typ, TypeStruct):
                assert self.z3_transformer is not None
                struct_def = get_struct_definition(
                    typ.scope, self.z3_transformer.preprocessor.identifiers
                )
                offset += struct_def.members[mem_name].offset
                typ = struct_def.members[mem_name].cairo_type
            elif isinstance(typ, TypeFelt):
                break

        return offset

    def visit_RvalueFuncCall(self, expr: RvalueFuncCall):
        name = expr.func_ident.name.split("#")[0]

        storage_var = z3.Function(
            name,
            z3.IntSort(),
            *[z3.IntSort() for _ in expr.arguments.args],
            z3.IntSort(),
        )

        assert self.z3_transformer is not None

        typ = try_get_storage_type(
            ScopedName.from_string(name),
            self.z3_transformer.preprocessor,
            self.z3_transformer.logical_identifiers,
            self.z3_transformer.storage_vars,
            expr.location,
        )

        assert isinstance(typ, TypeTuple)

        offset = self.get_deep_member_offset(
            ScopedName.from_string(expr.func_ident.name.split("#")[1]),
            typ,
            expr.location,
        )

        args = [
            self.visit(
                simplify(
                    arg.expr,
                    self.z3_transformer.preprocessor,
                    self.z3_transformer.logical_identifiers,
                    self.z3_transformer.storage_vars,
                    is_post=self.z3_transformer.is_post,
                )
            )
            for arg in expr.arguments.args
        ]
        return storage_var(offset, *args)

    def visit_ExprCast(self, expr: ExprCast):
        if isinstance(expr.dest_type, TypeStruct):
            assert self.identifiers is not None
            assert self.z3_transformer is not None
            search_result = self.identifiers.search(
                self.z3_transformer.preprocessor.accessible_scopes, expr.dest_type.scope
            )
            definition = resolve_search_result(search_result, self.identifiers)

            if isinstance(definition, NamespaceDefinition):
                if not search_result.canonical_name in self.z3_transformer.storage_vars:
                    raise PreprocessorError(
                        f"{expr.dest_type.scope} is not a storage var.",
                        location=expr.location,
                    )

                arg_struct_def = get_struct_definition(
                    search_result.canonical_name + "read" + "Args", self.identifiers
                )
                assert isinstance(arg_struct_def, StructDefinition)

                storage_var = z3.Function(
                    str(search_result.canonical_name),
                    *[z3.IntSort() for _ in arg_struct_def.members.values()],
                    z3.IntSort(),
                )

                assert isinstance(expr.expr, ExprTuple)

                args = [
                    self.visit(
                        simplify(
                            arg.expr,
                            self.z3_transformer.preprocessor,
                            self.z3_transformer.logical_identifiers,
                            self.z3_transformer.storage_vars,
                            is_post=self.z3_transformer.is_post,
                        )
                    )
                    for arg in expr.expr.members.args
                ]

                return storage_var(*args)
            elif isinstance(definition, FunctionDefinition):
                if search_result.canonical_name in allowed_syscalls:
                    return z3.Int(expr.dest_type.scope.path[-1].replace("get_", "%"))

        inner_expr = self.visit(expr.expr)
        return inner_expr

    def visit_ExprFuncCall(self, expr: ExprFuncCall):
        """
        If a function call appears in an assertion it is expected to be a storage variable
        reference. Otherwise an exception is thrown.
        """
        assert self.z3_transformer is not None
        search_result = self.identifiers.search(
            self.z3_transformer.preprocessor.accessible_scopes,
            ScopedName.from_string(expr.rvalue.func_ident.name),
        )
        definition = resolve_search_result(search_result, self.identifiers)
        if search_result.canonical_name in allowed_syscalls:
            return z3.Int(search_result.canonical_name.path[-1].replace("get_", "%"))

        if isinstance(definition, NamespaceDefinition):
            if not search_result.canonical_name in self.z3_transformer.storage_vars:
                raise PreprocessorError(
                    f"{expr.rvalue.func_ident.name} is not a storage var.",
                    location=expr.location,
                )

            arg_struct_def = get_struct_definition(
                search_result.canonical_name + "read" + "Args", self.identifiers
            )
            assert isinstance(arg_struct_def, StructDefinition)

            storage_var = z3.Function(
                str(search_result.canonical_name),
                *[z3.IntSort() for _ in arg_struct_def.members.values()],
                z3.IntSort(),
            )

            args = [
                self.visit(
                    simplify(
                        arg.expr,
                        self.z3_transformer.preprocessor,
                        self.z3_transformer.logical_identifiers,
                        self.z3_transformer.storage_vars,
                        is_post=self.z3_transformer.is_post,
                    )
                )
                for arg in expr.rvalue.arguments.args
            ]

            return storage_var(*args)

        raise PreprocessorError(
            f"Function {search_result.canonical_name} cannot be used in assertions.",
            location=expr.location,
        )

    def visit_ArgList(self, arg_list: ArgList):
        raise PreprocessorError(
            "This was supposed to be unreachable.",
            location=arg_list.location,
        )

    def visit_ExprTuple(self, expr: ExprTuple):
        raise PreprocessorError(
            "This was supposed to be unreachable.",
            location=expr.location,
        )

    def visit_ExprNewOperator(self, expr: ExprNewOperator):
        raise PreprocessorError(
            "Usage of the new operator in assertions is not allowed",
            location=expr.location,
        )


class Z3Transformer(IdentifierAwareVisitor):
    def __init__(
        self,
        identifiers: IdentifierManager,
        preprocessor: Preprocessor,
        logical_identifiers: dict[str, CairoType],
        storage_vars: dict[ScopedName, StorageVarInfo],
        is_post: bool = False,
    ):
        super().__init__(identifiers)
        self.preprocessor = preprocessor
        self.logical_identifiers = logical_identifiers
        self.is_post = is_post
        self.storage_vars = storage_vars
        self.z3_expression_transformer = Z3ExpressionTransformer(identifiers, self)

    def visit(self, formula: BoolFormula):
        funcname = f"visit_{type(formula).__name__}"
        return getattr(self, funcname)(formula)

    def get_smt_expression(self, expr: Expression, identifiers: IdentifierManager):
        return self.z3_expression_transformer.visit(expr)

    def get_element_at(self, expr: Expression, ind: int):
        if isinstance(expr, ExprTuple):
            member = expr.members.args[ind]
            return member.expr
        elif isinstance(expr, ExprDeref):
            return ExprDeref(
                ExprOperator(expr.addr, "+", ExprConst(ind)), location=expr.location
            )
        else:
            return ExprSubscript(expr, ExprConst(ind))

    def get_member(
        self, expr: Expression, name: str, mem_def: Optional[MemberDefinition] = None
    ):
        if isinstance(expr, ExprTuple):
            for member in expr.members.args:
                if member.identifier is not None and member.identifier.name == name:
                    return simplify(
                        member.expr,
                        self.preprocessor,
                        self.logical_identifiers,
                        self.storage_vars,
                        self.is_post,
                    )

            raise PreprocessorError(f"No member with the name {name}")

        if isinstance(expr, ExprDeref):
            assert (
                not mem_def is None
            ), "Member definition 'mem_def' should not be None."
            return ExprDeref(
                addr=ExprOperator(expr.addr, "+", ExprConst(mem_def.offset)),
                location=expr.location,
            )

        return ExprDot(expr, ExprIdentifier(name))

    def flatten_typed_expr(
        self,
        a: Expression,
        a_type: CairoType,
        result: Optional[list[Expression]] = None,
    ):
        if result is None:
            result = []
        if isinstance(a_type, TypeStruct):
            definition = get_struct_definition(
                struct_name=a_type.scope, identifier_manager=self.identifiers
            )
            assert isinstance(
                definition, StructDefinition
            ), "TypeStruct with the name {a_type.scope} must yield a StructDefinition.\n Got {definition.TYPE()}"
            for member_name, member_definition in definition.members.items():
                member_a = self.get_member(a, member_name, member_definition)
                if isinstance(member_definition.cairo_type, (TypeFelt, TypePointer)):
                    result.append(
                        z3.simplify(
                            self.get_smt_expression(
                                simplify(
                                    member_a,
                                    self.preprocessor,
                                    self.logical_identifiers,
                                    self.storage_vars,
                                    self.is_post,
                                ),
                                self.identifiers,
                            )
                        )
                    )
                elif isinstance(member_definition.cairo_type, TypeIdentifier):
                    res = self.identifiers.get(
                        member_definition.cairo_type.name
                    ).identifier_definition
                    if isinstance(res, StructDefinition):
                        self.flatten_typed_expr(
                            member_a,
                            TypeStruct(res.full_name, location=res.location),
                            result,
                        )
                    elif isinstance(res, TypeDefinition):
                        self.flatten_typed_expr(member_a, res.cairo_type, result)
                elif isinstance(member_definition.cairo_type, TypeStruct):
                    self.flatten_typed_expr(
                        member_a, member_definition.cairo_type, result
                    )
                elif isinstance(member_definition.cairo_type, TypeTuple):
                    self.flatten_typed_expr(
                        member_a, member_definition.cairo_type, result
                    )
                else:
                    raise NotImplementedError(
                        f"Unsupported type {member_definition.cairo_type.format()}"
                    )
        elif isinstance(a_type, TypeTuple):
            for i, member in enumerate(a_type.members):
                if member.name is not None:
                    member_a = self.get_member(
                        a,
                        member.name,
                    )
                else:
                    member_a = self.get_element_at(a, i)

                if isinstance(member.typ, (TypeFelt, TypePointer)):
                    result.append(
                        z3.simplify(
                            self.get_smt_expression(
                                simplify(
                                    member_a,
                                    self.preprocessor,
                                    self.logical_identifiers,
                                    self.storage_vars,
                                    self.is_post,
                                ),
                                self.identifiers,
                            )
                        )
                    )
                elif isinstance(member.typ, TypeIdentifier):
                    res = self.identifiers.get(member.typ.name).identifier_definition
                    if isinstance(res, StructDefinition):
                        self.flatten_typed_expr(
                            member_a,
                            TypeStruct(res.full_name, location=res.location),
                            result,
                        )
                    elif isinstance(res, TypeDefinition):
                        self.flatten_typed_expr(member_a, res.cairo_type, result)
                elif isinstance(member.typ, TypeStruct):
                    self.flatten_typed_expr(member_a, member.typ, result)
                elif isinstance(member.typ, TypeTuple):
                    self.flatten_typed_expr(member_a, member.typ, result)
        else:
            a = self.z3_expression_transformer.visit(a)
            result.append(a)

        return result

    def flatten_expr(self, expr: Expression):
        a, _ = self.flatten_expr_and_get_type(expr)

        return a

    def flatten_expr_and_get_type(self, expr: Expression):
        a, a_type = simplify_and_get_type(
            expr,
            self.preprocessor,
            self.logical_identifiers,
            self.storage_vars,
            self.is_post,
        )

        return self.flatten_typed_expr(a, a_type, result=[]), a_type

    def make_tuple_eq(self, a: Expression, b: Expression, type: TypeTuple):
        result = z3True
        for i, member in enumerate(type.members):
            if member.name is not None:
                member_a = self.get_member(a, member.name)
                member_b = self.get_member(b, member.name)
            else:
                member_a = self.get_element_at(a, i)
                member_b = self.get_element_at(b, i)

            if isinstance(member.typ, (TypeFelt, TypePointer)):
                result = z3And(
                    result,
                    self.get_smt_expression(
                        simplify(
                            member_a,
                            self.preprocessor,
                            self.logical_identifiers,
                            self.storage_vars,
                            self.is_post,
                        ),
                        self.identifiers,
                    )
                    == self.get_smt_expression(
                        simplify(
                            member_b,
                            self.preprocessor,
                            self.logical_identifiers,
                            self.storage_vars,
                            self.is_post,
                        ),
                        self.identifiers,
                    ),
                )
            elif isinstance(member.typ, TypeStruct):
                result = z3And(
                    result, self.make_struct_eq(member_a, member_b, member.typ)
                )
            elif isinstance(member.typ, TypeTuple):
                result = z3And(
                    result, self.make_tuple_eq(member_a, member_b, member.typ)
                )

        return result

    def make_struct_eq(
        self, a: Expression, b: Expression, type: TypeStruct
    ) -> z3.BoolRef:
        definition = get_struct_definition(
            struct_name=type.scope, identifier_manager=self.identifiers
        )
        assert isinstance(
            definition, StructDefinition
        ), "TypeStruct must contain StructDefinition"
        result = z3True
        for member_name, member_definition in definition.members.items():
            member_a = self.get_member(a, member_name)
            member_b = self.get_member(b, member_name)
            if isinstance(member_definition.cairo_type, (TypeFelt, TypePointer)):
                result = z3And(
                    result,
                    self.get_smt_expression(
                        simplify(
                            member_a,
                            self.preprocessor,
                            self.logical_identifiers,
                            self.storage_vars,
                            self.is_post,
                        ),
                        self.identifiers,
                    )
                    == self.get_smt_expression(
                        simplify(
                            member_b,
                            self.preprocessor,
                            self.logical_identifiers,
                            self.storage_vars,
                            self.is_post,
                        ),
                        self.identifiers,
                    ),
                )
            elif isinstance(member_definition.cairo_type, TypeStruct):
                result = z3And(
                    result,
                    self.make_struct_eq(
                        member_a, member_b, member_definition.cairo_type
                    ),
                )
            elif isinstance(member_definition.cairo_type, TypeTuple):
                result = z3And(
                    result,
                    self.make_tuple_eq(
                        member_a, member_b, member_definition.cairo_type
                    ),
                )
            else:
                raise NotImplementedError("test")

        return result

    def visit_BoolExprAtom(self, bool_expr_atom: BoolExprAtom):
        return self.visit_BoolEqExpr(bool_expr_atom.bool_expr)

    def visit_BoolEqExpr(self, bool_expr: BoolEqExpr):
        a, a_type = simplify_and_get_type(
            bool_expr.a,
            self.preprocessor,
            self.logical_identifiers,
            self.storage_vars,
            self.is_post,
        )
        b, b_type = simplify_and_get_type(
            bool_expr.b,
            self.preprocessor,
            self.logical_identifiers,
            self.storage_vars,
            self.is_post,
        )

        if a_type != b_type:
            raise CairoTypeError(
                f"Types of lhs and rhs must coincide. Got {a_type.format()} and {b_type.format()}",
                bool_expr.location,
            )

        if isinstance(a_type, TypeStruct):
            result = self.make_struct_eq(bool_expr.a, bool_expr.b, a_type)
        elif isinstance(a_type, TypeTuple):
            result = self.make_tuple_eq(bool_expr.a, bool_expr.b, a_type)
        else:
            a = self.z3_expression_transformer.visit(a)
            b = self.z3_expression_transformer.visit(b)
            result = a == b

        if bool_expr.eq:
            return result
        else:
            return z3.Not(result)

    def visit_BoolExprCompare(self, formula: BoolExprCompare):
        a, a_type = simplify_and_get_type(
            formula.a,
            self.preprocessor,
            self.logical_identifiers,
            self.storage_vars,
            self.is_post,
        )
        b, b_type = simplify_and_get_type(
            formula.b,
            self.preprocessor,
            self.logical_identifiers,
            self.storage_vars,
            self.is_post,
        )

        if a_type != b_type:
            raise CairoTypeError(
                f"Types of lhs and rhs must coincide. Got {a_type.format()} and {b_type.format()}",
                formula.location,
            )

        if isinstance(a_type, (TypeFelt, TypePointer)):
            a = self.z3_expression_transformer.visit(a)
            b = self.z3_expression_transformer.visit(b)

            if formula.comp == "<=":
                return a <= b
            elif formula.comp == "<":
                return a < b
            elif formula.comp == ">=":
                return a >= b
            elif formula.comp == ">":
                return a > b
        else:
            raise CairoTypeError(
                f"Cannot compare values of type {a_type.format()}",
                location=formula.location,
            )

    def visit_BoolConst(self, formula: BoolConst):
        return z3.BoolVal(formula.const)

    def visit_BoolOperation(self, formula: BoolOperation):
        a = self.visit(formula.a)
        b = self.visit(formula.b)

        if formula.op == "&":
            return z3And(a, b)
        elif formula.op == "|":
            return z3.Or(a, b)
        elif formula.op == "->":
            return z3.Implies(a, b)
        else:
            raise PreprocessorError(f"unknown logical operation {formula.op}")

    def visit_BoolNegation(self, formula: BoolNegation):
        return z3.Not(self.visit(formula.operand))
