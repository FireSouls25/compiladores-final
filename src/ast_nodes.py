"""AST node definitions (output of the syntactic phase)."""
from dataclasses import dataclass, field
from typing import Optional

# ---- expressions ----

@dataclass
class Literal:
    value: object
    lit_type: str  # 'int' | 'float' | 'str' | 'bool' | 'None'
    line: int = 0
    col: int = 0

@dataclass
class Var:
    name: str
    line: int = 0
    col: int = 0

@dataclass
class BinOp:
    op: str  # '+','-','*','/','%','==','!=','<','<=','>','>=','and','or'
    left: object
    right: object
    line: int = 0
    col: int = 0

@dataclass
class UnaryOp:
    op: str  # '-' | 'not'
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

# ---- statements ----

@dataclass
class LetStmt:
    name: str
    ann: Optional[str]  # declared type or None
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
    init: object        # LetStmt | AssignStmt | ExprStmt
    cond: object
    update: object      # AssignStmt | ExprStmt
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
    target: object      # Var
    index: object
    expr: object
    line: int = 0
    col: int = 0

@dataclass
class ReturnStmt:
    expr: object = None  # None => bare `return;`
    line: int = 0
    col: int = 0

@dataclass
class ExprStmt:
    expr: object
    line: int = 0
    col: int = 0

@dataclass
class Block:
    """Bare `{ ... }` block; opens a new lexical scope."""
    stmts: list
    line: int = 0
    col: int = 0

@dataclass
class Param:
    name: str
    ann: Optional[str]  # None => unchecked (accepts anything)
    line: int = 0
    col: int = 0

@dataclass
class FuncDef:
    name: str
    params: list[Param]
    ret: str  # 'None' when omitted
    body: list
    line: int = 0
    col: int = 0

@dataclass
class Program:
    items: list  # FuncDef | statement
