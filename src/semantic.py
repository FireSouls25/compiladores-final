from . import ast_nodes as A
from .suggest import closest


class SemanticError(Exception):
    pass


NUMERIC = {"int", "float"}

BUILTINS = {
    "print": (["unknown"], "None", True),
    "len": (["str"], "int", False),
    "input": ([], "str", True),
}


def assignable(expected: str, actual: str) -> bool:
    if expected == actual:
        return True
    if expected == "unknown" or actual == "unknown":
        return True
    if expected == "float" and actual == "int":
        return True
    return False


def _stmt_always_returns(s) -> bool:
    if isinstance(s, A.ReturnStmt):
        return True
    if isinstance(s, A.Block):
        return _block_always_returns(s.stmts)
    if isinstance(s, A.IfStmt):
        return (
            bool(s.else_body)
            and _block_always_returns(s.then_body)
            and _block_always_returns(s.else_body)
        )
    if isinstance(s, A.WhileStmt):
        cond = s.cond
        return (
            isinstance(cond, A.Literal)
            and cond.lit_type == "bool"
            and cond.value is True
            and _block_always_returns(s.body)
        )
    return False


def _block_always_returns(stmts: list) -> bool:
    return any(_stmt_always_returns(s) for s in stmts)


def _top_level_globals(items: list) -> list[str]:
    names: list[str] = []

    def walk(stmts):
        for s in stmts:
            if isinstance(s, A.LetStmt):
                names.append(getattr(s, "resolved_name", s.name))
            elif isinstance(s, A.Block):
                walk(s.stmts)
            elif isinstance(s, A.ForStmt) and isinstance(s.init, A.LetStmt):
                names.append(getattr(s.init, "resolved_name", s.init.name))

    walk(items)
    return names


def _top_level_names(items: list) -> set[str]:
    names: set[str] = set()

    def walk(stmts):
        for s in stmts:
            if isinstance(s, A.LetStmt):
                names.add(s.name)
            elif isinstance(s, A.Block):
                walk(s.stmts)
            elif isinstance(s, A.ForStmt) and isinstance(s.init, A.LetStmt):
                names.add(s.init.name)

    walk(items)
    return names


