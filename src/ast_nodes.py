from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Literal:
    value: object
    lit_type: str
    line: int = 0
    col: int = 0

@dataclass
class Var:
    name: str
    line: int = 0
    col: int = 0

@dataclass
class BinOp:
    op: str
    left: object
    right: object
    line: int = 0
    col: int = 0

@dataclass
class UnaryOp:
    op: str
    operand: object
    line: int = 0
    col: int = 0

@dataclass
class Call:
    name: str
    args: list
    line: int = 0
    col: int = 0

@dataclass
class ListLit:
    items: list
    line: int = 0
    col: int = 0

@dataclass
class Index:
    target: object
    index: object
    line: int = 0
    col: int = 0


@dataclass
class LetStmt:
    name: str
    ann: Optional[str]
    expr: object
    line: int = 0
    col: int = 0

@dataclass
class AssignStmt:
    name: str
    expr: object
    line: int = 0
    col: int = 0

@dataclass
class IfStmt:
    cond: object
    then_body: list
    else_body: list = field(default_factory=list)
    line: int = 0
    col: int = 0

@dataclass
class WhileStmt:
    cond: object
    body: list
    line: int = 0
    col: int = 0

@dataclass
class ForStmt:
    init: object
    cond: object
    update: object
    body: list
    line: int = 0
    col: int = 0

@dataclass
class BreakStmt:
    line: int = 0
    col: int = 0

@dataclass
class ContinueStmt:
    line: int = 0
    col: int = 0

@dataclass
class SetIndexStmt:
    target: object
    index: object
    expr: object
    line: int = 0
    col: int = 0

@dataclass
class ReturnStmt:
    expr: object = None
    line: int = 0
    col: int = 0

@dataclass
class ExprStmt:
    expr: object
    line: int = 0
    col: int = 0

@dataclass
class Block:
    stmts: list
    line: int = 0
    col: int = 0

@dataclass
class Param:
    name: str
    ann: Optional[str]
    line: int = 0
    col: int = 0

@dataclass
class FuncDef:
    name: str
    params: list[Param]
    ret: str
    body: list
    line: int = 0
    col: int = 0

@dataclass
class Program:
    items: list
