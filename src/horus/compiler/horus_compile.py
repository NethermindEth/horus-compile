import argparse
import json
import sys
from typing import Callable, Tuple

from starkware.cairo.lang.compiler.cairo_compile import (
    cairo_compile_add_common_args,
    cairo_compile_common,
)
from starkware.cairo.lang.compiler.error_handling import LocationError
from starkware.cairo.lang.compiler.module_reader import ModuleReader
from starkware.cairo.lang.compiler.preprocessor.default_pass_manager import (
    PreprocessorStage,
)
from starkware.cairo.lang.compiler.preprocessor.pass_manager import PassManager
from starkware.starknet.compiler.compile import assemble_starknet_contract, get_abi
from starkware.starknet.compiler.starknet_pass_manager import starknet_pass_manager
from starkware.starknet.compiler.validation_utils import verify_account_contract

from horus.compiler.horus_definition import HorusChecks, HorusDefinition
from horus.compiler.horus_preprocessor import HorusPreprocessor, HorusProgram


def assemble_horus_contract(
    preprocessed_program: HorusProgram, *args, **kwargs
) -> HorusDefinition:
    contract_definition = assemble_starknet_contract(
        preprocessed_program, *args, **kwargs
    )

    return HorusDefinition(
        **contract_definition.__dict__,
        checks=preprocessed_program.checks,
        ret_map=preprocessed_program.ret_map
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
    preprocessor_stage = manager.stages[manager.get_stage_index("preprocessor")][1]
    assert isinstance(preprocessor_stage, PreprocessorStage)
    preprocessor_stage.preprocessor_cls = HorusPreprocessor
    return manager


def main():
    parser = argparse.ArgumentParser(
        description="A tool to compile checked StarkNet contracts."
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

    try:
        cairo_compile_add_common_args(parser)
        args = parser.parse_args()
        preprocessed = cairo_compile_common(
            args=args,
            pass_manager_factory=pass_manager_factory,
            assemble_func=assemble_horus_contract,
        )
        abi = get_abi(preprocessed=preprocessed)
        verify_account_contract(
            contract_abi=abi, is_account_contract=args.account_contract
        )
        if args.abi is not None:
            json.dump(abi, args.abi, indent=4, sort_keys=True)
            args.abi.write("\n")
    except LocationError as err:
        print(err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
