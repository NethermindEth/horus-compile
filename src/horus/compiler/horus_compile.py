from __future__ import annotations

import argparse
import dataclasses
import functools
import json
import os
import sys
import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import starkware.cairo.lang.compiler.ast.visitor
import starkware.cairo.lang.compiler.parser
import starkware.cairo.lang.compiler.preprocessor.preprocess_codes
import starkware.cairo.lang.version
from starkware.cairo.lang.cairo_constants import DEFAULT_PRIME
from starkware.cairo.lang.compiler.ast.arguments import IdentifierList
from starkware.cairo.lang.compiler.ast.code_elements import CodeElementFunction
from starkware.cairo.lang.compiler.cairo_compile import (
    LIBS_DIR_ENVVAR,
    MAIN_SCOPE,
    START_FILE_NAME,
    generate_cairo_dependencies_file,
    get_codes,
    get_module_reader,
    get_start_code,
)
from starkware.cairo.lang.compiler.error_handling import LocationError
from starkware.cairo.lang.compiler.expression_transformer import ExpressionTransformer
from starkware.cairo.lang.compiler.identifier_manager import IdentifierManager
from starkware.cairo.lang.compiler.module_reader import ModuleReader
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
)
from starkware.cairo.lang.compiler.preprocessor.preprocessor import PreprocessedProgram
from starkware.cairo.lang.compiler.scoped_name import ScopedName
from starkware.starknet.compiler.compile import assemble_starknet_contract, get_abi
from starkware.starknet.compiler.starknet_pass_manager import starknet_pass_manager
from starkware.starknet.compiler.storage_var import STORAGE_VAR_DECORATOR
from starkware.starknet.compiler.validation_utils import has_decorator
from starkware.starknet.services.api.contract_class import ContractClass

import horus.compiler.parser
from horus.compiler.code_elements import AnnotatedCodeElement
from horus.compiler.contract_definition import HorusDefinition
from horus.compiler.preprocessor import HorusPreprocessor, HorusProgram


def assemble_horus_contract(
    preprocessed_program: HorusProgram, *args, **kwargs
) -> Tuple[ContractClass, HorusDefinition]:
    contract_definition = assemble_starknet_contract(
        preprocessed_program, *args, **kwargs
    )

    return (
        contract_definition,
        HorusDefinition(
            horus_version=horus.__version__,
            specifications=preprocessed_program.specifications,
            invariants=preprocessed_program.invariants,
            storage_vars=preprocessed_program.storage_vars,
        ),
    )


