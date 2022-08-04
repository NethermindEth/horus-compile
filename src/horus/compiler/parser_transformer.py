from __future__ import annotations

from typing import Optional

import lark
from starkware.cairo.lang.compiler.ast.expr import *
from starkware.cairo.lang.compiler.ast.expr import ExprIdentifier
from starkware.cairo.lang.compiler.error_handling import InputFile
from starkware.cairo.lang.compiler.parser_transformer import (
    ParserContext,
    ParserError,
    ParserTransformer,
)

import horus.compiler.parser
from horus.compiler.code_elements import (
    BoolConst,
    BoolExprAtom,
    BoolExprCompare,
    BoolNegation,
    BoolOperation,
    CheckedCodeElement,
    CodeElementCheck,
    CodeElementLogicalVariableDeclaration,
    ExprLogicalIdentifier,
)


class HorusTransformer(ParserTransformer):
    """
    Transforms lark trees generated by extended
    grammar `Horus.ebnf`.
    """

    def __init__(
        self,
        input_file: InputFile,
        parser_context: Optional[ParserContext],
        is_parsing_check: bool = False,
    ):
        self.is_parsing_check = is_parsing_check
        super().__init__(input_file, parser_context)

    @lark.v_args(meta=True)
    def commented_code_element(self, value, meta):
        comment: Optional[str] = value[1][1:] if len(value) == 2 else None

        if comment is not None:
            possible_annotation = comment.strip()

            for annotation in [
                "@pre",
                "@post",
                "@assert",
                "@require",
                "@invariant",
                "@declare",
            ]:
                if possible_annotation.startswith(annotation):
                    check = horus.compiler.parser.parse(
                        filename=self.input_file.filename,
                        code=possible_annotation,
                        code_type="annotation",
                        expected_type=(
                            CodeElementCheck,
                            CodeElementLogicalVariableDeclaration,
                        ),
                        parser_context=self.parser_context,
                    )
                    code_elem = super().commented_code_element(value[:1], meta)
                    code_elem.code_elm = CheckedCodeElement(
                        check, code_elm=code_elem.code_elm, location=code_elem.location
                    )
                    return code_elem

        return super().commented_code_element(value, meta)

    @lark.v_args(meta=True)
    def logical_identifier(self, value, meta):
        identifier_name = ".".join(x.value for x in value)
        if value[0].value == "$Return":
            return ExprIdentifier(name=identifier_name, location=self.meta2loc(meta))
        else:
            return ExprLogicalIdentifier(
                name=identifier_name, location=self.meta2loc(meta)
            )

    @lark.v_args(meta=True)
    def logical_identifier_def(self, value, meta):
        if value[0].value == "$Return":
            raise ParserError(
                f"'$Return' is a reserved name.", location=self.meta2loc(meta)
            )
        return ExprLogicalIdentifier(name=value[0].value, location=self.meta2loc(meta))

    def atom_logical_identifier(self, value):
        return value[0]

    @lark.v_args(inline=True)
    def bool_formula_impl(self, lhs, rhs):
        return BoolOperation(lhs, rhs, "->")

    @lark.v_args(inline=True)
    def bool_formula_or(self, lhs, rhs):
        return BoolOperation(lhs, rhs, "|")

    @lark.v_args(inline=True)
    def bool_formula_and(self, lhs, rhs):
        return BoolOperation(lhs, rhs, "&")

    @lark.v_args(inline=True)
    def bool_unary_neg(self, formula):
        return BoolNegation(formula)

    @lark.v_args(inline=True)
    def bool_expr_true(self):
        return BoolConst(True)

    @lark.v_args(inline=True)
    def bool_expr_false(self):
        return BoolConst(False)

    @lark.v_args(inline=True)
    def bool_atom(self, expr):
        return BoolExprAtom(expr)

    @lark.v_args(inline=True)
    def bool_expr_le(self, lhs, rhs):
        return BoolExprCompare(lhs, rhs, "<=")

    @lark.v_args(inline=True)
    def bool_expr_lt(self, lhs, rhs):
        return BoolExprCompare(lhs, rhs, "<")

    @lark.v_args(inline=True)
    def bool_expr_ge(self, lhs, rhs):
        return BoolExprCompare(lhs, rhs, ">=")

    @lark.v_args(inline=True)
    def bool_expr_gt(self, lhs, rhs):
        return BoolExprCompare(lhs, rhs, ">")

    @lark.v_args(inline=True)
    def bool_expr_parentheses(self, formula):
        return formula

    @lark.v_args(inline=True)
    def precond_annotation(self, expr):
        return CodeElementCheck(CodeElementCheck.CheckKind.PRE_COND, expr)

    @lark.v_args(inline=True)
    def postcond_annotation(self, expr):
        return CodeElementCheck(CodeElementCheck.CheckKind.POST_COND, expr)

    @lark.v_args(inline=True)
    def assert_annotation(self, expr):
        return CodeElementCheck(CodeElementCheck.CheckKind.ASSERT, expr)

    @lark.v_args(inline=True)
    def require_annotation(self, expr):
        return CodeElementCheck(CodeElementCheck.CheckKind.REQUIRE, expr)

    @lark.v_args(inline=True)
    def invariant_annotation(self, expr):
        return CodeElementCheck(CodeElementCheck.CheckKind.INVARIANT, expr)

    @lark.v_args(inline=True)
    def declare_annotation(self, identifier, type):
        return CodeElementLogicalVariableDeclaration(identifier.name, type)

    def transform(self, tree: lark.Tree):
        # The nodes of the tree imported from cairo.ebnf appear with
        # prefix starkware__cairo__lang__compiler__cairo__ which we remove here.
        for node in tree.iter_subtrees():
            node.data = node.data.replace(
                "starkware__cairo__lang__compiler__cairo__", ""
            )

        return super().transform(tree)
