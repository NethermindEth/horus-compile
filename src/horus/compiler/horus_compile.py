from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
from typing import Callable, Optional, Sequence, Tuple, Type

import starkware.cairo.lang.compiler.ast.visitor
import starkware.cairo.lang.compiler.parser
import starkware.cairo.lang.compiler.preprocessor.preprocess_codes
import starkware.cairo.lang.version
from starkware.cairo.lang.compiler.ast.code_elements import CodeElementFunction
from starkware.cairo.lang.compiler.cairo_compile import (
    LIBS_DIR_ENVVAR,
    MAIN_SCOPE,
    START_FILE_NAME,
    cairo_compile_add_common_args,
    cairo_compile_common,
    generate_cairo_dependencies_file,
    get_codes,
    get_module_reader,
    get_start_code,
)
from starkware.cairo.lang.compiler.expression_transformer import ExpressionTransformer
from starkware.cairo.lang.compiler.identifier_manager import IdentifierManager
from starkware.cairo.lang.compiler.module_reader import ModuleReader
from starkware.cairo.lang.compiler.preprocessor.auxiliary_info_collector import (
    AuxiliaryInfoCollector,
)
from starkware.cairo.lang.compiler.preprocessor.default_pass_manager import (
    PreprocessorStage,
)
from starkware.cairo.lang.compiler.preprocessor.identifier_aware_visitor import (
    IdentifierAwareVisitor,
)
from starkware.cairo.lang.compiler.preprocessor.pass_manager import (
    PassManager,
    PassManagerContext,
    Stage,
    VisitorStage,
)
from starkware.cairo.lang.compiler.preprocessor.preprocessor import PreprocessedProgram
from starkware.cairo.lang.compiler.scoped_name import ScopedName
from starkware.starknet.compiler.compile import assemble_starknet_contract, get_abi
from starkware.starknet.compiler.starknet_pass_manager import starknet_pass_manager
from starkware.starknet.compiler.storage_var import (
    STORAGE_VAR_ATTR,
    STORAGE_VAR_DECORATOR,
    StorageVarDeclVisitor,
    StorageVarImplementationVisitor,
)
from starkware.starknet.compiler.validation_utils import (
    has_decorator,
    verify_account_contract,
)

import horus.compiler.parser
from horus.compiler.code_elements import AnnotatedCodeElement
from horus.compiler.contract_definition import HorusDefinition
from horus.compiler.preprocessor import HorusPreprocessor, HorusProgram


def assemble_horus_contract(
    preprocessed_program: HorusProgram, *args, **kwargs
) -> HorusDefinition:
    contract_definition = assemble_starknet_contract(
        preprocessed_program, *args, **kwargs
    )

    return HorusDefinition(
        **contract_definition.__dict__,
        specifications=preprocessed_program.specifications,
        invariants=preprocessed_program.invariants,
        storage_vars=preprocessed_program.storage_vars,
    )


class HorusStorageVarDeclVisitor(IdentifierAwareVisitor):
    def __init__(
        self,
        storage_vars: set[ScopedName],
        identifiers: Optional[IdentifierManager] = None,
    ):
        self.storage_vars = storage_vars
        super().__init__(identifiers)

    def _visit_default(self, obj):
        return obj

    def visit_CodeElementFunction(self, elm: CodeElementFunction):
        is_storage_var, storage_var_location = has_decorator(
            elm=elm, decorator_name=STORAGE_VAR_DECORATOR
        )
        if is_storage_var:
            self.storage_vars.add(self.current_scope + elm.name)
        return elm


class HorusStorageVarCollectorStage(Stage):
    def run(self, context: PassManagerContext):
        assert isinstance(context, HorusPassManagerContext)
        visitor = HorusStorageVarDeclVisitor(
            storage_vars=context.storage_vars, identifiers=context.identifiers
        )
        for module in context.modules:
            visitor.visit(module)

        context.storage_vars = visitor.storage_vars
        return visitor


def horus_pass_manager(
    prime: int,
    read_module: Callable[[str], Tuple[str, str]],
    disable_hint_validation: bool = False,
) -> PassManager:

    manager = starknet_pass_manager(
        prime,
        read_module,
        opt_unused_functions=False,  # don't omit unused functions it breaks storage var stuff.
        disable_hint_validation=disable_hint_validation,
    )
    manager.stages.insert(0, ("monkeypatch", MonkeyPatchStage()))
    preprocessor_stage = manager.stages[manager.get_stage_index("preprocessor")][1]
    manager.replace(
        "preprocessor",
        HorusPreprocessorStage(
            preprocessor_stage.prime,
            HorusPreprocessor,
            preprocessor_stage.auxiliary_info_cls,
            preprocessor_stage.preprocessor_kwargs,
        ),
    )
    manager.add_before(
        "storage_var_signature", "storage_collector", HorusStorageVarCollectorStage()
    )
    return manager


@dataclasses.dataclass
class HorusPassManagerContext(PassManagerContext):
    storage_vars: set[ScopedName] = dataclasses.field(default_factory=set)


class HorusPreprocessorStage(PreprocessorStage):
    def run(self, context: PassManagerContext):
        assert isinstance(context, HorusPassManagerContext)
        self.preprocessor_kwargs["storage_vars"] = context.storage_vars
        return super().run(context)


