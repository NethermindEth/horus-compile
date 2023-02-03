from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from starkware.cairo.lang.compiler.ast.arguments import IdentifierList
from starkware.cairo.lang.compiler.ast.code_elements import (
    CodeBlock,
    CodeElement,
    CodeElementEmptyLine,
    CodeElementFunction,
    CodeElementLabel,
    CodeElementScoped,
)
from starkware.cairo.lang.compiler.error_handling import Location
from starkware.cairo.lang.compiler.identifier_definition import (
    FunctionDefinition,
    FutureIdentifierDefinition,
    LabelDefinition,
    StructDefinition,
)
from starkware.cairo.lang.compiler.identifier_manager import MissingIdentifierError
from starkware.cairo.lang.compiler.identifier_utils import get_struct_definition
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
from horus.compiler.contract_definition import (
    Annotation,
    FunctionAnnotations,
    StorageUpdate,
)
from horus.compiler.parser import *
from horus.compiler.z3_transformer import *
from horus.utils import get_decls

PRE_COND = CodeElementCheck.CheckKind.PRE_COND
POST_COND = CodeElementCheck.CheckKind.POST_COND
ASSERT = CodeElementCheck.CheckKind.ASSERT
INVARIANT = CodeElementCheck.CheckKind.INVARIANT


@dataclass
class HorusProgram(StarknetPreprocessedProgram):
    specifications: Dict[ScopedName, FunctionAnnotations]
    invariants: Dict[ScopedName, Annotation]
    storage_vars: Dict[ScopedName, int]


