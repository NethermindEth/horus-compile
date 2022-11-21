from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

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
from starkware.cairo.lang.compiler.identifier_definition import StructDefinition
from starkware.cairo.lang.compiler.identifier_utils import get_struct_definition
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
    CodeElementStorageUpdate,
)
from horus.compiler.contract_definition import FunctionAnnotations, StorageUpdate
from horus.compiler.parser import *
from horus.compiler.z3_transformer import *
from horus.utils import get_decls, z3And


@dataclass
class HorusProgram(StarknetPreprocessedProgram):
    specifications: dict[ScopedName, FunctionAnnotations]
    invariants: dict[ScopedName, z3.BoolRef]
    storage_vars: dict[ScopedName, int]


class HorusPreprocessor(StarknetPreprocessor):
    def __init__(self, **kwargs):
        self.storage_vars = kwargs.pop("storage_vars")
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

        storage_vars: dict[ScopedName, int] = {}

        for storage_var in self.storage_vars:
            storage_vars[storage_var] = self.get_size(
                TypeStruct(
                    self.identifiers.get(storage_var + "read" + "Args").canonical_name,
                )
            )

        return HorusProgram(
            **starknet_program.__dict__,
            specifications=self.specifications,
            invariants=self.invariants,
            storage_vars=storage_vars,
        )

    def visit_CodeBlock(self, code_block: CodeBlock):
        return super().visit_CodeBlock(code_block)

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
                    self.compile_annotations(unfolded_obj)

        return super().visit(obj)

    def add_logical_variable(
        self,
        declaration: CodeElementLogicalVariableDeclaration,
        is_member: bool = False,
    ):
        declaration.type = self.resolve_type(declaration.type)
        if isinstance(declaration.type, TypeStruct):
            definition = self.identifiers.get_by_full_name(declaration.type.scope)

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
                    CodeElementLogicalVariableDeclaration(
                        member_name, self.resolve_type(member.typ)
                    ),
                    is_member=True,
                )

        if not is_member:
            current_annotations = self.specifications.get(
                self.current_scope, FunctionAnnotations()
            )
            variables_of_the_function = current_annotations.logical_variables
            variables_of_the_function[
                ScopedName.from_string(declaration.name)
            ] = self.resolve_type(declaration.type)
            self.specifications[self.current_scope] = current_annotations

        self.logical_identifiers[declaration.name] = declaration.type

    def add_state_change(self, decl: CodeElementStorageUpdate):
        z3_transformer = Z3Transformer(
            self.identifiers,
            self,
            self.logical_identifiers,
            is_post=True,
            storage_vars=self.storage_vars,
        )
        z3_expr_transformer = Z3ExpressionTransformer(
            identifiers=self.identifiers, z3_transformer=z3_transformer
        )

        decl_full_name = self.identifiers.search(
            self.accessible_scopes, ScopedName.from_string(decl.name)
        ).canonical_name

        if not decl_full_name in self.storage_vars:
            raise PreprocessorError(
                f"{decl_full_name} is not a storage variable", location=decl.location
            )

        storage_var_args = get_struct_definition(
            decl_full_name + "read" + "Args", self.identifiers
        )
        assert isinstance(storage_var_args, StructDefinition)

        if len(storage_var_args.members) != len(decl.arguments.args):
            raise PreprocessorError(
                f"Incorrect number of arguments for a storage map.",
                location=decl.location,
            )

        for storage_def in storage_var_args.members.values():
            assert isinstance(
                storage_def.cairo_type, TypeFelt
            ), "Non-felt arguments of storage maps are not supported yet."

        args = []
        for [storage_arg_name, storage_def], arg in zip(
            storage_var_args.members.items(), decl.arguments.args
        ):
            if arg.identifier and arg.identifier.name != storage_arg_name:
                raise PreprocessorError(
                    f"Wrong argument name: {arg.identifier.name}",
                    location=decl.location,
                )

            arg_expr, arg_type = simplify_and_get_type(
                arg.expr, self, self.logical_identifiers, is_post=True
            )

            if not isinstance(arg_type, TypeFelt):
                raise PreprocessorError(
                    f"Argument value must have type {TypeFelt().format}",
                    location=decl.location,
                )
            args.append(z3_expr_transformer.visit(arg_expr))

        current_annotations = self.specifications.get(
            self.current_scope, FunctionAnnotations()
        )
        storage_updates = current_annotations.storage_update.get(decl_full_name, [])
        storage_update = StorageUpdate(
            args,
            z3_expr_transformer.visit(
                simplify(decl.value, self, self.logical_identifiers, is_post=True)
            ),
        )
        storage_updates.append(storage_update)
        current_annotations.storage_update[decl_full_name] = storage_updates
        self.specifications[self.current_scope] = current_annotations

    def compile_annotations(self, code_elem: CodeElement):
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

        for parsed_check in self.current_checks:
            if (
                isinstance(parsed_check, CodeElementCheck)
                and parsed_check.check_kind is CodeElementCheck.CheckKind.INVARIANT
            ):
                if not isinstance(code_elem, CodeElementLabel):
                    raise PreprocessorError(
                        "@invariant annotation must be placed before a label",
                        code_elem.location,
                    )
            else:
                if not (
                    isinstance(code_elem, CodeElementFunction)
                    and code_elem.element_type == "func"
                ):
                    raise PreprocessorError(
                        f"{parsed_check.format()} annotation is not allowed here",
                        code_elem.location,
                    )

            if isinstance(parsed_check, CodeElementLogicalVariableDeclaration):
                self.add_logical_variable(parsed_check)
            elif isinstance(parsed_check, CodeElementStorageUpdate):
                self.add_state_change(parsed_check)
            elif isinstance(parsed_check, CodeElementCheck):
                is_post = (
                    parsed_check.check_kind == CodeElementCheck.CheckKind.POST_COND
                )
                z3_transformer = Z3Transformer(
                    self.identifiers,
                    self,
                    self.logical_identifiers,
                    is_post,
                    self.storage_vars,
                )
                expr = z3_transformer.visit(parsed_check.formula)

                if parsed_check.check_kind == CodeElementCheck.CheckKind.INVARIANT:
                    append_check(
                        parsed_check.check_kind,
                        self.current_scope + code_elem.identifier.name,
                        expr,
                    )
                elif (
                    parsed_check.check_kind == CodeElementCheck.CheckKind.POST_COND
                    or parsed_check.check_kind == CodeElementCheck.CheckKind.PRE_COND
                ):
                    append_check(
                        parsed_check.check_kind,
                        None,
                        expr,
                    )

        self.current_checks = []

    def visit_function_body_with_retries(
        self, code_block: CodeBlock, location: Optional[Location]
    ):
        # This is needed because pre/postconditions can refer to arguments of the function.
        # So it's easier to process the conditions when the preprocessor
        # has stepped into the body of the function.

        if self.current_function is not None:
            self.compile_annotations(self.current_function)
            self.current_function = None
            self.current_checks = []

        super().visit_function_body_with_retries(code_block, location)
        self.logical_identifiers = {}
