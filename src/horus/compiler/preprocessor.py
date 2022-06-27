from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

import z3
from starkware.cairo.lang.compiler.ast.code_elements import (
    CodeBlock,
    CodeElement,
    CodeElementEmptyLine,
    CodeElementFunction,
    CodeElementLabel,
)
from starkware.cairo.lang.compiler.error_handling import Location
from starkware.cairo.lang.compiler.resolve_search_result import resolve_search_result
from starkware.starknet.compiler.starknet_preprocessor import (
    StarknetPreprocessedProgram,
    StarknetPreprocessor,
)

from horus.compiler.code_elements import (
    CheckedCodeElement,
    CodeElementCheck,
    CodeElementLogicalVariableDeclaration,
    CodeElementSmt,
    HorusCodeElement,
)
from horus.compiler.contract_definition import Assertion, HorusChecks
from horus.compiler.parser import *
from horus.compiler.z3_transformer import *
from horus.utils import z3And


@dataclass
class HorusProgram(StarknetPreprocessedProgram):
    checks: HorusChecks
    ret_map: dict[int, str]
    logical_variables: dict[str, dict[str, str]]
    smt: str


class HorusPreprocessor(StarknetPreprocessor):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.checks: HorusChecks = HorusChecks()
        self.ret_map: dict[int, str] = {}
        self.logical_identifiers: dict[str, CairoType] = {}
        self.logical_signatures: dict[str, dict[str, str]] = {}

        # This is used to defer pre/postcondition unfolding
        # until the visitor steps into the body of the function
        # when the preprocessor stumbles upon a function.
        self.current_checks: list[HorusCodeElement] = []
        self.current_function = None
        self.smt = ""

    def get_program(self) -> HorusProgram:
        starknet_program = super().get_program()
        return HorusProgram(
            **starknet_program.__dict__,
            checks=self.checks,
            ret_map=self.ret_map,
            logical_variables=self.logical_signatures,
            smt=self.smt,
        )

    def visit_CodeBlock(self, code_block: CodeBlock):
        return super().visit_CodeBlock(code_block)

    def visit_CodeElementCheck(self, check: CodeElementCheck):
        pass

    def visit_CheckedCodeElement(self, checked_code_element: CheckedCodeElement):
        result = self.visit(checked_code_element.code_elm)
        if isinstance(checked_code_element.annotation, CodeElementSmt):
            self.smt += checked_code_element.annotation.smt_expr
        self.current_checks.append(checked_code_element.annotation)
        return result

    def visit(self, obj):
        unfolded_obj = obj.code_elm if isinstance(obj, CheckedCodeElement) else obj
        if self.current_checks:
            if not isinstance(unfolded_obj, CodeElementEmptyLine):
                if (
                    isinstance(unfolded_obj, CodeElementFunction)
                    and unfolded_obj.element_type == "func"
                ):
                    self.current_function = unfolded_obj
                else:
                    self.compile_checks(unfolded_obj)

        return super().visit(obj)

    def add_logical_variable(
        self,
        declaration: CodeElementLogicalVariableDeclaration,
        is_member: bool = False,
    ):
        if isinstance(declaration.type, TypeStruct):
            if declaration.type.is_fully_resolved:
                search_result = self.identifiers.get(declaration.type.scope)
            else:
                search_result = self.identifiers.search(
                    self.accessible_scopes, declaration.type.scope
                )
            definition = resolve_search_result(search_result, self.identifiers)

            declaration.type.scope = definition.full_name
            declaration.type.is_fully_resolved = True

            assert isinstance(
                definition, StructDefinition
            ), "TypeStruct must contain StructDefinition"

            for member_name, member_definition in definition.members.items():
                self.add_logical_variable(
                    CodeElementLogicalVariableDeclaration(
                        declaration.name + "." + member_name,
                        member_definition.cairo_type,
                    ),
                    is_member=True,
                )
        elif isinstance(declaration.type, TypeTuple):
            for i, member in enumerate(declaration.type.members):
                if member.name is not None:
                    member_name = f"{declaration.name}.{member.name}"
                else:
                    member_name = f"{declaration.name}.{i}"
                self.add_logical_variable(
                    CodeElementLogicalVariableDeclaration(member_name, member.typ),
                    is_member=True,
                )

        if not is_member:
            try:
                variables_of_the_function = self.logical_signatures[
                    str(self.current_scope)
                ]
            except KeyError:
                self.logical_signatures[str(self.current_scope)] = {}
                variables_of_the_function = self.logical_signatures[
                    str(self.current_scope)
                ]

            variables_of_the_function[declaration.name] = declaration.type.format()

        self.logical_identifiers[declaration.name] = declaration.type

    def compile_checks(self, code_elem: CodeElement):
        def append_check(
            check_dict: dict[Any, Assertion],
            key: Any,
            check: z3.BoolRef,
            axiom: z3.BoolRef,
        ):
            current_check_bool_ref = check_dict.get(
                key, Assertion(z3.BoolVal(True), z3.BoolVal(True))
            )
            check_dict[key] = Assertion(
                z3And(current_check_bool_ref.bool_ref, check),
                z3And(current_check_bool_ref.axiom, axiom),
            )

        is_function = isinstance(code_elem, CodeElementFunction)

        for parsed_check in self.current_checks:
            if isinstance(parsed_check, CodeElementLogicalVariableDeclaration):
                if is_function:
                    self.add_logical_variable(parsed_check)
                else:
                    raise PreprocessorError(
                        "@declare annotation is not allowed here", code_elem.location
                    )
            elif isinstance(parsed_check, CodeElementCheck):
                z3_transformer = Z3Transformer(
                    self.identifiers, self, self.logical_identifiers
                )
                expr = z3_transformer.visit(parsed_check.formula)
                axiom = z3.BoolVal(True)

                if z3_transformer.inverse_equations:
                    axiom = z3.And(z3_transformer.inverse_equations)

                if parsed_check.check_kind == CodeElementCheck.CheckKind.ASSERT:
                    append_check(self.checks.asserts, self.current_pc, expr, axiom)
                elif parsed_check.check_kind == CodeElementCheck.CheckKind.REQUIRE:
                    append_check(self.checks.requires, self.current_pc, expr, axiom)
                elif parsed_check.check_kind == CodeElementCheck.CheckKind.INVARIANT:
                    if isinstance(code_elem, CodeElementLabel):
                        append_check(
                            self.checks.invariants,
                            str(self.current_scope + code_elem.identifier.name),
                            expr,
                            axiom,
                        )
                    else:
                        raise PreprocessorError(
                            "@invariant annotation must be placed before a label",
                            code_elem.location,
                        )
                elif (
                    parsed_check.check_kind == CodeElementCheck.CheckKind.POST_COND
                    or parsed_check.check_kind == CodeElementCheck.CheckKind.PRE_COND
                ):
                    if isinstance(code_elem, CodeElementFunction):
                        if (
                            parsed_check.check_kind
                            == CodeElementCheck.CheckKind.PRE_COND
                        ):
                            append_check(
                                self.checks.pre_conds,
                                str(self.current_scope),
                                expr,
                                axiom,
                            )
                        else:
                            append_check(
                                self.checks.post_conds,
                                str(self.current_scope),
                                expr,
                                axiom,
                            )
                    else:
                        raise PreprocessorError(
                            "@pre/@post annotation must be placed before a function",
                            code_elem.location,
                        )

        self.current_checks = []

    def visit_function_body_with_retries(
        self, code_block: CodeBlock, location: Optional[Location]
    ):
        # This is needed because pre/postconditions can refer to arguments of the function.
        # So it's easier to process the conditions when the preprocessor
        # has stepped into the body of the function.

        if self.current_function is not None:
            self.compile_checks(self.current_function)
            self.current_function = None
            self.current_checks = []

        result = super().visit_function_body_with_retries(code_block, location)
        self.logical_identifiers = {}

        return result

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
