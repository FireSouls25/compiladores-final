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


def _rewrite_with(ins: Instr, sub) -> Instr:
    """Rebuild an instruction applying `sub` to every read operand."""
    new = Instr(ins.op, ins.a, ins.b, ins.c)
    new.extra = ins.extra
    if ins.op == "assign":
        new.b = sub(ins.b)
    elif ins.op == "unop":
        new.b = sub(ins.b)
    elif ins.op == "ifFalse":
        new.a = sub(ins.a)
    elif ins.op == "return":
        new.a = sub(ins.a)
    elif ins.op == "binop":
        new.b = sub(ins.b)
        new.extra = sub(ins.extra)
    elif ins.op in ("call", "list"):
        new.b = [sub(x) for x in (ins.b or [])]
    elif ins.op in ("index", "setindex"):
        new.b = sub(ins.b)
        new.c = sub(ins.c)
    return new


def _rewrite(ins: Instr, consts: dict) -> Instr:
    """Replace operands that hold a known constant. Destinations are kept."""
    return _rewrite_with(ins, lambda v: _sub(v, consts))


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
            # Reads live in b/c/extra (for `call` and `list`, b is a list).
            for operand in (ins.b, ins.c, ins.extra):
                values = operand if isinstance(operand, list) else [operand]
                for v in values:
                    if is_temp(v):
                        used.add(v)
            if ins.op in ("return", "ifFalse", "setindex") and is_temp(ins.a):
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


def propagate_variables(code: list[Instr]) -> list[Instr]:
    """Propagate constants through variables assigned exactly once.

    A variable with a single static assignment to a constant always holds that
    value at every read (including inside loops), so every read can be replaced
    by the constant. This is the variable-level counterpart of the temporary
    propagation done by `fold_constants`.
    """
    assignments: dict[str, int] = {}
    for ins in code:
        if ins.op in ("assign", "binop", "unop", "call") and isinstance(ins.a, str):
            assignments[ins.a] = assignments.get(ins.a, 0) + 1

    consts: dict[str, object] = {}
    for ins in code:
        if (
            ins.op == "assign"
            and isinstance(ins.a, str)
            and not is_temp(ins.a)
            and assignments.get(ins.a) == 1
            and is_const(ins.b)
        ):
            consts[ins.a] = ins.b

    if not consts:
        return code
    return [
        _rewrite_with(ins, lambda v: consts.get(v, v) if isinstance(v, str) else v)
        for ins in code
    ]


def find_loops(code: list[Instr]) -> list[tuple[int, int]]:
    """Return (header, back-edge) index pairs, innermost loops first."""
    labels = {ins.a: i for i, ins in enumerate(code) if ins.op == "label"}
    backedges: dict[int, int] = {}
    for i, ins in enumerate(code):
        if ins.op != "goto":
            continue
        header = labels.get(ins.a)
        if header is None or header >= i:
            continue
        if any(code[k].op in ("func_begin", "func_end") for k in range(header, i)):
            continue
        backedges[header] = max(backedges.get(header, i), i)
    return sorted(backedges.items(), key=lambda pair: pair[1] - pair[0])


def hoist_loop_invariants(code: list[Instr], global_names=None) -> list[Instr]:
    """Loop-invariant code motion for pure `binop`/`unop` instructions.

    Division and modulo are not hoisted because they may raise at runtime.
    Instructions are only moved when all their operands are constants or
    variables/temporaries not modified inside the loop. A call to a user
    function may mutate globals, so global operands are treated as modified.
    """
    loops = find_loops(code)
    if not loops:
        return code
    header, backedge = loops[0]  # innermost loop
    body = range(header + 1, backedge)

    assigned: set[str] = set()
    temp_def: dict[str, int] = {}
    user_call = False
    for k in body:
        ins = code[k]
        if ins.op == "call" and ins.c not in ("print", "len", "input"):
            user_call = True
        if ins.op in ("assign", "binop", "unop", "call", "list", "index"):
            if isinstance(ins.a, str):
                assigned.add(ins.a)
                if is_temp(ins.a):
                    temp_def[ins.a] = k
        elif ins.op == "setindex" and isinstance(ins.a, str):
            assigned.add(ins.a)  # list mutation

    if user_call:
        if global_names is None:
            # No symbol information: any variable could be a global.
            assigned |= {
                ins.b for ins in code[header:backedge + 1]
                if isinstance(ins.b, str) and not ins.b.startswith(("@", "%"))
            }
            assigned |= {
                ins.extra for ins in code[header:backedge + 1]
                if isinstance(ins.extra, str) and not ins.extra.startswith(("@", "%"))
            }
        else:
            assigned |= set(global_names)

    hoisted: list[int] = []
    hoisted_dests: set[str] = set()
    hoisted_idx: set[int] = set()
    changed = True
    while changed:
        changed = False
        for k in body:
            if k in hoisted_idx:
                continue
            ins = code[k]
            if ins.op not in ("binop", "unop"):
                continue
            if ins.op == "binop" and ins.c in ("/", "%"):
                continue
            operands = [ins.b, ins.extra] if ins.op == "binop" else [ins.b]
            invariant = True
            for op in operands:
                if is_const(op):
                    continue
                if not isinstance(op, str):
                    continue
                if is_temp(op):
                    if op in hoisted_dests:
                        continue
                    if op in assigned or temp_def.get(op, k) >= k:
                        invariant = False
                        break
                elif op in assigned:
                    invariant = False
                    break
            if not invariant:
                continue
            hoisted.append(k)
            hoisted_idx.add(k)
            if is_temp(ins.a):
                hoisted_dests.add(ins.a)
                assigned.discard(ins.a)
            changed = True

    if not hoisted:
        return code
    moved = [code[k] for k in sorted(hoisted)]
    rest = [ins for k, ins in enumerate(code) if k > header and k not in hoisted_idx]
    return code[:header] + moved + [code[header]] + rest


def optimize(code: list[Instr], global_names=None) -> list[Instr]:
    prev = None
    while code != prev:
        prev = code
        code = propagate_variables(code)
        code = fold_constants(code)
        code = hoist_loop_invariants(code, global_names)
        code = remove_unreachable(code)
        code = remove_dead_temps(code)
    return code
