from __future__ import annotations

from importlib import resources
from typing import Union

import lark


def starkware_grammar_loader(
    base_path: Union[None, str, lark.PackageResource], grammar_path: str
) -> tuple[str, str]:
    """
    A hack to load cairo.ebnf instead of cairo.lark.
    """
    if base_path is not None:
        raise IOError()

    if not grammar_path.startswith("starkware"):
        raise IOError()

    actual_path = grammar_path.replace(".lark", ".ebnf")
    path_entries = actual_path.split("/")
    module_name = ".".join(path_entries[:-1])

    return (actual_path, resources.read_text(module_name, path_entries[-1]))


grammar = resources.read_text("horus.compiler", "check_language.ebnf")
parser = lark.Lark(
    grammar=grammar,
    start="annotation",
    parser="lalr",
    import_paths=[starkware_grammar_loader],
)


def parse(code: str, start: str = None):
    return parser.parse(code, start)
