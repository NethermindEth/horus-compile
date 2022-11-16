from pathlib import Path

import pytest
from starkware.cairo.lang.compiler.parser_transformer import ParserError

from horus.compiler.parser import parse

TESTS = Path(__file__).parent


def test_parse_handles_non_annotation_code():
    """
    Do we get an `UnexpectedToken` error when there's a logical identifier
    outside an annotation?
    """
    code = (TESTS / "logical_identifier_outside_annotation.cairo").read_text()
    with pytest.raises(ParserError):
        parse(filename=None, code=code, code_type="cairo_file", expected_type=None)
