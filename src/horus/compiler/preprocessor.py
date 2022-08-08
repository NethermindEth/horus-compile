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
    CodeElementScoped,
)
from starkware.cairo.lang.compiler.error_handling import Location
from starkware.cairo.lang.compiler.resolve_search_result import resolve_search_result
from starkware.cairo.lang.compiler.scoped_name import ScopedName
from starkware.starknet.compiler.starknet_preprocessor import (
    StarknetPreprocessedProgram,
    StarknetPreprocessor,
)

from horus.compiler.code_elements import (
    AnnotatedCodeElement,
    CodeElementAnnotation,
    CodeElementCheck,
    CodeElementLogicalVariableDeclaration,
)
from horus.compiler.contract_definition import FunctionAnnotations
from horus.compiler.parser import *
from horus.compiler.z3_transformer import *
from horus.utils import get_decls, z3And


@dataclass
class HorusProgram(StarknetPreprocessedProgram):
    specifications: dict[ScopedName, FunctionAnnotations]
    invariants: dict[ScopedName, z3.BoolRef]


class HorusPreprocessor(StarknetPreprocessor):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.specifications: dict[ScopedName, FunctionAnnotations] = {}
        self.invariants: dict[ScopedName, z3.BoolRef] = {}
        self.logical_identifiers: dict[str, CairoType] = {}

        # This is used to defer pre/postcondition unfolding
        # until the visitor steps into the body of the function
        # when the preprocessor stumbles upon a function.
        self.current_checks: list[CodeElementAnnotation] = []
        self.current_function = None

    def get_program(self) -> HorusProgram:
        starknet_program = super().get_program()

        for specification in self.specifications.values():
            specification.decls = {
                **get_decls(specification.pre),
                **get_decls(specification.post),
            }
            for var in HORUS_DECLS.keys():
                specification.decls.pop(var, None)

        return HorusProgram(
            **starknet_program.__dict__,
            specifications=self.specifications,
            invariants=self.invariants,
        )

    def visit_CodeBlock(self, code_block: CodeBlock):
        return super().visit_CodeBlock(code_block)

    def visit_CodeElementCheck(self, check: CodeElementCheck):
        pass

    def visit_AnnotatedCodeElement(self, annotated_code_element: AnnotatedCodeElement):
        result = self.visit(annotated_code_element.code_elm)
        self.current_checks.append(annotated_code_element.annotation)
        return result

    def visit(self, obj):
        unfolded_obj = obj.code_elm if isinstance(obj, AnnotatedCodeElement) else obj
        if self.current_checks:
            if not isinstance(unfolded_obj, CodeElementEmptyLine):
                if (
                    isinstance(unfolded_obj, CodeElementFunction)
                    and unfolded_obj.element_type == "func"
                ):
                    self.current_function = unfolded_obj
                elif isinstance(unfolded_obj, CodeElementScoped):
                    if (
                        isinstance(unfolded_obj.code_elements[0], CodeElementFunction)
                        and unfolded_obj.code_elements[0].element_type == "func"
                    ):
                        self.current_function = unfolded_obj.code_elements[0]
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
            current_annotations = self.specifications.get(
                self.current_scope, FunctionAnnotations()
            )
            variables_of_the_function = current_annotations.logical_variables
            variables_of_the_function[
                ScopedName.from_string(declaration.name)
            ] = declaration.type
            self.specifications[self.current_scope] = current_annotations

        self.logical_identifiers[declaration.name] = declaration.type

    def compile_checks(self, code_elem: CodeElement):
        def append_check(
            check_kind: CodeElementCheck.CheckKind,
            key: Optional[ScopedName],
            check: z3.BoolRef,
        ):
            current_annotations = self.specifications.get(
                self.current_scope, FunctionAnnotations()
            )
            if check_kind is CodeElementCheck.CheckKind.PRE_COND:
                current_annotations.pre = z3And(current_annotations.pre, check)
            elif check_kind is CodeElementCheck.CheckKind.POST_COND:
                current_annotations.post = z3And(current_annotations.post, check)
            elif check_kind is CodeElementCheck.CheckKind.INVARIANT:
                current_invariant = self.invariants.get(key, z3.BoolVal(True))
                self.invariants[key] = z3And(current_invariant, check)

            self.specifications[self.current_scope] = current_annotations

        is_function = isinstance(code_elem, CodeElementFunction)

        for parsed_check in self.current_checks:
            if isinstance(parsed_check, CodeElementLogicalVariableDeclaration):
                if is_function:
                    self.add_logical_variable(parsed_check)
                else:
                    raise PreprocessorError(
                        "@declare annotation is not allowed here", code_elem.location
                    )
            else:
                is_post = (
                    parsed_check.check_kind == CodeElementCheck.CheckKind.POST_COND
                )
                z3_transformer = Z3Transformer(
                    self.identifiers,
                    self,
                    self.logical_identifiers,
                    is_post,
                )
                expr = z3_transformer.visit(parsed_check.formula)

                if parsed_check.check_kind == CodeElementCheck.CheckKind.INVARIANT:
                    if isinstance(code_elem, CodeElementLabel):
                        append_check(
                            parsed_check.check_kind,
                            self.current_scope + code_elem.identifier.name,
                            expr,
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
                        append_check(
                            parsed_check.check_kind,
                            None,
                            expr,
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