class HorusPreprocessor(StarknetPreprocessor):
    def __init__(self, **kwargs):
        self.storage_vars: Dict[ScopedName, IdentifierList] = kwargs.pop("storage_vars")
        super().__init__(**kwargs)
        self.specifications: Dict[ScopedName, FunctionAnnotations] = {}
        self.invariants: Dict[ScopedName, Annotation] = {}
        self.logical_identifiers: Dict[str, CairoType] = {}

        # This is used to defer pre/postcondition unfolding
        # until the visitor steps into the body of the function
        # when the preprocessor stumbles upon a function.
        self.current_checks: List[CodeElementAnnotation] = []
        self.current_function = None

        # Used for dummy labels
        self.current_fresh_index: int = 0

    def get_program(self) -> HorusProgram:
        starknet_program = super().get_program()

        for specification in self.specifications.values():
            specification.decls = {
                **get_decls(specification.pre.sexpr),
                **get_decls(specification.post.sexpr),
            }
            for var in HORUS_DECLS.keys():
                specification.decls.pop(var, None)

        storage_vars: Dict[ScopedName, int] = {}

        for storage_var, args in self.storage_vars.items():
            size = sum(
                (
                    self.get_size(arg.expr_type)
                    if arg.expr_type is not None
                    else self.get_size(TypeFelt())
                    for arg in args.identifiers
                )
            )

            storage_vars[storage_var] = size

        return HorusProgram(
            **starknet_program.__dict__,
            specifications=self.specifications,
            invariants=self.invariants,
            storage_vars=storage_vars,
        )

    def visit_CodeBlock(self, code_block: CodeBlock):
        return super().visit_CodeBlock(code_block)

    def add_dummy_label_with_assert(self, assrt: CodeElementCheck):
        if not isinstance(
            self.identifiers.get_by_full_name(self.current_scope),
            FunctionDefinition,
        ):
            raise (
                PreprocessorError(
                    f"Cannot use @assert annotation outside of a function.",
                    location=assrt.location,
                )
            )

        name = f"!anonymous_assert_label_{self.current_fresh_index}"
        self.current_fresh_index += 1
        self.identifiers.add_identifier(
            name=self.current_scope + name,
            definition=FutureIdentifierDefinition(identifier_type=LabelDefinition),
        )
        self.add_label(ExprIdentifier(name))
        z3_transformer = Z3Transformer(
            self.identifiers,
            self,
            self.logical_identifiers,
            self.storage_vars,
            is_post=False,
        )
        expr = z3_transformer.visit(assrt.formula)
        self.invariants[self.current_scope + name] = Annotation(
            sexpr=expr,
            source=[assrt.unpreprocessed_rep],
        )

    def visit_AnnotatedCodeElement(self, annotated_code_element: AnnotatedCodeElement):
        if isinstance(annotated_code_element.annotation, CodeElementCheck):
            if annotated_code_element.annotation.check_kind == ASSERT:
                self.add_dummy_label_with_assert(annotated_code_element.annotation)

                # Turning the function into annotated one.
                current_annotations = self.specifications.get(
                    self.current_scope, FunctionAnnotations()
                )
                self.specifications[self.current_scope] = current_annotations

                return self.visit(annotated_code_element.code_elm)

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
            self.storage_vars,
            is_post=True,
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
                arg.expr,
                self,
                self.logical_identifiers,
                self.storage_vars,
                is_post=True,
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
                simplify(
                    decl.value,
                    self,
                    self.logical_identifiers,
                    self.storage_vars,
                    is_post=True,
                )
            ),
            decl.unpreprocessed_rep,
        )
        storage_updates.append(storage_update)
        current_annotations.storage_update[decl_full_name] = storage_updates
        self.specifications[self.current_scope] = current_annotations

    def compile_annotations(self, code_elem: CodeElement):
        def append_check(
            check_kind: CodeElementCheck.CheckKind,
            key: Optional[ScopedName],
            check: Annotation,
        ):
            current_annotations = self.specifications.get(
                self.current_scope, FunctionAnnotations()
            )
            if check_kind == PRE_COND:
                current_annotations.pre = current_annotations.pre & check
            elif check_kind == POST_COND:
                current_annotations.post = current_annotations.post & check
            elif check_kind == INVARIANT:
                assert key is not None
                current_invariant = self.invariants.get(key, Annotation())
                self.invariants[key] = current_invariant & check

            self.specifications[self.current_scope] = current_annotations

        for parsed_check in self.current_checks:
            try:
                if (
                    isinstance(parsed_check, CodeElementCheck)
                    and parsed_check.check_kind == INVARIANT
                ):
                    if not isinstance(code_elem, CodeElementLabel):
                        raise PreprocessorError(
                            "@invariant annotation must be placed before a label",
                            parsed_check.location,
                        )
                elif isinstance(parsed_check, CodeElementCheck):
                    if not (
                        isinstance(code_elem, CodeElementFunction)
                        and code_elem.element_type == "func"
                    ):
                        raise PreprocessorError(
                            f"{parsed_check.check_kind} annotation is not allowed here",
                            parsed_check.location,
                        )

                if isinstance(parsed_check, CodeElementLogicalVariableDeclaration):
                    self.add_logical_variable(parsed_check)
                elif isinstance(parsed_check, CodeElementStorageUpdate):
                    self.add_state_change(parsed_check)
                elif isinstance(parsed_check, CodeElementCheck):
                    is_post = parsed_check.check_kind == POST_COND
                    z3_transformer = Z3Transformer(
                        self.identifiers,
                        self,
                        self.logical_identifiers,
                        self.storage_vars,
                        is_post,
                    )
                    expr = z3_transformer.visit(parsed_check.formula)
                    annotation = Annotation(
                        sexpr=expr, source=[parsed_check.unpreprocessed_rep]
                    )

                    if parsed_check.check_kind == INVARIANT:
                        append_check(
                            parsed_check.check_kind,
                            self.current_scope + code_elem.identifier.name,
                            annotation,
                        )
                    elif parsed_check.check_kind in (PRE_COND, POST_COND):
                        append_check(
                            parsed_check.check_kind,
                            None,
                            annotation,
                        )
            except MissingIdentifierError as e:
                raise PreprocessorError(str(e), location=parsed_check.location)

        self.current_checks = []

    def visit_CodeElementFunction(self, elm: CodeElementFunction):
        new_scope = self.current_scope + elm.name

        if elm.element_type == "func":
            # Check if this function should be skipped.
            if (
                self.functions_to_compile is not None
                and new_scope not in self.functions_to_compile
            ):
                self.current_function = None
                self.current_checks = []

        return super().visit_CodeElementFunction(elm)

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
