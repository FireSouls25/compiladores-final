"""Phase 5: IR interpreter (iterative evaluation of the TAC).

The evaluator keeps an explicit call stack, so deep recursion in the source
language does not consume Python's recursion limit.
"""
import builtins

from .ir_gen import Instr


class InterpError(Exception):
    pass


def decode(op):
    """Decode an IR string constant (`@text` -> `text`)."""
    if isinstance(op, str) and op.startswith("@"):
        return op[1:]
    return op


class Interpreter:
    def __init__(self, code: list[Instr], global_names=None):
        self.code = code
        self.global_names = set(global_names or ())
        self.labels: dict[str, int] = {}
        self.funcs: dict[str, dict] = {}
        self.globals: dict = {}  # frame 0
        for i, ins in enumerate(code):
            if ins.op == "label":
                self.labels[ins.a] = i
            elif ins.op == "func_begin":
                # Functions are not nested: the first func_end closes this one.
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
        call_stack: list[tuple[int, str | None]] = []  # (return pc, dest temp)
        pc = 0

        def lookup(name):
            if name in frames[-1]:
                return frames[-1][name]
            if name in self.globals:
                return self.globals[name]
            raise InterpError(f"runtime: undefined variable '{name}'")

        def store(name, val):
            # Inside a function, locals live in the top frame; writing an
            # existing global mutates the global. At top level frame 0 *is*
            # the globals dict.
            if len(frames) > 1 and name not in self.globals:
                frames[-1][name] = val
            else:
                self.globals[name] = val

        def value_of(operand):
            if isinstance(operand, str):
                if operand.startswith("@"):
                    return operand[1:]          # string constant
                return lookup(operand)          # variable or %temp
            return operand                      # int / float / bool / None

        while pc < len(self.code):
            ins = self.code[pc]
            op = ins.op

            if op == "func_begin":
                # Sequential execution skips bodies; calls jump to entry.
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
                    raise InterpError("runtime: 'return' outside function")
                ret_pc, dest = call_stack.pop()
                frames.pop()
                if dest is not None:
                    frames[-1][dest] = val
                pc = ret_pc

            elif op == "func_end":
                # Falling off a function returns None (void functions only;
                # semantic analysis guarantees non-void functions return).
                if not call_stack:
                    raise InterpError("runtime: fell off a function without caller")
                ret_pc, dest = call_stack.pop()
                frames.pop()
                if dest is not None:
                    frames[-1][dest] = None
                pc = ret_pc

            else:
                raise InterpError(f"runtime: unknown op {op!r}")

        return self.globals

    def do_call(self, name, args, dest, frames, call_stack, pc):
        if name == "print":
            print(*args)
            if dest is not None:
                frames[-1][dest] = None
            return pc + 1
        if name == "len":
            if len(args) != 1 or not isinstance(args[0], str):
                raise InterpError("runtime: len() expects 1 str")
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
            raise InterpError(f"runtime: undefined function '{name}'")
        fn = self.funcs[name]
        if len(args) != len(fn["params"]):
            raise InterpError(
                f"runtime: '{name}' expects {len(fn['params'])} args, got {len(args)}"
            )
        call_stack.append((pc + 1, dest))
        frames.append(dict(zip(fn["params"], args)))
        return fn["entry"]

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
            raise InterpError("runtime: division by zero")
        except TypeError as e:
            raise InterpError(f"runtime: bad operands for '{op}': {e}")
        raise InterpError(f"runtime: unknown operator {op!r}")

    @staticmethod
    def apply_unop(op, v):
        if op == "-":
            try:
                return -v
            except TypeError:
                raise InterpError(f"runtime: unary '-' requires a number, got {v!r}")
        if op == "not":
            return not v
        raise InterpError(f"runtime: unknown unary {op!r}")