def preprocess_codes(
    codes: Sequence[Tuple[str, str]],
    pass_manager: PassManager,
    main_scope: ScopedName = ScopedName(),
    start_codes: Optional[list[Tuple[str, str]]] = None,
):
    """
    Preprocesses a list of Cairo files and returns a PreprocessedProgram instance.
    codes is a list of pairs (code_string, file_name).
    """
    context = HorusPassManagerContext(
        codes=list(codes),
        main_scope=main_scope,
        identifiers=IdentifierManager(),
        start_codes=[] if start_codes is None else start_codes,
    )

    pass_manager.run(context)

    assert context.preprocessed_program is not None
    return context.preprocessed_program


class MonkeyPatchStage(Stage):
    """
    Additional compilation stage we add before
    any other stage is performed in order to monkey-patch
    StarkWare definitions.
    All future monkey-patching should be done here.
    """

    def run(self, context: PassManagerContext):
        def visit_AnnotatedCodeElement(self, annotated_code_element):
            return AnnotatedCodeElement(
                annotation=annotated_code_element.annotation,
                code_elm=self.visit(annotated_code_element.code_elm),
            )

        starkware.cairo.lang.compiler.ast.visitor.Visitor.visit_AnnotatedCodeElement = (
            visit_AnnotatedCodeElement
        )
        starkware.cairo.lang.compiler.parser.parse = horus.compiler.parser.parse
        ExpressionTransformer.visit_ExprLogicalIdentifier = lambda self, expr: expr


def horus_compile_common(
    args: argparse.Namespace,
    pass_manager_factory: Callable[[argparse.Namespace, ModuleReader], PassManager],
    assemble_func: Callable,
) -> PreprocessedProgram:
    """
    Common code for CLI Cairo compilation.

    Arguments:
    args - Parsed arguments.
    pass_manager_factory - A pass manager factory.
    assemble_func - a function that converts a preprocessed program to the final output,
        the return value should be a Marshmallow dataclass.
    """

    start_time = time.time()
    debug_info = args.debug_info or args.debug_info_with_source

    try:
        codes = get_codes(args.files)
        out = args.output if args.output is not None else sys.stdout

        cairo_path: list[str] = list(
            filter(
                None,
                args.cairo_path.split(":") + os.getenv(LIBS_DIR_ENVVAR, "").split(":"),
            )
        )
        module_reader = get_module_reader(cairo_path=cairo_path)

        pass_manager = pass_manager_factory(args, module_reader)

        start_codes = []
        file_contents_for_debug_info = {}
        if getattr(args, "proof_mode", False):
            start_codes = [(get_start_code(), START_FILE_NAME)]
            file_contents_for_debug_info[START_FILE_NAME] = start_codes[0][0]

        preprocessed = preprocess_codes(
            codes=codes,
            pass_manager=pass_manager,
            main_scope=MAIN_SCOPE,
            start_codes=start_codes,
        )

        if args.preprocess:
            print(preprocessed.format(with_locations=debug_info), end="", file=out)
        else:
            if args.debug_info_with_source:
                for source_file in module_reader.source_files | set(args.files):
                    file_contents_for_debug_info[source_file] = open(source_file).read()

            assembled_program = assemble_func(
                preprocessed,
                main_scope=MAIN_SCOPE,
                add_debug_info=debug_info,
                file_contents_for_debug_info=file_contents_for_debug_info,
            )

            json.dump(
                assembled_program.Schema().dump(assembled_program),
                out,
                indent=4,
                sort_keys=True,
            )
            # Print a new line at the end.
            print(file=out)

        return preprocessed
    finally:
        if args.cairo_dependencies:
            generate_cairo_dependencies_file(
                args.cairo_dependencies,
                module_reader.source_files | set(args.files),
                start_time,
            )


def main(args):
    parser = argparse.ArgumentParser(
        description="A tool to compile checked StarkNet contracts.",
        conflict_handler="resolve",
    )
    parser.add_argument(
        "--abi", type=argparse.FileType("w"), help="Output the contract's ABI."
    )
    parser.add_argument(
        "--disable_hint_validation",
        action="store_true",
        help="Disable the hint validation.",
    )
    parser.add_argument(
        "--account_contract", action="store_true", help="Compile as account contract."
    )

    def pass_manager_factory(
        args: argparse.Namespace, module_reader: ModuleReader
    ) -> PassManager:
        return horus_pass_manager(
            prime=args.prime,
            read_module=module_reader.read,
            disable_hint_validation=args.disable_hint_validation,
        )

    cairo_compile_add_common_args(parser)
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {horus.__version__}; cairo-compile {starkware.cairo.lang.version.__version__}",
    )
    args = parser.parse_args(args)
    preprocessed = horus_compile_common(
        args=args,
        pass_manager_factory=pass_manager_factory,
        assemble_func=assemble_horus_contract,
    )
    abi = get_abi(preprocessed=preprocessed)
    verify_account_contract(contract_abi=abi, is_account_contract=args.account_contract)
    if args.abi is not None:
        json.dump(abi, args.abi, indent=4, sort_keys=True)
        args.abi.write("\n")


def run():
    main(sys.argv[1:])
