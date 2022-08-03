from __future__ import annotations

from typing import Optional

import z3
from starkware.cairo.lang.compiler.ast.bool_expr import BoolExpr
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
    ExprAssignment,
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
from starkware.cairo.lang.compiler.expression_simplifier import ExpressionSimplifier
from starkware.cairo.lang.compiler.expression_transformer import ExpressionTransformer
from starkware.cairo.lang.compiler.identifier_definition import StructDefinition
from starkware.cairo.lang.compiler.identifier_manager import (
    IdentifierError,
    IdentifierManager,
)
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
from starkware.cairo.lang.compiler.substitute_identifiers import substitute_identifiers
from starkware.cairo.lang.compiler.type_system_visitor import *
from starkware.cairo.lang.compiler.type_system_visitor import simplify_type_system
from starkware.crypto.signature.math_utils import div_mod
from starkware.crypto.signature.signature import FIELD_PRIME

from horus.compiler.code_elements import (
    BoolConst,
    BoolExprCompare,
    BoolFormula,
    BoolNegation,
    BoolOperation,
    ExprLogicalIdentifier,
)
from horus.compiler.type_checker import HorusTypeChecker
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
        return ExprIdentifier(
            name=expr.name, location=self.location_modifier(expr.location)
        )

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
            return (a + b) % self.prime
        elif expr.op == "-":
            return (a - b) % self.prime
        elif expr.op == "*":
            return (a * b) % self.prime
        elif expr.op == "/":
            assert self.z3_transformer is not None, "z3_transformer should not be None"
            inverse_b = self.z3_transformer.add_inverse(b)
            return (a * inverse_b) % self.prime

    def visit_ExprPow(self, expr: ExprPow):
        a = self.visit(expr.a)
        b = self.visit(expr.b)

        if z3.is_int_value(a) and z3.is_int_value(b):
            b_long = b.as_long()
            if b_long < 0:
                a_inverse = div_mod(1, a.as_long(), FIELD_PRIME)
                return z3.IntVal(a_inverse ** (-b_long) % FIELD_PRIME)
            else:
                return z3.IntVal(a.as_long() ** b_long % FIELD_PRIME)

        raise PreprocessorError("Non-constant powers in assertions are not supported.")

    def visit_ExprNeg(self, expr: ExprNeg):
        return (-self.visit(expr.val)) % self.prime

    def visit_ExprParentheses(self, expr: ExprParentheses):
        return self.visit(expr.val)

    def visit_ExprDeref(self, expr: ExprDeref):
        return self.memory(self.visit(expr.addr))

    def visit_ExprSubscript(self, expr: ExprSubscript):
        return ExprSubscript(
            expr=self.visit(expr.expr),
            offset=self.visit(expr.offset),
            location=self.location_modifier(expr.location),
        )

    def visit_ExprDot(self, expr: ExprDot):
        return ExprDot(
            expr=self.visit(expr.expr),
            # Avoid visiting 'member' with an overridden visit_ExprIdentifier, as it is not a
            # proper identifier.
            member=ExpressionTransformer.visit_ExprIdentifier(self, expr.member),
            location=self.location_modifier(expr.location),
        )

    def visit_ExprAddressOf(self, expr: ExprAddressOf):
        inner_expr = self.visit(expr.expr)
        return ExprAddressOf(
            expr=inner_expr, location=self.location_modifier(expr.location)
        )

    def visit_ExprCast(self, expr: ExprCast):
        inner_expr = self.visit(expr.expr)
        return ExprCast(
            expr=inner_expr,
            dest_type=expr.dest_type,
            cast_type=expr.cast_type,
            location=self.location_modifier(expr.location),
        )

    def visit_ArgList(self, arg_list: ArgList):
        return ArgList(
            args=[
                ExprAssignment(
                    identifier=item.identifier,
                    expr=self.visit(item.expr),
                    location=self.location_modifier(item.location),
                )
                for item in arg_list.args
            ],
            notes=arg_list.notes,
            has_trailing_comma=arg_list.has_trailing_comma,
            location=self.location_modifier(arg_list.location),
        )

    def visit_ExprTuple(self, expr: ExprTuple):
        return ExprTuple(
            members=self.visit_ArgList(expr.members),
            location=self.location_modifier(expr.location),
        )

    def visit_RvalueFuncCall(self, rvalue):
        raise PreprocessorError(
            "Usage of function calls in assertions is not allowed",
            location=rvalue.location,
        )

    def visit_ExprFuncCall(self, expr):
        raise PreprocessorError(
            "Usage of function calls in assertions is not allowed",
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
        logical_identifiers: dict[str, CairoType] = {},
        is_post: bool = False,
    ):
        super().__init__(identifiers)
        self.preprocessor = preprocessor
        self.z3_expression_transformer = Z3ExpressionTransformer(identifiers, self)
        self.logical_identifiers = logical_identifiers
        self.inverse_equations: list[z3.BoolRef] = []
        self.is_post = is_post

    def add_inverse(self, z3_expr: z3.ArithRef):
        var = z3.FreshInt()

        self.inverse_equations.append((z3_expr * var) % z3.Int(PRIME_CONST_NAME) == 1)

        return var

    def visit(self, formula: BoolFormula):
        funcname = f"visit_{type(formula).__name__}"
        return getattr(self, funcname)(formula)

    def simplify_and_get_type(self, expr: Expression) -> tuple[Expression, CairoType]:
        def get_identifier(expr: ExprIdentifier):
            if self.is_post:
                definition = get_struct_definition(
                    self.preprocessor.current_scope + "ImplicitArgs", self.identifiers
                )

                if definition.members.get(expr.name.split(".")[0]) is not None:
                    implicit_args_type = TypeStruct(
                        definition.full_name, is_fully_resolved=True
                    )
                    return_def = get_struct_definition(
                        self.preprocessor.current_scope + "Return", self.identifiers
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

            try:
                search_result = self.identifiers.search(
                    self.preprocessor.accessible_scopes, expr.name
                )
                definition = resolve_search_result(search_result, self.identifiers)

                return definition.eval(
                    self.preprocessor.flow_tracking.reference_manager,
                    self.preprocessor.flow_tracking.data,
                )
            except IdentifierError:
                definition = get_struct_definition(
                    self.preprocessor.current_scope + "Return", self.identifiers
                )
                assert isinstance(definition, StructDefinition)
                return_type = TypeStruct(definition.full_name, is_fully_resolved=True)

                return_struct = ExprCast(
                    expr=ExprOperator(
                        ExprReg(Register.AP), "-", ExprConst(definition.size)
                    ),
                    dest_type=TypePointer(return_type),
                )

                result = return_struct
                for member_name in expr.name.split("."):
                    result = ExprDot(result, ExprIdentifier(member_name))

                return result

        return HorusTypeChecker(self.identifiers, self.logical_identifiers).visit(
            substitute_identifiers(expr, get_identifier)
        )

    def simplify(self, expr: Expression) -> Expression:
        return self.simplify_and_get_type(expr)[0]

    def get_member(self, expr: Expression, name: str):
        if isinstance(expr, ExprTuple):
            for member in expr.members.args:
                if member.identifier is not None and member.identifier.name == name:
                    return self.simplify(member.expr)

            raise PreprocessorError(f"No member with the name {name}")
        else:
            return ExprDot(expr, ExprIdentifier(name))

    def get_element_at(self, expr: Expression, ind: int):
        if isinstance(expr, ExprTuple):
            member = expr.members.args[ind]
            return member.expr
        else:
            return ExprSubscript(expr, ExprConst(ind))

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
                    get_smt_expression(self.simplify(member_a), self.identifiers)
                    == get_smt_expression(self.simplify(member_b), self.identifiers),
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
            struct_name=type.resolved_scope, identifier_manager=self.identifiers
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
                    get_smt_expression(self.simplify(member_a), self.identifiers)
                    == get_smt_expression(self.simplify(member_b), self.identifiers),
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

    def visit_BoolExpr(self, bool_expr: BoolExpr):
        a, a_type = self.simplify_and_get_type(bool_expr.a)
        b, b_type = self.simplify_and_get_type(bool_expr.b)

        simplifier = ExpressionSimplifier(prime=FIELD_PRIME)
        a = simplifier.visit(a)
        b = simplifier.visit(b)

        assert a_type == b_type, "Types of lhs and rhs must coincide"

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
        a, a_type = self.simplify_and_get_type(formula.a)
        b, b_type = self.simplify_and_get_type(formula.b)

        assert a_type == b_type, "Types of lhs and rhs must coincide"

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
