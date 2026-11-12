"""Phase 4.5: IR optimizer (optional, enabled with --opt).

Runs a small, safe set of classic TAC optimizations to a fixed point:

* constant folding        `%t1 = 2 + 3`        -> `%t1 = 5`
* constant propagation    `x = %t1 * 2`        -> `x = 5 * 2` -> `x = 10`
* constant conditional    `ifFalse True goto L` -> removed
* unreachable code        instructions after `goto`/`return` up to the next label
* dead temporaries        `%t1 = ...` never read -> removed

Calls are never removed (they may have side effects such as `print`).
"""
from .ir_gen import Instr
from .interp import Interpreter, InterpError


def is_temp(v) -> bool:
    return isinstance(v, str) and v.startswith("%")


def is_str_const(v) -> bool:
    return isinstance(v, str) and v.startswith("@")


def is_const(v) -> bool:
    return not isinstance(v, str) or is_str_const(v)


def const_value(v):
    return v[1:] if is_str_const(v) else v


def encode(v):
    return "@" + v if isinstance(v, str) else v


def _sub(v, consts):
    return consts.get(v, v) if is_temp(v) else v


def _rewrite(ins: Instr, consts: dict) -> Instr:
    """Replace operands that hold a known constant. Destinations are kept."""
    new = Instr(ins.op, ins.a, ins.b, ins.c)
    new.extra = ins.extra
    if ins.op == "assign":
        new.b = _sub(ins.b, consts)
    elif ins.op == "unop":
        new.b = _sub(ins.b, consts)
    elif ins.op == "ifFalse":
        new.a = _sub(ins.a, consts)
    elif ins.op == "return":
        new.a = _sub(ins.a, consts)
    elif ins.op == "binop":
        new.b = _sub(ins.b, consts)
        new.extra = _sub(ins.extra, consts)
    elif ins.op == "call":
        new.b = [_sub(x, consts) for x in (ins.b or [])]
    return new


def fold_constants(code: list[Instr]) -> list[Instr]:
    """Fold constant operations and forward-propagate constant temporaries."""
    consts: dict = {}
    out: list[Instr] = []
    for ins in code:
        ins = _rewrite(ins, consts)

        if ins.op == "binop" and is_const(ins.b) and is_const(ins.extra):
            try:
                val = Interpreter.apply_binop(
                    ins.c, const_value(ins.b), const_value(ins.extra)
                )
            except InterpError:
                pass  # leave it for runtime (e.g. division by zero)
            else:
                ins = Instr("assign", ins.a, encode(val))
        elif ins.op == "unop" and is_const(ins.b):
            try:
                val = Interpreter.apply_unop(ins.c, const_value(ins.b))
            except InterpError:
                pass
            else:
                ins = Instr("assign", ins.a, encode(val))

        if ins.op == "assign" and is_const(ins.b) and is_temp(ins.a):
            consts[ins.a] = ins.b

        if ins.op == "ifFalse" and is_const(ins.a):
            if const_value(ins.a):
                continue  # condition always true -> fall through
            ins = Instr("goto", ins.b)  # condition always false -> jump

        out.append(ins)
    return out


def remove_unreachable(code: list[Instr]) -> list[Instr]:
    out: list[Instr] = []
    dead = False
    for ins in code:
        if dead:
            if ins.op in ("label", "func_begin", "func_end"):
                dead = False
            else:
                continue
        out.append(ins)
        if ins.op in ("goto", "return"):
            dead = True
    return out


def remove_dead_temps(code: list[Instr]) -> list[Instr]:
    """Drop definitions of temporaries that are never read."""
    changed = True
    while changed:
        changed = False
        used: set = set()
        for ins in code:
            for operand in (ins.b, ins.extra):
                if is_temp(operand):
                    used.add(operand)
            for arg in ins.b if ins.op == "call" and isinstance(ins.b, list) else []:
                if is_temp(arg):
                    used.add(arg)
            if ins.op in ("return", "ifFalse") and is_temp(ins.a):
                used.add(ins.a)
        kept = []
        for ins in code:
            if (
                ins.op in ("assign", "binop", "unop")
                and is_temp(ins.a)
                and ins.a not in used
            ):
                changed = True
                continue
            kept.append(ins)
        code = kept
    return code


def optimize(code: list[Instr]) -> list[Instr]:
    prev = None
    while code != prev:
        prev = code
        code = fold_constants(code)
        code = remove_unreachable(code)
        code = remove_dead_temps(code)
    return code
