from dataclasses import dataclass

from starkware.cairo.lang.compiler.ast.arguments import IdentifierList
from starkware.cairo.lang.compiler.ast.cairo_types import CairoType


@dataclass
class StorageVarInfo:
    args: IdentifierList
    ret_type: CairoType
