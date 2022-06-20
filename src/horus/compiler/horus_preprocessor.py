from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence

import z3
from starkware.cairo.lang.compiler.ast.code_elements import (
    CodeBlock,
    CodeElement,
    CodeElementEmptyLine,
    CodeElementFunction,
    CodeElementIf,
    CodeElementLabel,
    CodeElementWith,
    CodeElementWithAttr,
    CommentedCodeElement,
)
from starkware.cairo.lang.compiler.ast.formatting_utils import LocationField
from starkware.cairo.lang.compiler.ast.instructions import RetInstruction
from starkware.cairo.lang.compiler.ast.node import AstNode
from starkware.cairo.lang.compiler.error_handling import Location
from starkware.starknet.compiler.starknet_preprocessor import (
    StarknetPreprocessedProgram,
    StarknetPreprocessor,
)

from horus.compiler.check_parser import *
from horus.compiler.horus_definition import HorusChecks
from horus.compiler.z3_transformer import *


@dataclass
class CheckedCodeElement(CodeElement):
    raw_checks: list[str]
    code_elm: CodeElement
    location: Optional[Location] = LocationField

    def format(self, allowed_line_length):
        return f"{self.raw_check}\n{self.code_elm.format(allowed_line_length)}"

    def get_children(self) -> Sequence[Optional[AstNode]]:
        return [self.code_elm]


@dataclass
class HorusProgram(StarknetPreprocessedProgram):
    checks: HorusChecks
    ret_map: dict[int, str]


