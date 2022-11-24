from __future__ import annotations

from importlib import resources
from typing import Optional, Tuple, Union

import lark
from lark.exceptions import LarkError, UnexpectedToken, VisitError
from lark.load_grammar import PackageResource
from starkware.cairo.lang.compiler.error_handling import InputFile, LocationError
from starkware.cairo.lang.compiler.parser import wrap_lark_error
from starkware.cairo.lang.compiler.parser_transformer import ParserContext

from horus.compiler.parser_transformer import HorusTransformer


def starkware_grammar_loader(
    base_path: Union[None, str, PackageResource], grammar_path: str
) -> tuple[str, str]:
    """
    A hack to load cairo.ebnf instead of cairo.lark.
    """
    if base_path is not None:
        raise IOError()  # lark import loading procedure will try
        # to use another loader in this case

    if not grammar_path.startswith("starkware"):
        raise IOError()  # same here

    actual_path = grammar_path.replace(".lark", ".ebnf")
    path_entries = actual_path.split("/")
    module_name = ".".join(path_entries[:-1])

    return (actual_path, resources.read_text(module_name, path_entries[-1]))


grammar = resources.read_text("horus.compiler", "horus.ebnf")
gram_parser = lark.Lark(
    grammar,
    start=[
        "cairo_file",
        "code_block",
        "code_element",
        "expr",
        "instruction",
        "type",
        "typed_identifier",
        "annotation",
    ],
    lexer="basic",
    parser="lalr",
    propagate_positions=True,
    import_paths=[starkware_grammar_loader],
)


def parse(
    filename: Optional[str],
    code: str,
    code_type: str,
    expected_type,
    parser_context: Optional[ParserContext] = None,
):
    """
    Copy-pasted function from StarkWare's compiler with only
    difference is that we use `HorusTransformer`
    instead of `ParserTranformer` and do some manipulations
    with logical identifier tokens.
    """
    is_parsing_check = code_type == "annotation"
    input_file = InputFile(filename=filename, content=code)
    parser_transformer = HorusTransformer(
        input_file, parser_context=parser_context, is_parsing_check=is_parsing_check
    )

    parser = gram_parser.parse_interactive(code, start=code_type)
    parser_state = parser.parser_state
    old_state_stack = list(parser_state.state_stack)
    old_value_stack = list(parser_state.value_stack)
    try:
        token = None
        for token in parser.lexer_state.lex(parser_state):
            if not is_parsing_check:
                # This is a hack to use the same grammar for
                # Cairo code and Horus checks.
                # If a Cairo code is being parsed
                # logical identifiers cannot appear anywhere.
                if token.type == "LOGICAL_IDENTIFIER":
                    accepts = parser.accepts()
                    accepts.remove("LOGICAL_IDENTIFIER")
                    raise UnexpectedToken(token=token, expected=accepts)  # type: ignore

            old_state_stack = list(parser_state.state_stack)
            old_value_stack = list(parser_state.value_stack)
            parser.feed_token(token)
        old_state_stack = list(parser_state.state_stack)
        old_value_stack = list(parser_state.value_stack)
        tree = parser.feed_eof(last_token=token)
    except UnexpectedToken as err:
        # Restore the old state stack.
        parser_state.state_stack = old_state_stack
        parser_state.value_stack = old_value_stack
        err.interactive_parser = parser
        raise wrap_lark_error(err, input_file) from None
    except LarkError as err:
        raise wrap_lark_error(err, input_file) from None

    try:
        parsed = parser_transformer.transform(tree)
    except VisitError as err:
        if isinstance(err.orig_exc, LocationError):
            raise err.orig_exc
        else:
            raise
    assert isinstance(
        parsed, expected_type
    ), f"Expected parsing result to be {expected_type.__name__}. Found: {type(parsed).__name__}"

    return parsed
