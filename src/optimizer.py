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
    """Remove instructions that no control-flow path can reach.

    Every function body is a root (it may be called at any time), top-level
    code starts at index 0, and `ifFalse`/`goto` add their label as an edge.
    """
    if not code:
        return code
    labels = {ins.a: i for i, ins in enumerate(code) if ins.op == "label"}
    func_end: dict[int, int] = {}
    for i, ins in enumerate(code):
        if ins.op == "func_begin":
            j = i + 1
            while j < len(code) and code[j].op != "func_end":
                j += 1
            func_end[i] = j

    roots = [0]
    for i, ins in enumerate(code):
        if ins.op == "func_begin":
            roots.append(i)          # keep the marker itself
            roots.append(i + 1)      # body entry
            if i in func_end:
                roots.append(func_end[i])  # always keep its matching func_end

    reachable: set[int] = set()
    work = list(roots)
    while work:
        i = work.pop()
        if i < 0 or i >= len(code) or i in reachable:
            continue
        reachable.add(i)
        ins = code[i]
        if ins.op == "goto":
            work.append(labels.get(ins.a, i + 1))
        elif ins.op == "ifFalse":
            work.append(labels.get(ins.b, i + 1))
            work.append(i + 1)
        elif ins.op in ("return", "func_end"):
            pass  # no fallthrough
        elif ins.op == "func_begin":
            work.append(func_end.get(i, i + 1) + 1)  # sequential skip
        else:
            work.append(i + 1)

    return [ins for i, ins in enumerate(code) if i in reachable]


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
