"""Phase 3: Semantic analysis. AST -> typed AST checks + symbol table.

Checks: scopes, redeclare, undefined vars, type mismatches, arity,
return types, bool conditions. Allows int->float promotion.
`None` annotation on params means unchecked (accepts anything).
"""
from . import ast_nodes as A
from .parser import _Block


class SemanticError(Exception):
    pass


NUMERIC = {"int", "float"}

BUILTINS = {
    # name: (param_types, return_type, variadic)
    "print": (["unknown"], "None", True),
    "len": (["str"], "int", False),
    "input": ([], "str", True),  # input() or input(prompt: str)
}


def assignable(expected: str, actual: str) -> bool:
    if expected == actual:
        return True
    if expected in ("unknown",) or actual in ("unknown",):
        return True
    if expected == "float" and actual == "int":
        return True
    return False


class SemanticAnalyzer:
    def __init__(self):
        self.errors: list[str] = []
        self.scopes: list[dict] = [{}]  # name -> {'kind','type',...}
        self.functions: dict = {}  # name -> {'params':[(n,t)], 'ret':t}
        self.current_ret: str | None = None
        self.current_fn: str | None = None
        self.has_return: bool = False

    # -- scope helpers --
    def push(self):
        self.scopes.append({})

    def pop(self):
        self.scopes.pop()

    def declare(self, name, info, line, col):
        if name in self.scopes[-1]:
            self.errors.append(f"{line}:{col}: redeclaration of '{name}' in same scope")
            return
        self.scopes[-1][name] = info

    def lookup(self, name):
        for s in reversed(self.scopes):
            if name in s:
                return s[name]
        return None

    def err(self, line, col, msg):
        self.errors.append(f"{line}:{col}: {msg}")

    # -- entry --
    def analyze(self, prog: A.Program) -> dict:
        # pass 1: register all function signatures (allows forward calls)
        for it in prog.items:
            if isinstance(it, A.FuncDef):
                if it.name in self.functions or it.name in BUILTINS:
                    self.err(it.line, it.col, f"redefinition of function '{it.name}'")
                else:
                    self.functions[it.name] = {
                        "params": [(p.name, p.ann or "unknown") for p in it.params],
                        "ret": it.ret,
                    }
        # pass 2: check bodies + top-level statements
        for it in prog.items:
            if isinstance(it, A.FuncDef):
                self.check_func(it)
            else:
                self.check_stmt(it)
        if self.errors:
            raise SemanticError("\n".join(self.errors))
        return {"functions": self.functions}

    def check_func(self, fn: A.FuncDef):
        self.push()
        self.current_ret = fn.ret
        self.current_fn = fn.name
        self.has_return = False
        seen = set()
        for p in fn.params:
            if p.name in seen:
                self.err(p.line, p.col, f"duplicate parameter '{p.name}'")
            seen.add(p.name)
            self.scopes[-1][p.name] = {"kind": "param", "type": p.ann or "unknown"}
        for s in fn.body:
            self.check_stmt(s)
        if fn.ret != "None" and not self.has_return:
            self.err(fn.line, fn.col, f"function '{fn.name}' must return '{fn.ret}' on all paths (no return found)")
        self.pop()
        self.current_ret = None
        self.current_fn = None

    def check_stmt(self, s):
        if isinstance(s, _Block):
            self.push()
            for x in s.stmts:
                self.check_stmt(x)
            self.pop()
            return
        if isinstance(s, A.LetStmt):
            t = self.check_expr(s.expr)
            if s.ann:
                if not assignable(s.ann, t):
                    self.err(s.line, s.col, f"cannot assign '{t}' to '{s.ann}' in 'let {s.name}'")
                self.declare(s.name, {"kind": "var", "type": s.ann}, s.line, s.col)
            else:
                self.declare(s.name, {"kind": "var", "type": t}, s.line, s.col)
        elif isinstance(s, A.AssignStmt):
            info = self.lookup(s.name)
            if info is None:
                self.err(s.line, s.col, f"undefined variable '{s.name}'")
                self.check_expr(s.expr)
            else:
                t = self.check_expr(s.expr)
                if not assignable(info["type"], t):
                    self.err(s.line, s.col, f"cannot assign '{t}' to variable '{s.name}' of type '{info['type']}'")
        elif isinstance(s, A.IfStmt):
            t = self.check_expr(s.cond)
            if t != "bool":
                self.err(s.line, s.col, f"'if' condition must be bool, got '{t}'")
            self.push()
            for x in s.then_body:
                self.check_stmt(x)
            self.pop()
            self.push()
            for x in s.else_body:
                self.check_stmt(x)
            self.pop()
        elif isinstance(s, A.WhileStmt):
            t = self.check_expr(s.cond)
            if t != "bool":
                self.err(s.line, s.col, f"'while' condition must be bool, got '{t}'")
            self.push()
            for x in s.body:
                self.check_stmt(x)
            self.pop()
        elif isinstance(s, A.ReturnStmt):
            if self.current_ret is None:
                self.err(s.line, s.col, "'return' outside function")
                return
            self.has_return = True
            actual = "None" if s.expr is None else self.check_expr(s.expr)
            # bare `return;` inside non-None function: still counts but is an error
            if s.expr is None and self.current_ret != "None":
                self.err(s.line, s.col, f"function '{self.current_fn}' must return '{self.current_ret}', got empty return")
            elif not assignable(self.current_ret, actual):
                self.err(s.line, s.col, f"return type mismatch: expected '{self.current_ret}', got '{actual}'")
        elif isinstance(s, A.ExprStmt):
            self.check_expr(s.expr)
        else:
            self.err(getattr(s, "line", 0), getattr(s, "col", 0), f"unknown statement {type(s).__name__}")

    def check_expr(self, e) -> str:
        if isinstance(e, A.Literal):
            return e.lit_type
        if isinstance(e, A.Var):
            info = self.lookup(e.name)
            if info is None:
                self.err(e.line, e.col, f"undefined variable '{e.name}'")
                return "unknown"
            return info["type"]
        if isinstance(e, A.UnaryOp):
            t = self.check_expr(e.operand)
            if e.op == "not":
                if t != "bool":
                    self.err(e.line, e.col, f"'not' requires bool, got '{t}'")
                return "bool"
            if e.op == "-":
                if t not in NUMERIC and t != "unknown":
                    self.err(e.line, e.col, f"unary '-' requires numeric, got '{t}'")
                return t
        if isinstance(e, A.BinOp):
            lt = self.check_expr(e.left)
            rt = self.check_expr(e.right)
            return self.check_binop(e.op, lt, rt, e.line, e.col)
        if isinstance(e, A.Call):
            arg_ts = [self.check_expr(a) for a in e.args]
            if e.name in BUILTINS:
                params, ret, variadic = BUILTINS[e.name]
                if e.name == "print":
                    return "None"
                if e.name == "input":
                    if len(arg_ts) > 1 or (len(arg_ts) == 1 and arg_ts[0] not in ("str", "unknown")):
                        self.err(e.line, e.col, "'input' takes 0 args or 1 str prompt")
                    return "str"
                # len
                if len(arg_ts) != 1:
                    self.err(e.line, e.col, f"'{e.name}' expects {len(params)} arg(s), got {len(arg_ts)}")
                    return ret
                if not assignable(params[0], arg_ts[0]):
                    self.err(e.line, e.col, f"'{e.name}' expects '{params[0]}', got '{arg_ts[0]}'")
                return ret
            sig = self.functions.get(e.name)
            if sig is None:
                self.err(e.line, e.col, f"undefined function '{e.name}'")
                return "unknown"
            exp = sig["params"]
            if len(exp) != len(arg_ts):
                self.err(e.line, e.col, f"'{e.name}' expects {len(exp)} arg(s), got {len(arg_ts)}")
            else:
                for (pn, pt), at in zip(exp, arg_ts):
                    if not assignable(pt, at):
                        self.err(e.line, e.col, f"'{e.name}' param '{pn}' expects '{pt}', got '{at}'")
            return sig["ret"]
        self.err(getattr(e, "line", 0), getattr(e, "col", 0), f"unknown expression {type(e).__name__}")
        return "unknown"

    def check_binop(self, op, lt, rt, line, col) -> str:
        if op in ("and", "or"):
            if lt != "bool" or rt != "bool":
                self.err(line, col, f"'{op}' requires bools, got '{lt}' and '{rt}'")
            return "bool"
        if op in ("==", "!="):
            if lt != rt and not (lt in NUMERIC and rt in NUMERIC) and "unknown" not in (lt, rt):
                self.err(line, col, f"cannot compare '{lt}' with '{rt}'")
            return "bool"
        if op in ("<", "<=", ">", ">="):
            if lt not in NUMERIC and lt != "unknown":
                self.err(line, col, f"'{op}' requires numbers, got '{lt}'")
            if rt not in NUMERIC and rt != "unknown":
                self.err(line, col, f"'{op}' requires numbers, got '{rt}'")
            return "bool"
        # arithmetic
        if op == "+":
            if lt == "str" and rt == "str":
                return "str"
            if lt in NUMERIC and rt in NUMERIC:
                return "float" if "float" in (lt, rt) else "int"
            if "unknown" in (lt, rt):
                return "unknown"
            self.err(line, col, f"cannot apply '+' to '{lt}' and '{rt}'")
            return "unknown"
        if op in ("-", "*", "/", "%"):
            if op == "*" and ((lt == "str" and rt == "int") or (lt == "int" and rt == "str")):
                return "str"
            if lt in NUMERIC and rt in NUMERIC:
                if op == "/":
                    return "float"
                return "float" if "float" in (lt, rt) else "int"
            if "unknown" in (lt, rt):
                return "unknown"
            self.err(line, col, f"cannot apply '{op}' to '{lt}' and '{rt}'")
            return "unknown"
        return "unknown"
