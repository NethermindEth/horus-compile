import dataclasses
from enum import Enum
from typing import Optional, Sequence, Union

from starkware.cairo.lang.compiler.ast.bool_expr import BoolExpr
from starkware.cairo.lang.compiler.ast.cairo_types import CairoType
from starkware.cairo.lang.compiler.ast.code_elements import CodeElement
from starkware.cairo.lang.compiler.ast.expr import Expression
from starkware.cairo.lang.compiler.ast.formatting_utils import LocationField
from starkware.cairo.lang.compiler.ast.node import AstNode
from starkware.cairo.lang.compiler.error_handling import Location
from starkware.python.expression_string import ExpressionString


@dataclasses.dataclass
class ExprLogicalIdentifier(Expression):
    """
    Represents an expression of the form "$name".
    """

    name: str
    location: Optional[Location] = LocationField

    def to_expr_str(self) -> ExpressionString:
        return ExpressionString.highest(self.name)

    def get_children(self) -> Sequence[Optional["AstNode"]]:
        return []


@dataclasses.dataclass
class BoolFormula(AstNode):
    """
    Base class for all boolean formula classes.
    """

    pass


@dataclasses.dataclass
class BoolExprAtom(BoolFormula):
    """
    Wrapper around Cairo's `BoolExpr`.
    """

    bool_expr: BoolExpr

    def get_children(self) -> Sequence[Optional["AstNode"]]:
        return [self.bool_expr]


@dataclasses.dataclass
class BoolExprCompare(BoolFormula):
    """
    A boolean formula of the form a <= b, a < b,
    a >= b or a > b.
    """

    a: Expression
    b: Expression
    comp: str

    def get_children(self) -> Sequence[Optional["AstNode"]]:
        return [self.a, self.b]


@dataclasses.dataclass
class BoolConst(BoolFormula):
    """
    A boolean constant `True` or `False`.
    """

    const: bool

    def get_children(self) -> Sequence[Optional["AstNode"]]:
        return []


@dataclasses.dataclass
class BoolOperation(BoolFormula):
    """
    Represents A /\ B, A \/ B, A -> B.
    """

    a: BoolFormula
    b: BoolFormula
    op: str

    def get_children(self) -> Sequence[Optional["AstNode"]]:
        return [self.a, self.b]


@dataclasses.dataclass
class BoolNegation(BoolFormula):
    """
    Represents ~A.
    """

    operand: BoolFormula

    def get_children(self) -> Sequence[Optional["AstNode"]]:
        return [self.operand]


@dataclasses.dataclass
class CodeElementCheck(CodeElement):
    """
    Represent a particular Horus annotation which is not
    a logical variable declaration.
    """

    class CheckKind(Enum):
        ASSERT = "@assert"
        REQUIRE = "@require"
        POST_COND = "@post"
        PRE_COND = "@pre"
        INVARIANT = "@invariant"

    check_kind: CheckKind
    formula: BoolFormula

    def format(self, allowed_line_length):
        # TODO: implement better formatting
        return str(self.check_kind)

    def get_children(self) -> Sequence[Optional["AstNode"]]:
        return [self.formula]


@dataclasses.dataclass
class CodeElementLogicalVariableDeclaration(CodeElement):
    """
    Represents a logical variable declaration.
    """

    name: str
    type: CairoType

    def format(self, allowed_line_length):
        return f"@declare {self.name}: {self.type.format()}"

    def get_children(self) -> Sequence[Optional["AstNode"]]:
        return []


@dataclasses.dataclass
class CheckedCodeElement(CodeElement):
    """
    Represents a code element with a check placed after.
    E.g., `[ap] = 1; ap++ # @assert True` will be parsed
    into one `CheckedCodeElement`.
    """

    check: Union[CodeElementCheck, CodeElementLogicalVariableDeclaration]
    code_elm: CodeElement
    location: Optional[Location] = LocationField

    def format(self, allowed_line_length):
        return f"{self.check.format(allowed_line_length)}\n{self.code_elm.format(allowed_line_length)}"

    def get_children(self) -> Sequence[Optional[AstNode]]:
        return [self.check, self.code_elm]
