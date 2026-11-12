"""Phase 4: IR generation. Typed/resolved AST -> Three-Address Code (TAC).

Temporaries are `%tN` and labels `%LN`. Neither prefix can appear in a MiniB
identifier (the lexer only accepts letters, digits and `_`), so generated names
can never collide with user variables.
"""
from dataclasses import dataclass, field
from typing import Any
from . import ast_nodes as A


@dataclass
class Instr:
    op: str
    a: Any = None
    b: Any = None
    c: Any = None

    def __str__(self) -> str:
        if self.op == "func_begin":
            params = ", ".join(self.c or [])
            return f"func {self.a}({params}):"
        if self.op == "func_end":
            return f"endfunc {self.a}"
        if self.op == "label":
            return f"{self.a}:"
        if self.op == "assign":
            return f"  {self.a} = {fmt(self.b)}"
        if self.op == "binop":
            return f"  {self.a} = {fmt(self.b)} {self.c} {fmt(self.extra)}"
        if self.op == "unop":
            return f"  {self.a} = {self.c} {fmt(self.b)}"
        if self.op == "goto":
            return f"  goto {self.a}"
        if self.op == "ifFalse":
            return f"  ifFalse {fmt(self.a)} goto {self.b}"
        if self.op == "call":
            args = ", ".join(fmt(x) for x in (self.b or []))
            if self.a:
                return f"  {self.a} = call {self.c}({args})"
            return f"  call {self.c}({args})"
        if self.op == "return":
            return f"  return {fmt(self.a) if self.a is not None else ''}".rstrip()
        return f"  {self.op} {self.a} {self.b} {self.c}"

    extra: Any = field(default=None, repr=False)


def fmt(v) -> str:
    if isinstance(v, str) and v.startswith("@"):
        return repr(v[1:])  # string constant -> quoted
    if isinstance(v, str):
        return v
    if v is True:
        return "True"
    if v is False:
        return "False"
    if v is None:
        return "None"
    if isinstance(v, float):
        return repr(v)
    return repr(v)


def const(v) -> str:
    """Encode a Python constant as an IR operand."""
    if isinstance(v, str):
        return "@" + v  # '@' prefix marks string constants
    return v


def var_name(node) -> str:
    """Resolved (scope-safe) name of a declaration/assignment."""
    return getattr(node, "resolved_name", None) or getattr(node, "resolved", None) or node.name


class IRGenerator:
    def __init__(self):
        self.code: list[Instr] = []
        self.t = 0
        self.l = 0

    def temp(self) -> str:
        self.t += 1
        return f"%t{self.t}"

    def label(self) -> str:
        self.l += 1
        return f"%L{self.l}"

    def emit(self, ins: Instr):
        self.code.append(ins)

    def generate(self, prog: A.Program) -> list[Instr]:
        for it in prog.items:
            if isinstance(it, A.FuncDef):
                self.gen_func(it)
            else:
                self.gen_stmt(it, is_top=True)
        return self.code

    def gen_func(self, fn: A.FuncDef):
        self.emit(Instr("func_begin", fn.name, None, [p.name for p in fn.params]))
        for s in fn.body:
            self.gen_stmt(s, is_top=False)
        # implicit return None for void functions
        if fn.ret == "None":
            self.emit(Instr("return", None))
        self.emit(Instr("func_end", fn.name))

    def gen_stmt(self, s, is_top: bool):
        if isinstance(s, A.Block):
            for x in s.stmts:
                self.gen_stmt(x, is_top)
        elif isinstance(s, A.LetStmt):
            v = self.gen_expr(s.expr)
            self.emit(Instr("assign", var_name(s), v))
        elif isinstance(s, A.AssignStmt):
            v = self.gen_expr(s.expr)
            self.emit(Instr("assign", var_name(s), v))
        elif isinstance(s, A.IfStmt):
            c = self.gen_expr(s.cond)
            le, lend = self.label(), self.label()
            self.emit(Instr("ifFalse", c, le))
            for x in s.then_body:
                self.gen_stmt(x, is_top)
            self.emit(Instr("goto", lend))
            self.emit(Instr("label", le))
            for x in s.else_body:
                self.gen_stmt(x, is_top)
            self.emit(Instr("label", lend))
        elif isinstance(s, A.WhileStmt):
            ls, le = self.label(), self.label()
            self.emit(Instr("label", ls))
            c = self.gen_expr(s.cond)
            self.emit(Instr("ifFalse", c, le))
            for x in s.body:
                self.gen_stmt(x, is_top)
            self.emit(Instr("goto", ls))
            self.emit(Instr("label", le))
        elif isinstance(s, A.ReturnStmt):
            v = self.gen_expr(s.expr) if s.expr is not None else None
            self.emit(Instr("return", v))
        elif isinstance(s, A.ExprStmt):
            self.gen_expr(s.expr, stmt=True)
        else:
            raise ValueError(f"unknown stmt {type(s).__name__}")

    def gen_expr(self, e, stmt: bool = False):
        if isinstance(e, A.Literal):
            if e.lit_type == "str":
                return const(e.value)
            return e.value
        if isinstance(e, A.Var):
            return getattr(e, "resolved", e.name)
        if isinstance(e, A.UnaryOp):
            v = self.gen_expr(e.operand)
            d = self.temp()
            self.emit(Instr("unop", d, v, e.op, extra=None))
            return d
        if isinstance(e, A.BinOp):
            l = self.gen_expr(e.left)
            r = self.gen_expr(e.right)
            d = self.temp()
            ins = Instr("binop", d, l, e.op)
            ins.extra = r
            self.emit(ins)
            return d
        if isinstance(e, A.Call):
            args = [self.gen_expr(a) for a in e.args]
            if stmt:
                self.emit(Instr("call", None, args, e.name))
                return None
            d = self.temp()
            self.emit(Instr("call", d, args, e.name))
            return d
        raise ValueError(f"unknown expr {type(e).__name__}")
