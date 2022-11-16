from pathlib import Path

import pytest
from starkware.cairo.lang.compiler.ast.expr import ExprIdentifier
from starkware.cairo.lang.compiler.parser_transformer import ParserError

from horus.compiler.parser import parse
from horus.compiler.z3_transformer import Z3ExpressionTransformer

TESTS = Path(__file__).parent


def test_parse_handles_non_annotation_code():
    """
    Do we get an `UnexpectedToken` error when there's a logical identifier
    outside an annotation?
    """
    code = (TESTS / "logical_identifier_outside_annotation.cairo").read_text()
    with pytest.raises(ParserError):
        parse(filename=None, code=code, code_type="cairo_file", expected_type=None)


def test_z3_transformer_visit_expr_identifier():
    t = Z3ExpressionTransformer()
    t.visit_ExprIdentifier(ExprIdentifier(name=""))
