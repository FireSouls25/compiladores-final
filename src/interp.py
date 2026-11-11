"""Phase 5: IR interpreter (tree-walk over TAC so .mb files actually run)."""
from .ir_gen import Instr, const


def decode(op):
    if isinstance(op, str) and op.startswith("@"):
        return op[1:]
    return op


class InterpError(Exception):
    pass


class Interpreter:
    def __init__(self, code: list[Instr]):
        self.code = code
        self.labels: dict[str, int] = {}
        self.funcs: dict[str, dict] = {}
        self.globals: dict = {}
        for i, ins in enumerate(code):
            if ins.op == "label":
                self.labels[ins.a] = i
            elif ins.op == "func_begin":
                # find matching func_end
                depth = 1
                j = i + 1
                while j < len(code):
                    if code[j].op == "func_begin":
                        depth += 1
                    elif code[j].op == "func_end" and code[j].a == ins.a:
                        depth -= 1
                        if depth == 0:
                            break
                    j += 1
                self.funcs[ins.a] = {"params": ins.c or [], "entry": i + 1, "end": j}

    def run(self):
        frames: list[dict] = [{}]  # frame 0 = top-level locals (== globals scope)
        call_stack: list[tuple[int, str | None, dict]] = []  # (ret_pc, dest, caller_frame)
        pc = 0
        # skip function bodies at top level: jump over func_begin..func_end
        in_func = lambda: len(call_stack) > 0 or cur_func is not None
        cur_func: str | None = None

        def lookup(name):
            if name in frames[-1]:
                return frames[-1][name]
            if name in self.globals:
                return self.globals[name]
            raise InterpError(f"runtime: undefined variable '{name}'")

        def store(name, val):
            # inside a function: locals first, else globals if exists, else locals
            if len(call_stack) > 0 or cur_func is not None:
                if name in frames[-1]:
                    frames[-1][name] = val
                elif name in self.globals:
                    self.globals[name] = val
                else:
                    frames[-1][name] = val
            else:
                # top-level: everything is global
                if name in frames[-1]:
                    frames[-1][name] = val
                self.globals[name] = val
                frames[-1][name] = val

        def value_of(operand):
            if isinstance(operand, str) and operand.startswith("@"):
                return operand[1:]
            if isinstance(operand, str) and operand[:1].isalpha() or isinstance(operand, str) and operand.startswith("_"):
                # variable or temp
                return lookup(operand)
            return operand

        while pc < len(self.code):
            ins = self.code[pc]
            op = ins.op
            if op == "func_begin":
                if call_stack and pc == call_stack[-1][0] - 1:
                    pass  # entered via call, continue
                else:
                    # skip over function body when at top level
                    pc = self.funcs[ins.a]["end"] + 1
                    continue
            elif op == "func_end":
                # implicit fall-off: return None
                if not call_stack:
                    raise InterpError("runtime: fell off function without caller")
                ret_pc, dest, caller = call_stack.pop()
                frames.pop()
                cur_func = None if not call_stack else cur_func
                if dest is not None:
                    # store None into caller frame temporarily
                    frames[-1][dest] = None
                    if dest in caller:
                        pass
                pc = ret_pc
                continue
            elif op == "label":
                pc += 1
                continue
            elif op == "assign":
                store(ins.a, value_of(ins.b))
                pc += 1
            elif op == "binop":
                l = value_of(ins.b)
                r = value_of(ins.extra)
                frames[-1][ins.a] = self.apply_binop(ins.c, l, r)
                if cur_func is None and not call_stack:
                    self.globals[ins.a] = frames[-1][ins.a]
                pc += 1
            elif op == "unop":
                v = value_of(ins.b)
                frames[-1][ins.a] = self.apply_unop(ins.c, v)
                if cur_func is None and not call_stack:
                    self.globals[ins.a] = frames[-1][ins.a]
                pc += 1
            elif op == "goto":
                pc = self.labels[ins.a]
            elif op == "ifFalse":
                c = value_of(ins.a)
                pc = self.labels[ins.b] if not c else pc + 1
            elif op == "call":
                args = [value_of(x) for x in (ins.b or [])]
                pc = self.do_call(ins.c, args, ins.a, frames, call_stack, store, pc)
                # do_call returns next pc (either next instr or func entry)
            elif op == "return":
                val = value_of(ins.a) if ins.a is not None else None
                if not call_stack:
                    if cur_func is None:
                        raise InterpError("runtime: 'return' outside function")
                    # returning from top-level wrapped? shouldn't happen
                    pc += 1
                else:
                    ret_pc, dest, caller = call_stack.pop()
                    frames.pop()
                    cur_func = None if not call_stack else cur_func
                    if dest is not None:
                        frames[-1][dest] = val
                        if not call_stack:
                            self.globals[dest] = val
                    pc = ret_pc
            else:
                raise InterpError(f"runtime: unknown op {op!r}")
        return self.globals

    # -- helpers --
    def do_call(self, name, args, dest, frames, call_stack, store_fn, pc):
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
                s = __builtins__.input(prompt) if not isinstance(__builtins__, dict) else __builtins__["input"](prompt)
            except EOFError:
                s = ""
            if dest is not None:
                frames[-1][dest] = s
            return pc + 1
        if name not in self.funcs:
            raise InterpError(f"runtime: undefined function '{name}'")
        fn = self.funcs[name]
        if len(args) != len(fn["params"]):
            raise InterpError(f"runtime: '{name}' expects {len(fn['params'])} args, got {len(args)}")
        call_stack.append((pc + 1, dest, frames[-1]))
        new_frame = dict(zip(fn["params"], args))
        frames.append(new_frame)
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
        except TypeError as e:
            raise InterpError(f"runtime: bad operands for '{op}': {e}")
        raise InterpError(f"runtime: unknown operator {op!r}")

    @staticmethod
    def apply_unop(op, v):
        if op == "-":
            return -v
        if op == "not":
            return not v
        raise InterpError(f"runtime: unknown unary {op!r}")
