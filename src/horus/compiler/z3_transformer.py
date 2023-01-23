from __future__ import annotations

from typing import Dict, Optional

import z3
from starkware.cairo.lang.compiler.ast.arguments import IdentifierList
from starkware.cairo.lang.compiler.ast.bool_expr import BoolEqExpr
from starkware.cairo.lang.compiler.ast.cairo_types import (
    CairoType,
    TypeFelt,
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
from starkware.cairo.lang.compiler.ast.expr_func_call import ExprFuncCall
from starkware.cairo.lang.compiler.expression_simplifier import ExpressionSimplifier
from starkware.cairo.lang.compiler.identifier_definition import (
    FunctionDefinition,
    NamespaceDefinition,
    StructDefinition,
)
from starkware.cairo.lang.compiler.identifier_manager import IdentifierManager
from starkware.cairo.lang.compiler.identifier_utils import get_struct_definition
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
from starkware.cairo.lang.compiler.type_system_visitor import simplify_type_system

from horus.compiler.allowed_syscalls import allowed_syscalls
from horus.compiler.code_elements import (
    BoolConst,
    BoolExprCompare,
    BoolFormula,
    BoolNegation,
    BoolOperation,
    ExprLogicalIdentifier,
)
from horus.compiler.type_checker import simplify, simplify_and_get_type
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

                args = [self.visit(arg.expr) for arg in expr.expr.members.args]

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

            args = [self.visit(arg.expr) for arg in expr.rvalue.arguments.args]

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


def get_smt_expression(expr: Expression, identifiers: IdentifierManager):
    return Z3ExpressionTransformer(identifiers).visit(expr)


class Z3Transformer(IdentifierAwareVisitor):
    def __init__(
        self,
        identifiers: IdentifierManager,
        preprocessor: Preprocessor,
        logical_identifiers: Dict[str, CairoType],
        storage_vars: Dict[ScopedName, IdentifierList],
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

    def get_element_at(self, expr: Expression, ind: int):
        if isinstance(expr, ExprTuple):
            member = expr.members.args[ind]
            return member.expr
        else:
            return ExprSubscript(expr, ExprConst(ind))

    def get_member(self, expr: Expression, name: str):
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
        else:
            return ExprDot(expr, ExprIdentifier(name))

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
                    get_smt_expression(
                        simplify(
                            member_a,
                            self.preprocessor,
                            self.logical_identifiers,
                            self.storage_vars,
                            self.is_post,
                        ),
                        self.identifiers,
                    )
                    == get_smt_expression(
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
                    get_smt_expression(
                        simplify(
                            member_a,
                            self.preprocessor,
                            self.logical_identifiers,
                            self.storage_vars,
                            self.is_post,
                        ),
                        self.identifiers,
                    )
                    == get_smt_expression(
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
