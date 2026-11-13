import builtins

from .ir_gen import Instr


class InterpError(Exception):
    pass


def decode(op):
    if isinstance(op, str) and op.startswith("@"):
        return op[1:]
    return op


class Interpreter:
    def __init__(self, code: list[Instr], global_names=None, traza=None):
        self.traza = traza
        self.marcos: list[str] = ["main"]
        self.profundidad_max = 1
        self.reservas_heap = 0
        self.code = code
        self.global_names = set(global_names or ())
        self.labels: dict[str, int] = {}
        self.funcs: dict[str, dict] = {}
        self.globals: dict = {}
        for i, ins in enumerate(code):
            if ins.op == "label":
                self.labels[ins.a] = i
            elif ins.op == "func_begin":
                j = i + 1
                while j < len(code) and code[j].op != "func_end":
                    j += 1
                self.funcs[ins.a] = {
                    "params": ins.c or [],
                    "entry": i + 1,
                    "end": j,
                }

    def run(self):
        frames: list[dict] = [self.globals]
        call_stack: list[tuple[int, str | None]] = []
        pc = 0

        def lookup(name):
            if name in frames[-1]:
                return frames[-1][name]
            if name in self.globals:
                return self.globals[name]
            raise InterpError(f"variable no definida '{name}'")

        def store(name, val):
            if len(frames) > 1 and name not in self.globals:
                frames[-1][name] = val
            else:
                self.globals[name] = val

        def value_of(operand):
            if isinstance(operand, str):
                if operand.startswith("@"):
                    return operand[1:]
                return lookup(operand)
            return operand

        while pc < len(self.code):
            ins = self.code[pc]
            op = ins.op

            if op == "func_begin":
                pc = self.funcs[ins.a]["end"] + 1
                continue

            if op == "label":
                pc += 1
                continue

            if op == "assign":
                store(ins.a, value_of(ins.b))
                pc += 1

            elif op == "binop":
                frames[-1][ins.a] = self.apply_binop(
                    ins.c, value_of(ins.b), value_of(ins.extra)
                )
                pc += 1

            elif op == "unop":
                frames[-1][ins.a] = self.apply_unop(ins.c, value_of(ins.b))
                pc += 1

            elif op == "list":
                frames[-1][ins.a] = [value_of(x) for x in (ins.b or [])]
                self.reservas_heap += 1
                self.log(f"[HEAP] reservada una lista de {len(frames[-1][ins.a])} elemento(s) (id {id(frames[-1][ins.a]) % 0x10000:#06x})")
                pc += 1

            elif op == "index":
                frames[-1][ins.a] = self.get_index(value_of(ins.b), value_of(ins.c))
                pc += 1

            elif op == "setindex":
                self.set_index(lookup(ins.a), value_of(ins.b), value_of(ins.c))
                pc += 1

            elif op == "goto":
                pc = self.labels[ins.a]

            elif op == "ifFalse":
                pc = self.labels[ins.b] if not value_of(ins.a) else pc + 1

            elif op == "call":
                args = [value_of(x) for x in (ins.b or [])]
                pc = self.do_call(ins.c, args, ins.a, frames, call_stack, pc)

            elif op == "return":
                val = value_of(ins.a) if ins.a is not None else None
                if not call_stack:
                    raise InterpError("'return' fuera de una función")
                ret_pc, dest = call_stack.pop()
                frames.pop()
                self.log(f"[STACK] pop  marco '{self.marcos[-1]}' → retorna {val!r}")
                self.marcos.pop()
                if dest is not None:
                    frames[-1][dest] = val
                pc = ret_pc

            elif op == "func_end":
                if not call_stack:
                    raise InterpError("fin de función sin llamador")
                ret_pc, dest = call_stack.pop()
                frames.pop()
                self.log(f"[STACK] pop  marco '{self.marcos[-1]}' → retorna None")
                self.marcos.pop()
                if dest is not None:
                    frames[-1][dest] = None
                pc = ret_pc

            else:
                raise InterpError(f"operación desconocida {op!r}")

        return self.globals

    def do_call(self, name, args, dest, frames, call_stack, pc):
        if name == "print":
            print(*args)
            if dest is not None:
                frames[-1][dest] = None
            return pc + 1
        if name == "len":
            if len(args) != 1 or not isinstance(args[0], (str, list)):
                raise InterpError("len() espera 1 valor str o list")
            if dest is not None:
                frames[-1][dest] = len(args[0])
            return pc + 1
        if name == "input":
            prompt = args[0] if args else ""
            try:
                s = builtins.input(prompt)
            except EOFError:
                s = ""
            if dest is not None:
                frames[-1][dest] = s
            return pc + 1
        if name not in self.funcs:
            raise InterpError(f"función no definida '{name}'")
        fn = self.funcs[name]
        if len(args) != len(fn["params"]):
            raise InterpError(
                f"'{name}' espera {len(fn['params'])} argumentos, se obtuvieron {len(args)}"
            )
        call_stack.append((pc + 1, dest))
        frames.append(dict(zip(fn["params"], args)))
        self.marcos.append(name)
        self.profundidad_max = max(self.profundidad_max, len(self.marcos))
        locales = ", ".join(f"{k}={v!r}" for k, v in frames[-1].items())
        self.log(f"[STACK] push marco '{name}' ({locales}) · profundidad {len(self.marcos)}")
        return fn["entry"]

    def log(self, msg: str):
        if self.traza is not None:
            self.traza("  " * (len(self.marcos) - 1) + msg)

    @staticmethod
    def get_index(obj, idx):
        if not isinstance(obj, (list, str)):
            raise InterpError("no se puede indexar un valor que no es list ni str")
        if not isinstance(idx, int) or isinstance(idx, bool):
            raise InterpError("el índice debe ser int")
        try:
            return obj[idx]
        except IndexError:
            raise InterpError(f"índice {idx} fuera de rango")

    @staticmethod
    def set_index(obj, idx, val):
        if not isinstance(obj, list):
            raise InterpError("no se puede asignar a un índice de un valor que no es list")
        if not isinstance(idx, int) or isinstance(idx, bool):
            raise InterpError("el índice debe ser int")
        try:
            obj[idx] = val
        except IndexError:
            raise InterpError(f"índice {idx} fuera de rango")

    @staticmethod
    def apply_binop(op, l, r):
        try:
            if op == "+":
                return l + r
            if op == "-":
                return l - r
            if op == "*":
                return l * r
            if op == "/":
                return l / r
            if op == "%":
                return l % r
            if op == "==":
                return l == r
            if op == "!=":
                return l != r
            if op == "<":
                return l < r
            if op == "<=":
                return l <= r
            if op == ">":
                return l > r
            if op == ">=":
                return l >= r
            if op == "and":
                return l and r
            if op == "or":
                return l or r
        except ZeroDivisionError:
            raise InterpError("división por cero")
        except TypeError as e:
            raise InterpError(f"operandos inválidos para '{op}': {e}")
        raise InterpError(f"operador desconocido {op!r}")

    @staticmethod
    def apply_unop(op, v):
        if op == "-":
            try:
                return -v
            except TypeError:
                raise InterpError(f"el '-' unario requiere un número, se obtuvo {v!r}")
        if op == "not":
            return not v
        raise InterpError(f"operador unario desconocido {op!r}")
