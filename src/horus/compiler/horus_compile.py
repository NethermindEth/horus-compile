import argparse
import json
import sys
from tabnanny import check
from typing import Callable, Tuple

import starkware.cairo.lang.compiler.ast.visitor
import starkware.cairo.lang.compiler.parser
import starkware.cairo.lang.version
from starkware.cairo.lang.compiler.cairo_compile import (
    cairo_compile_add_common_args,
    cairo_compile_common,
)
from starkware.cairo.lang.compiler.error_handling import LocationError
from starkware.cairo.lang.compiler.expression_transformer import ExpressionTransformer
from starkware.cairo.lang.compiler.module_reader import ModuleReader
from starkware.cairo.lang.compiler.preprocessor.default_pass_manager import (
    PreprocessorStage,
)
from starkware.cairo.lang.compiler.preprocessor.pass_manager import (
    PassManager,
    PassManagerContext,
    Stage,
)
from starkware.starknet.compiler.compile import assemble_starknet_contract, get_abi
from starkware.starknet.compiler.starknet_pass_manager import starknet_pass_manager
from starkware.starknet.compiler.validation_utils import verify_account_contract

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
    )


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
    assert isinstance(preprocessor_stage, PreprocessorStage)
    preprocessor_stage.preprocessor_cls = HorusPreprocessor
    return manager


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
    preprocessed = cairo_compile_common(
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