class HorusStorageVarDeclVisitor(IdentifierAwareVisitor):
    def __init__(
        self,
        storage_vars: Dict[ScopedName, IdentifierList],
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
            self.storage_vars[self.current_scope + elm.name] = elm.arguments
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
    opt_unused_functions: bool = True,
    disable_hint_validation: bool = False,
) -> PassManager:
    manager = starknet_pass_manager(
        prime, read_module, opt_unused_functions, disable_hint_validation
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
    storage_vars: Dict[ScopedName, IdentifierList] = dataclasses.field(
        default_factory=dict
    )


class HorusPreprocessorStage(PreprocessorStage):
    def run(self, context: PassManagerContext):
        assert isinstance(context, HorusPassManagerContext)
        self.preprocessor_kwargs["storage_vars"] = context.storage_vars
        return super().run(context)


def preprocess_codes(
    codes: Sequence[Tuple[str, str]],
    pass_manager: PassManager,
    main_scope: ScopedName = ScopedName(),
    start_codes: Optional[List[Tuple[str, str]]] = None,
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
        specs_out = args.spec_output if args.spec_output is not None else sys.stdout

        cairo_path: List[str] = list(
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

            assembled_program, specs = assemble_func(
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

            json.dump(
                specs.Schema().dump(specs),
                specs_out,
                indent=4,
                sort_keys=True,
            )
            # Print a new line at the end.
            print(file=specs_out)

        return preprocessed
    finally:
        if args.cairo_dependencies:
            generate_cairo_dependencies_file(
                args.cairo_dependencies,
                module_reader.source_files | set(args.files),
                start_time,
            )


def cairo_compile_add_common_args(parser: argparse.ArgumentParser):
    parser.add_argument(
        "files",
        metavar="file",
        type=str,
        nargs="+",
        help="One or more Cairo programs to compile.",
    )
    parser.add_argument(
        "--prime",
        type=int,
        default=DEFAULT_PRIME,
        help="The positive integer size of the finite field. This is a (usually large) prime power over which basic arithmetic within the program is carried out.",
    )
    parser.add_argument(
        "--cairo_path",
        type=str,
        default="",
        help=(
            'A list of directories, separated by ":" to resolve import paths. '
            "The full list will consist of directories defined by this argument, followed by "
            f"the environment variable {LIBS_DIR_ENVVAR}, the working directory and the standard "
            "library path."
        ),
    )
    parser.add_argument(
        "--preprocess",
        action="store_true",
        help="Stop after the preprocessor step and output the preprocessed program, which consists only of low-level Cairo (e.g. frame pointer and allocation pointer manipulations) along with annotations indicating relevant source code locations.",
    )
    parser.add_argument(
        "--output",
        type=argparse.FileType("w"),
        help="The output file name (default: stdout).",
    )
    parser.add_argument(
        "--no_debug_info",
        dest="debug_info",
        action="store_false",
        help="Don't include debug information in the compiled file. Removes the 'debug_info' field from the JSON output, which by default contains an 'instruction_locations' map with information on flow tracking data, hints, accessible scopes, and source code location.",
    )
    parser.add_argument(
        "--debug_info_with_source",
        action="store_true",
        help="Dump the source code of all relevant .cairo files into a 'file_contents' field in the 'debug_info' of the JSON output.",
    )
    parser.add_argument(
        "--cairo_dependencies",
        type=str,
        help="Path to dump a list of the Cairo source files used during the compilation as a CMake file.",
    )
    parser.add_argument(
        "--no_opt_unused_functions",
        dest="opt_unused_functions",
        action="store_false",
        default=True,
        help="Disable unused function optimization, which ordinarily only compiles functions reachable from the main scope in the dependency graph, i.e. functions that are actually called.",
    )


def main(args):
    parser = argparse.ArgumentParser(
        description="A tool to compile checked StarkNet contracts.",
        conflict_handler="resolve",
    )
    parser.add_argument(
        "--abi",
        type=argparse.FileType("w"),
        help=(
            "Dump the contract's ABI (application binary interface) to a file. "
            "This is a JSON list containing metadata (like type signatures and members) "
            "on functions, structs, and other things within the program."
        ),
    )
    parser.add_argument(
        "--disable_hint_validation",
        action="store_true",
        help="Disable the hint validation, which ordinarily checks program hints against a whitelist.",
    )
    parser.add_argument(
        "--account_contract",
        action="store_true",
        help="Compile as account contract, which means the ABI will be checked for expected builtin entry points.",
    )
    parser.add_argument(
        "--spec_output",
        type=argparse.FileType("w"),
        help="The specification output file name (default: stdout).",
    )

    def pass_manager_factory(
        args: argparse.Namespace, module_reader: ModuleReader
    ) -> PassManager:
        return horus_pass_manager(
            prime=args.prime,
            read_module=module_reader.read,
            opt_unused_functions=args.opt_unused_functions,
            disable_hint_validation=args.disable_hint_validation,
        )

    try:
        cairo_compile_add_common_args(parser)
        parser.add_argument(
            "-v",
            "--version",
            action="version",
            version=f"%(prog)s {horus.__version__}; cairo-compile {starkware.cairo.lang.version.__version__}",
        )
        args = parser.parse_args(args=args)
        assemble_func = functools.partial(
            assemble_horus_contract,
            filter_identifiers=False,
            is_account_contract=args.account_contract,
        )
        preprocessed = horus_compile_common(
            args=args,
            pass_manager_factory=pass_manager_factory,
            assemble_func=assemble_func,
        )
        abi = get_abi(preprocessed=preprocessed)
        if args.abi is not None:
            json.dump(abi, args.abi, indent=4, sort_keys=True)
            args.abi.write("\n")
    except LocationError as err:
        print(err, file=sys.stderr)
        return 1
    return 0


def run():
    main(sys.argv[1:])