class SemanticAnalyzer:
    def __init__(self, traza: list | None = None):
        self.traza = traza
        self.scope_names: list[str] = ["global"]
        self.errors: list[str] = []
        self.scopes: list[dict] = [{}]
        self.functions: dict = {}
        self.current_ret: str | None = None
        self.current_fn: str | None = None
        self.has_return: bool = False
        self.loop_depth: int = 0
        self._fresh = 0
        self.global_names: set[str] = set()

    def log(self, msg: str):
        if self.traza is not None:
            self.traza.append("  " * (len(self.scopes) - 1) + msg)

    def push(self, nombre: str = "bloque"):
        self.log(f"→ Entrando al ámbito '{nombre}'")
        self.scopes.append({})
        self.scope_names.append(nombre)

    def pop(self):
        nombre = self.scope_names.pop()
        locales = ", ".join(self.scopes.pop()) or "ninguna"
        self.log(f"← Saliendo del ámbito '{nombre}' (se destruyen: {locales})")

    def check_assignable(self, expected: str, actual: str) -> bool:
        ok = assignable(expected, actual)
        if ok and expected == "float" and actual == "int":
            self.log("[COERCIÓN] int → float (conversión implícita segura)")
        return ok

    def _unique(self, name: str) -> str:
        self._fresh += 1
        return f"{name}${self._fresh}"

    def declare(self, name, info, line, col):
        if name in BUILTINS:
            self.err(line, col, f"no se puede declarar '{name}': es una función integrada")
        if name in self.functions:
            self.err(line, col, f"no se puede declarar '{name}': ya es una función")
        if name in self.scopes[-1]:
            self.err(line, col, f"redeclaración de '{name}' en el mismo ámbito")
            return {**info, "resolved": name}
        shadowed = self.lookup(name) is not None or (
            self.current_fn is not None and name in self.global_names
        )
        info = {**info, "resolved": self._unique(name) if shadowed else name}
        self.scopes[-1][name] = info
        extra = f" → renombrada a {info['resolved']} (sombrea a otra)" if shadowed else ""
        self.log(f"[DECLARACIÓN] {name}: {info['type']} en ámbito '{self.scope_names[-1]}'{extra}")
        return info

    def lookup(self, name):
        for s in reversed(self.scopes):
            if name in s:
                return s[name]
        return None

    def lookup_scope(self, name) -> str:
        for s, nombre in zip(reversed(self.scopes), reversed(self.scope_names)):
            if name in s:
                return nombre
        return "?"

    def err(self, line, col, msg):
        self.log(f"[ERROR] {line}:{col}: {msg}")
        self.errors.append(f"{line}:{col}: {msg}")

    def visible_names(self) -> set[str]:
        names: set[str] = set(BUILTINS)
        for scope in self.scopes:
            names |= set(scope)
        return names

    def undefined_variable(self, name, line, col):
        msg = f"variable no definida '{name}'"
        suggestion = closest(name, self.visible_names())
        if suggestion is not None:
            msg += f" (¿quisiste decir '{suggestion}'?)"
        elif name in self.functions:
            msg += f" (¿quisiste llamar a '{name}(...)'?)"
        self.err(line, col, msg)

    def analyze(self, prog: A.Program) -> dict:
        self.global_names = _top_level_names(prog.items)
        self.log("Pasada 1: se registran las firmas de las funciones (permite llamarlas antes de definirlas)")
        for it in prog.items:
            if isinstance(it, A.FuncDef):
                if it.name in self.functions or it.name in BUILTINS:
                    self.err(it.line, it.col, f"redefinición de la función '{it.name}'")
                else:
                    self.functions[it.name] = {
                        "params": [(p.name, p.ann or "unknown") for p in it.params],
                        "ret": it.ret,
                    }
                    firma = ", ".join(f"{n}: {t}" for n, t in self.functions[it.name]["params"])
                    self.log(f"  función {it.name}({firma}) -> {it.ret}")
        self.log("Pasada 2: se recorren los cuerpos de las funciones y las sentencias")
        for it in prog.items:
            if isinstance(it, A.FuncDef):
                self.check_func(it)
            else:
                self.check_stmt(it)
        if self.errors:
            raise SemanticError("\n".join(self.errors))
        return {"functions": self.functions, "globals": _top_level_globals(prog.items)}

    def check_func(self, fn: A.FuncDef):
        self.push(f"función {fn.name}")
        self.current_ret = fn.ret
        self.current_fn = fn.name
        self.has_return = False
        self.loop_depth = 0
        seen = set()
        for p in fn.params:
            if p.name in seen:
                self.err(p.line, p.col, f"parámetro duplicado '{p.name}'")
            if p.name in BUILTINS:
                self.err(p.line, p.col, f"el parámetro '{p.name}' oculta una función integrada")
            if p.name in self.functions:
                self.err(p.line, p.col, f"el parámetro '{p.name}' oculta una función")
            seen.add(p.name)
            resolved = self._unique(p.name) if p.name in self.global_names else p.name
            p.resolved = resolved
            self.scopes[-1][p.name] = {
                "kind": "param",
                "type": p.ann or "unknown",
                "resolved": resolved,
            }
            self.log(f"[DECLARACIÓN] {p.name}: {p.ann or 'unknown'} (parámetro)")
        for s in fn.body:
            self.check_stmt(s)
        if fn.ret != "None" and not _block_always_returns(fn.body):
            self.err(
                fn.line,
                fn.col,
                f"la función '{fn.name}' debe retornar '{fn.ret}' en todos los caminos",
            )
        self.pop()
        self.current_ret = None
        self.current_fn = None

    def check_stmt(self, s):
        if isinstance(s, A.Block):
            self.push("bloque { }")
            for x in s.stmts:
                self.check_stmt(x)
            self.pop()
            return
        if isinstance(s, A.LetStmt):
            t = self.check_expr(s.expr)
            if s.ann:
                if not self.check_assignable(s.ann, t):
                    self.err(s.line, s.col, f"no se puede asignar '{t}' a '{s.ann}' en 'let {s.name}'")
                info = self.declare(s.name, {"kind": "var", "type": s.ann}, s.line, s.col)
            else:
                info = self.declare(s.name, {"kind": "var", "type": t}, s.line, s.col)
            s.resolved_name = info["resolved"]
        elif isinstance(s, A.AssignStmt):
            info = self.lookup(s.name)
            if info is None:
                self.undefined_variable(s.name, s.line, s.col)
                self.check_expr(s.expr)
            else:
                s.resolved = info["resolved"]
                t = self.check_expr(s.expr)
                if not self.check_assignable(info["type"], t):
                    self.err(s.line, s.col, f"no se puede asignar '{t}' a la variable '{s.name}' de tipo '{info['type']}'")
        elif isinstance(s, A.IfStmt):
            t = self.check_expr(s.cond)
            if t != "bool":
                self.err(s.line, s.col, f"la condición del 'if' debe ser bool, se obtuvo '{t}'")
            else:
                self.log("[TIPOS] condición del if: bool ✓")
            self.push("if")
            for x in s.then_body:
                self.check_stmt(x)
            self.pop()
            if s.else_body:
                self.push("else")
                for x in s.else_body:
                    self.check_stmt(x)
                self.pop()
        elif isinstance(s, A.WhileStmt):
            t = self.check_expr(s.cond)
            if t != "bool":
                self.err(s.line, s.col, f"la condición del 'while' debe ser bool, se obtuvo '{t}'")
            self.push("while")
            self.loop_depth += 1
            for x in s.body:
                self.check_stmt(x)
            self.loop_depth -= 1
            self.pop()
        elif isinstance(s, A.ForStmt):
            self.push("for")
            self.check_stmt(s.init)
            t = self.check_expr(s.cond)
            if t != "bool":
                self.err(s.line, s.col, f"la condición del 'for' debe ser bool, se obtuvo '{t}'")
            self.check_stmt(s.update)
            self.loop_depth += 1
            for x in s.body:
                self.check_stmt(x)
            self.loop_depth -= 1
            self.pop()
        elif isinstance(s, A.BreakStmt):
            if self.loop_depth == 0:
                self.err(s.line, s.col, "'break' fuera de un ciclo")
        elif isinstance(s, A.ContinueStmt):
            if self.loop_depth == 0:
                self.err(s.line, s.col, "'continue' fuera de un ciclo")
        elif isinstance(s, A.SetIndexStmt):
            tt = self.check_expr(s.target)
            it = self.check_expr(s.index)
            self.check_expr(s.expr)
            if tt not in ("list", "unknown"):
                self.err(s.line, s.col, f"no se puede asignar a un índice de '{tt}'")
            if it not in ("int", "unknown"):
                self.err(s.line, s.col, f"el índice de la lista debe ser int, se obtuvo '{it}'")
        elif isinstance(s, A.ReturnStmt):
            if self.current_ret is None:
                self.err(s.line, s.col, "'return' fuera de una función")
                return
            self.has_return = True
            actual = "None" if s.expr is None else self.check_expr(s.expr)
            if s.expr is None and self.current_ret != "None":
                self.err(s.line, s.col, f"la función '{self.current_fn}' debe retornar '{self.current_ret}', pero el return está vacío")
            elif not self.check_assignable(self.current_ret, actual):
                self.err(s.line, s.col, f"tipo de retorno incorrecto: se esperaba '{self.current_ret}', se obtuvo '{actual}'")
        elif isinstance(s, A.ExprStmt):
            self.check_expr(s.expr)
        else:
            self.err(getattr(s, "line", 0), getattr(s, "col", 0), f"sentencia desconocida {type(s).__name__}")

    def check_expr(self, e) -> str:
        if isinstance(e, A.Literal):
            return e.lit_type
        if isinstance(e, A.Var):
            info = self.lookup(e.name)
            if info is None:
                self.undefined_variable(e.name, e.line, e.col)
                return "unknown"
            e.resolved = info["resolved"]
            self.log(f"[USO] {e.name} → {info['type']} (encontrada en ámbito '{self.lookup_scope(e.name)}')")
            return info["type"]
        if isinstance(e, A.ListLit):
            for item in e.items:
                self.check_expr(item)
            return "list"
        if isinstance(e, A.Index):
            tt = self.check_expr(e.target)
            it = self.check_expr(e.index)
            if it not in ("int", "unknown"):
                self.err(e.line, e.col, f"el índice debe ser int, se obtuvo '{it}'")
            if tt == "str":
                return "str"
            if tt == "list":
                return "unknown"
            if tt != "unknown":
                self.err(e.line, e.col, f"no se puede indexar un valor de tipo '{tt}'")
            return "unknown"
        if isinstance(e, A.UnaryOp):
            t = self.check_expr(e.operand)
            if e.op == "not":
                if t != "bool":
                    self.err(e.line, e.col, f"'not' requiere bool, se obtuvo '{t}'")
                return "bool"
            if e.op == "-":
                if t not in NUMERIC and t != "unknown":
                    self.err(e.line, e.col, f"el '-' unario requiere un número, se obtuvo '{t}'")
                return t
        if isinstance(e, A.BinOp):
            lt = self.check_expr(e.left)
            rt = self.check_expr(e.right)
            res = self.check_binop(e.op, lt, rt, e.line, e.col)
            if res != "unknown" or "unknown" in (lt, rt):
                self.log(f"[TIPOS] {lt} {e.op} {rt} → {res}")
            return res
        if isinstance(e, A.Call):
            arg_ts = [self.check_expr(a) for a in e.args]
            if e.name in BUILTINS:
                params, ret, variadic = BUILTINS[e.name]
                if e.name == "print":
                    return "None"
                if e.name == "input":
                    if len(arg_ts) > 1 or (len(arg_ts) == 1 and arg_ts[0] not in ("str", "unknown")):
                        self.err(e.line, e.col, "'input' recibe 0 argumentos o 1 mensaje de tipo str")
                    return "str"
                if e.name == "len":
                    if len(arg_ts) != 1:
                        self.err(e.line, e.col, f"'len' espera 1 argumento, se obtuvieron {len(arg_ts)}")
                    elif arg_ts[0] not in ("str", "list", "unknown"):
                        self.err(e.line, e.col, f"'len' espera 'str' o 'list', se obtuvo '{arg_ts[0]}'")
                    return "int"
            sig = self.functions.get(e.name)
            if sig is None:
                msg = f"función no definida '{e.name}'"
                suggestion = closest(
                    e.name, list(self.functions) + list(BUILTINS)
                )
                if suggestion is not None:
                    msg += f" (¿quisiste decir '{suggestion}'?)"
                elif self.lookup(e.name) is not None:
                    msg += f" (la variable '{e.name}' no es invocable)"
                self.err(e.line, e.col, msg)
                return "unknown"
            exp = sig["params"]
            if len(exp) != len(arg_ts):
                self.err(e.line, e.col, f"'{e.name}' espera {len(exp)} argumento(s), se obtuvieron {len(arg_ts)}")
            else:
                self.log(f"[LLAMADA] {e.name}({', '.join(arg_ts)}) → {sig['ret']}")
                for (pn, pt), at in zip(exp, arg_ts):
                    if not self.check_assignable(pt, at):
                        self.err(e.line, e.col, f"el parámetro '{pn}' de '{e.name}' espera '{pt}', se obtuvo '{at}'")
            return sig["ret"]
        self.err(getattr(e, "line", 0), getattr(e, "col", 0), f"expresión desconocida {type(e).__name__}")
        return "unknown"

    def check_binop(self, op, lt, rt, line, col) -> str:
        if op in ("and", "or"):
            if lt != "bool" or rt != "bool":
                self.err(line, col, f"'{op}' requiere bool, se obtuvo '{lt}' y '{rt}'")
            return "bool"
        if op in ("==", "!="):
            if lt != rt and not (lt in NUMERIC and rt in NUMERIC) and "unknown" not in (lt, rt):
                self.err(line, col, f"no se puede comparar '{lt}' con '{rt}'")
            return "bool"
        if op in ("<", "<=", ">", ">="):
            if lt not in NUMERIC and lt != "unknown":
                self.err(line, col, f"'{op}' requiere números, se obtuvo '{lt}'")
            if rt not in NUMERIC and rt != "unknown":
                self.err(line, col, f"'{op}' requiere números, se obtuvo '{rt}'")
            return "bool"
        if op == "+":
            if lt == "str" and rt == "str":
                return "str"
            if lt in NUMERIC and rt in NUMERIC:
                return "float" if "float" in (lt, rt) else "int"
            if "unknown" in (lt, rt):
                return "unknown"
            self.err(line, col, f"no se puede aplicar '+' a '{lt}' y '{rt}'")
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
            self.err(line, col, f"no se puede aplicar '{op}' a '{lt}' y '{rt}'")
            return "unknown"
        return "unknown"
