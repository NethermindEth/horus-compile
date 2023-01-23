from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Optional, Sequence

from starkware.cairo.lang.compiler.ast.bool_expr import BoolEqExpr
from starkware.cairo.lang.compiler.ast.cairo_types import CairoType
from starkware.cairo.lang.compiler.ast.code_elements import CodeElement
from starkware.cairo.lang.compiler.ast.expr import ArgList, Expression
from starkware.cairo.lang.compiler.ast.formatting_utils import LocationField, Particle
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

    def get_particles(self) -> list[Particle]:
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
    Wrapper around Cairo's `BoolEqExpr`.
    """

    bool_expr: BoolEqExpr

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
    location: Optional[Location] = LocationField

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
    Represents A and B, A or B, A -> B.
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


class CodeElementAnnotation(CodeElement):
    pass


@dataclasses.dataclass
class CodeElementCheck(CodeElementAnnotation):
    """
    Represents a logical annotation of a kind
    specified by `check_kind`.
    """

    class CheckKind(Enum):
        POST_COND = "@post"
        PRE_COND = "@pre"
        ASSERT = "@assert"
        INVARIANT = "@invariant"

    check_kind: CheckKind
    formula: BoolFormula
    location: Optional[Location] = LocationField
    unpreprocessed_rep: str = ""

    def format(self, allowed_line_length):
        # TODO: implement better formatting
        return str(self.check_kind)

    def get_children(self) -> Sequence[Optional["AstNode"]]:
        return [self.formula]


@dataclasses.dataclass
class CodeElementLogicalVariableDeclaration(CodeElementAnnotation):
    """
    Represents a logical variable declaration.
    """

    name: str
    type: CairoType
    location: Optional[Location] = LocationField

    def format(self, allowed_line_length):
        return f"@declare {self.name}: {self.type.format()}"

    def get_children(self) -> Sequence[Optional["AstNode"]]:
        return []


@dataclasses.dataclass
class CodeElementStorageUpdate(CodeElementAnnotation):
    """
    Represents a storage variable change annotation.
    """

    name: str
    arguments: ArgList
    value: Expression
    location: Optional[Location] = LocationField
    unpreprocessed_rep: str = ""

    def format(self, allowed_line_length):
        return f"@storage_update {self.name}[{self.arguments.format()}] = {self.value.format()}"

    def get_children(self) -> Sequence[Optional["AstNode"]]:
        return [
            self.arguments,
            self.value,
        ]


@dataclasses.dataclass
class AnnotatedCodeElement(CodeElement):
    """
    Represents a code element with an annotation placed after.
    Note that empty lines are also code elements, so usually
    `code_elm` is a `CodeElementEmptyLine`.
    """

    annotation: CodeElementAnnotation
    code_elm: CodeElement

    def format(self, allowed_line_length):
        return f"{self.annotation.format(allowed_line_length)}\n{self.code_elm.format(allowed_line_length)}"

    def get_children(self) -> Sequence[Optional[AstNode]]:
        return [self.annotation, self.code_elm]