class HorusPreprocessor(StarknetPreprocessor):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.checks: HorusChecks = HorusChecks()
        self.ret_map: dict[int, str] = {}

        # This is used to defer pre/postcondition unfolding
        # until the visitor steps into the body of the function
        # when the preprocessor stumbles upon a function.
        self.current_checks = None
        self.current_function: Optional[CheckedCodeElement] = None

    def get_program(self) -> HorusProgram:
        starknet_program = super().get_program()
        return HorusProgram(
            **starknet_program.__dict__, checks=self.checks, ret_map=self.ret_map
        )

    def visit_CodeBlock(self, code_block: CodeBlock):
        self.scan_checks(code_block)
        return super().visit_CodeBlock(code_block)

    def scan_checks(self, code_block: CodeBlock):
        """
        Recursively traverses the codeblock and creates CodeElementCheck
        after every comment with a check.

        Parameters:
        -----------
        code_block: CodeBlock
            The code block to be traversed.
        scope: ScopedName
            The current scope.
        """

        def uncomment(
            commented_code_elements: list[CommentedCodeElement],
        ) -> list[CodeElement]:
            return [
                commented_code_element.code_elm
                for commented_code_element in commented_code_elements
            ]

        for i, commented_code_element in enumerate(code_block.code_elements):
            if commented_code_element.comment is not None:
                comment = commented_code_element.comment.strip()
                if comment.startswith("@"):
                    res = self.get_next_CodeElement(
                        enumerate(uncomment(code_block.code_elements[i + 1 :]))
                    )
                    commented_code_element.comment = None
                    if res is None:
                        code_block.code_elements.append(
                            CommentedCodeElement(
                                code_elm=CheckedCodeElement(
                                    raw_checks=[comment],
                                    code_elm=CodeElementEmptyLine(),
                                    location=commented_code_element.location,
                                ),
                                comment=None,
                                location=commented_code_element.location,
                            )
                        )
                    else:
                        j, code_elem = res
                        prev_comment = code_block.code_elements.pop(i + 1 + j).comment
                        if isinstance(code_elem, CheckedCodeElement):
                            code_elem.raw_checks.append(comment)
                            code_block.code_elements.insert(
                                i + 1 + j,
                                CommentedCodeElement(
                                    code_elm=code_elem,
                                    comment=prev_comment,
                                    location=commented_code_element.location,
                                ),
                            )
                        else:
                            code_block.code_elements.insert(
                                i + 1 + j,
                                CommentedCodeElement(
                                    code_elm=CheckedCodeElement(
                                        raw_checks=[comment],
                                        code_elm=code_elem,
                                        location=commented_code_element.location,
                                    ),
                                    comment=prev_comment,
                                    location=commented_code_element.location,
                                ),
                            )

            potential_block_elem = commented_code_element.code_elm
            if isinstance(potential_block_elem, CheckedCodeElement):
                potential_block_elem = potential_block_elem.code_elm

            if isinstance(
                potential_block_elem,
                (CodeElementFunction, CodeElementWith, CodeElementWithAttr),
            ):
                self.scan_checks(potential_block_elem.code_block)
            elif isinstance(potential_block_elem, CodeElementIf):
                self.scan_checks(potential_block_elem.main_code_block)
                if potential_block_elem.else_code_block is not None:
                    self.scan_checks(potential_block_elem.else_code_block)

    def compile_checks(self, checked_elm: CheckedCodeElement):
        def append_check(
            check_dict: dict[Any, z3.BoolRef], key: Any, check: z3.BoolRef
        ):
            try:
                current_check_bool_ref = check_dict[key]
                check_dict[key] = z3.And(current_check_bool_ref, check)
            except KeyError:
                check_dict[key] = check

        raw_checks = checked_elm.raw_checks
        elm = checked_elm.code_elm

        variables = {}

        if isinstance(checked_elm.code_elm, CodeElementFunction):
            are_variables_allowed = True
        else:
            are_variables_allowed = False

        for check in raw_checks:
            parsed_check = self.parse_check(check)

            if isinstance(parsed_check, LogicalVariableDeclaration):
                if are_variables_allowed:
                    variables[parsed_check.name] = parsed_check.type
                else:
                    raise PreprocessorError(
                        "@declare annotation is not allowed here", checked_elm.location
                    )
            else:
                if parsed_check.kind == CheckKind.ASSERT:
                    append_check(
                        self.checks.asserts, self.current_pc, parsed_check.expr
                    )
                elif parsed_check.kind == CheckKind.REQUIRE:
                    append_check(
                        self.checks.requires, self.current_pc, parsed_check.expr
                    )
                elif parsed_check.kind == CheckKind.INVARIANT:
                    if isinstance(elm, CodeElementLabel):
                        append_check(
                            self.checks.invariants,
                            str(self.current_scope + elm.identifier.name),
                            parsed_check.expr,
                        )
                    else:
                        raise PreprocessorError(
                            "@invariant annotation must be placed before a label",
                            checked_elm.location,
                        )
                elif (
                    parsed_check.kind == CheckKind.POST_COND
                    or parsed_check.kind == CheckKind.PRE_COND
                ):
                    if isinstance(elm, CodeElementFunction):
                        if parsed_check.kind == CheckKind.PRE_COND:
                            append_check(
                                self.checks.pre_conds,
                                str(self.current_scope),
                                parsed_check.expr,
                            )
                        else:
                            append_check(
                                self.checks.post_conds,
                                str(self.current_scope),
                                parsed_check.expr,
                            )
                    else:
                        raise PreprocessorError(
                            "@pre/@post annotation must be placed before a function",
                            checked_elm.location,
                        )

    def visit_CheckedCodeElement(self, checked_elm: CheckedCodeElement):
        if (
            isinstance(checked_elm.code_elm, CodeElementFunction)
            and checked_elm.code_elm.element_type == "func"
        ):
            self.current_checks = checked_elm.raw_checks
            self.current_function = checked_elm
        else:
            self.compile_checks(checked_elm)

        return self.visit(checked_elm.code_elm)

    def visit_RetInstruction(self, instruction: RetInstruction):
        self.ret_map[self.current_pc] = str(self.current_scope)

        return super().visit_RetInstruction(instruction)

    def visit_function_body_with_retries(
        self, code_block: CodeBlock, location: Optional[Location]
    ):
        # This is needed because pre/postconditions can refer to arguments of the function.
        # So it's easier to process the conditions when the preprocessor
        # has stepped into the body of the function.

        if self.current_checks is not None:
            assert (
                self.current_function is not None
            ), "self.current_checks is not None nut self.current_function is"
            self.compile_checks(self.current_function)
            self.current_checks = None

        return super().visit_function_body_with_retries(code_block, location)

    def parse_check(
        self, raw_check: str, logical_variables: dict[str, CairoType] = {}
    ) -> Union[PreprocessedCheck, LogicalVariableDeclaration]:
        """
        Parses a raw check into a `PreprocessedCheck`.
        """
        z3_transformer = Z3Transformer(
            identifiers=self.identifiers,
            accessible_scopes=self.accessible_scopes,
            flow_tracking=self.flow_tracking,
            preprocessor=self,
        )

        tree = parse(raw_check)

        return z3_transformer.transform(tree)

    def get_next_CodeElement(
        self, code_elements: Iterable[tuple[int, CodeElement]]
    ) -> Optional[tuple[int, CodeElement]]:
        """
        Returns the first non empty line code element in `code_elements`
        if it has the type `code_elm_type`. Returns `None` otherwise.
        """
        for i, code_elm in code_elements:
            if not isinstance(code_elm, CodeElementEmptyLine):
                return (i, code_elm)

        return None
