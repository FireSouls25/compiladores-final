from . import ast_nodes as A
from . import tokens as T
from .lexer import Lexer, LexError
from .parser import Parser, ParseError
from .semantic import SemanticAnalyzer, SemanticError
from .ir_gen import IRGenerator, fmt
from .optimizer import optimize
from .asm_gen import generar_asm
from .interp import Interpreter, InterpError
from .diagnostics import format_diagnostics, format_runtime_error

ANCHO = 72
LIMITE_EVENTOS = 60

PALABRAS = set(T.KEYWORDS.values())
LITERALES = {T.INT_LIT, T.FLOAT_LIT, T.STRING_LIT}


def titulo(n, nombre: str, pregunta: str, detalle: str):
    print()
    print("═" * ANCHO)
    print(f" FASE {n} · {nombre}")
    print(f" Pregunta que responde: {pregunta}")
    print("═" * ANCHO)
    print(detalle)
    print()


def resultado(texto: str):
    print(f"\n✔ {texto}")


def detenida(n, nombre: str):
    print(f"\n✘ La compilación se detuvo en la FASE {n} ({nombre}).")
    print("  Las fases siguientes no se ejecutan porque reciben una entrada inválida.\n")


def categoria(tok) -> str:
    if tok.type in PALABRAS:
        return "palabra reservada"
    if tok.type == T.IDENT:
        return "identificador"
    if tok.type in LITERALES:
        return "literal"
    if tok.type == T.EOF:
        return "fin de archivo"
    return "operador/delimitador"


def fase_lexica(source: str, path: str):
    titulo(1, "ANÁLISIS LÉXICO (lexer)", "¿las palabras están bien escritas? (ortografía)",
           f"Entrada: {len(source)} caracteres de texto plano.\n"
           "El lexer recorre el texto de izquierda a derecha, descarta espacios y\n"
           "comentarios y agrupa los caracteres en tokens (tipo + lexema + posición).")
    try:
        toks = Lexer(source).tokenize()
    except LexError as e:
        print(format_diagnostics(path, source, str(e), "léxico"))
        detenida(1, "léxica")
        return None
    print(f"  {'#':>3}  {'TOKEN':<11} {'LEXEMA':<18} {'POSICIÓN':<9} CATEGORÍA")
    print(f"  {'─' * 3}  {'─' * 11} {'─' * 18} {'─' * 9} {'─' * 20}")
    cuenta: dict[str, int] = {}
    for k, t in enumerate(toks, 1):
        cat = categoria(t)
        cuenta[cat] = cuenta.get(cat, 0) + 1
        lex = repr(t.lexeme) if t.lexeme else "''"
        print(f"  {k:>3}  {t.type:<11} {lex:<18} {f'{t.line}:{t.col}':<9} {cat}")
    resumen = ", ".join(f"{v} {k}" for k, v in cuenta.items())
    resultado(f"{len(toks)} tokens ({resumen}).")
    return toks


def etiqueta(n) -> str:
    if isinstance(n, A.Program):
        return "Programa"
    if isinstance(n, A.FuncDef):
        ps = ", ".join(f"{p.name}: {p.ann or 'unknown'}" for p in n.params)
        return f"Función {n.name}({ps}) -> {n.ret}"
    if isinstance(n, A.LetStmt):
        return f"Let {n.name}" + (f": {n.ann}" if n.ann else "")
    if isinstance(n, A.AssignStmt):
        return f"Asignación {n.name} ="
    if isinstance(n, A.SetIndexStmt):
        return "Asignación por índice"
    if isinstance(n, A.IfStmt):
        return "If"
    if isinstance(n, A.WhileStmt):
        return "While"
    if isinstance(n, A.ForStmt):
        return "For"
    if isinstance(n, A.ReturnStmt):
        return "Return"
    if isinstance(n, A.BreakStmt):
        return "Break"
    if isinstance(n, A.ContinueStmt):
        return "Continue"
    if isinstance(n, A.ExprStmt):
        return "Sentencia-expresión"
    if isinstance(n, A.Block):
        return "Bloque { }"
    if isinstance(n, A.BinOp):
        return f"OpBinaria '{n.op}'"
    if isinstance(n, A.UnaryOp):
        return f"OpUnaria '{n.op}'"
    if isinstance(n, A.Literal):
        return f"Literal {n.value!r} ({n.lit_type})"
    if isinstance(n, A.Var):
        return f"Variable {n.name}"
    if isinstance(n, A.Call):
        return f"Llamada {n.name}(…)"
    if isinstance(n, A.ListLit):
        return "Lista [ ]"
    if isinstance(n, A.Index):
        return "Índice [ ]"
    return type(n).__name__


def hijos(n) -> list:
    if isinstance(n, A.Program):
        return n.items
    if isinstance(n, A.FuncDef):
        return n.body
    if isinstance(n, (A.LetStmt, A.AssignStmt, A.ExprStmt)):
        return [n.expr]
    if isinstance(n, A.ReturnStmt):
        return [n.expr] if n.expr is not None else []
    if isinstance(n, A.SetIndexStmt):
        return [("destino", n.target), ("índice", n.index), ("valor", n.expr)]
    if isinstance(n, A.IfStmt):
        out = [("condición", n.cond), ("entonces", n.then_body)]
        if n.else_body:
            out.append(("si no", n.else_body))
        return out
    if isinstance(n, A.WhileStmt):
        return [("condición", n.cond), ("cuerpo", n.body)]
    if isinstance(n, A.ForStmt):
        return [("inicio", n.init), ("condición", n.cond), ("paso", n.update), ("cuerpo", n.body)]
    if isinstance(n, A.Block):
        return n.stmts
    if isinstance(n, A.BinOp):
        return [n.left, n.right]
    if isinstance(n, A.UnaryOp):
        return [n.operand]
    if isinstance(n, A.Call):
        return n.args
    if isinstance(n, A.ListLit):
        return n.items
    if isinstance(n, A.Index):
        return [n.target, n.index]
    return []


def imprimir_arbol(n, prefijo: str = "", ultimo: bool = True, raiz: bool = True):
    rotulo = None
    if isinstance(n, tuple):
        rotulo, n = n
    if isinstance(n, list):
        texto = f"{rotulo}:" if rotulo else "(lista)"
        sub = n
    else:
        texto = f"{rotulo}: {etiqueta(n)}" if rotulo else etiqueta(n)
        sub = hijos(n)
    if raiz:
        print(f"  {texto}")
        nuevo = "  "
    else:
        print(f"  {prefijo}{'└── ' if ultimo else '├── '}{texto}")
        nuevo = prefijo + ("    " if ultimo else "│   ")
    for k, h in enumerate(sub):
        imprimir_arbol(h, nuevo if not raiz else "", k == len(sub) - 1, False)


def contar_nodos(n) -> int:
    if isinstance(n, tuple):
        n = n[1]
    if isinstance(n, list):
        return sum(contar_nodos(x) for x in n)
    return 1 + sum(contar_nodos(h) for h in hijos(n))


def fase_sintactica(toks, source: str, path: str):
    titulo(2, "ANÁLISIS SINTÁCTICO (parser)", "¿las oraciones están bien estructuradas? (gramática)",
           "Parser descendente recursivo (top-down): cada regla de la gramática es una\n"
           "función (expr → or → and → igualdad → comparación → suma (E) → producto (T)\n"
           "→ unario → primario (F)). Convierte la lista plana de tokens en un árbol (AST).")
    try:
        prog = Parser(toks).parse()
    except ParseError as e:
        print(format_diagnostics(path, source, str(e), "sintáctico"))
        detenida(2, "sintáctica")
        return None
    imprimir_arbol(prog)
    resultado(f"AST con {contar_nodos(prog)} nodos. La precedencia quedó codificada en la profundidad del árbol.")
    return prog


def fase_semantica(prog, source: str, path: str):
    titulo(3, "ANÁLISIS SEMÁNTICO (tabla de símbolos + chequeo de tipos)",
           "¿lo que se estructuró tiene sentido? (significado)",
           "Recorre el AST con una pila de ámbitos (enter_scope / lookup / exit_scope),\n"
           "registra cada símbolo y verifica que cada operación reciba tipos compatibles.")
    traza: list[str] = []
    analizador = SemanticAnalyzer(traza)
    try:
        sym = analizador.analyze(prog)
    except SemanticError as e:
        for linea in traza:
            print(f"  {linea}")
        print()
        print(format_diagnostics(path, source, str(e), "semántico"))
        detenida(3, "semántica")
        return None
    for linea in traza:
        print(f"  {linea}")
    print("\n  Tabla de símbolos — funciones")
    print(f"  {'NOMBRE':<14} {'PARÁMETROS':<30} RETORNO")
    for nombre, f in sym["functions"].items():
        ps = ", ".join(f"{n}: {t}" for n, t in f["params"]) or "—"
        print(f"  {nombre:<14} {ps:<30} {f['ret']}")
    print("\n  Tabla de símbolos — ámbito global")
    print(f"  {'NOMBRE':<14} {'TIPO':<10} NOMBRE RESUELTO")
    for nombre, info in analizador.scopes[0].items():
        print(f"  {nombre:<14} {info['type']:<10} {info['resolved']}")
    resultado("Sin errores semánticos: el programa tiene sentido y puede traducirse.")
    return sym


def cuadrupla(ins):
    op = ins.op
    if op == "binop":
        return (ins.c, fmt(ins.b), fmt(ins.extra), ins.a)
    if op == "unop":
        return (ins.c, fmt(ins.b), "", ins.a)
    if op == "assign":
        return ("=", fmt(ins.b), "", ins.a)
    if op == "ifFalse":
        return ("ifFalse", fmt(ins.a), "", ins.b)
    if op == "goto":
        return ("goto", "", "", ins.a)
    if op == "label":
        return ("label", "", "", ins.a)
    if op == "call":
        return ("call", ins.c, "[" + ", ".join(fmt(x) for x in ins.b or []) + "]", ins.a or "")
    if op == "return":
        return ("return", fmt(ins.a) if ins.a is not None else "", "", "")
    if op == "list":
        return ("list", "[" + ", ".join(fmt(x) for x in ins.b or []) + "]", "", ins.a)
    if op == "index":
        return ("[]", fmt(ins.b), fmt(ins.c), ins.a)
    if op == "setindex":
        return ("[]=", fmt(ins.b), fmt(ins.c), ins.a)
    if op == "func_begin":
        return ("func", ins.a, "[" + ", ".join(ins.c or []) + "]", "")
    if op == "func_end":
        return ("endfunc", ins.a, "", "")
    return (op, fmt(ins.a), fmt(ins.b), fmt(ins.c))


def imprimir_ir(ir):
    print(f"  {'#':>3}  {'CÓDIGO DE TRES DIRECCIONES':<32} CUÁDRUPLA (op, arg1, arg2, resultado)")
    print(f"  {'─' * 3}  {'─' * 32} {'─' * 34}")
    for k, ins in enumerate(ir):
        texto = str(ins).strip()
        q = ", ".join(str(x) if x != "" else "—" for x in cuadrupla(ins))
        print(f"  {k:>3}  {texto[:32]:<32} ({q})")


def fase_ir(prog):
    titulo(4, "CÓDIGO INTERMEDIO (IR · TAC)",
           "¿cómo se desenrolla el árbol en pasos atómicos de máximo 3 direcciones?",
           "Recorrido post-orden del AST: cada operación produce un temporal (%tN).\n"
           "if / while / for se convierten en saltos (ifFalse, goto) hacia etiquetas (%LN).")
    ir = IRGenerator().generate(prog)
    imprimir_ir(ir)
    temps = {ins.a for ins in ir if isinstance(ins.a, str) and ins.a.startswith("%t")}
    etiquetas = sum(1 for ins in ir if ins.op == "label")
    resultado(f"{len(ir)} instrucciones TAC, {len(temps)} temporales, {etiquetas} etiquetas.")
    return ir


def fase_optimizacion(ir, sym, activa: bool):
    titulo(5, "OPTIMIZACIÓN (middle-end)",
           "¿se puede obtener el mismo resultado con menos instrucciones?",
           "Plegado y propagación de constantes, eliminación de código muerto y\n"
           "de bloques inalcanzables, y movimiento de invariantes fuera de los ciclos.")
    if not activa:
        print("  Fase omitida. Usa --opt junto con --fases para activarla.")
        return ir
    nuevo = optimize(ir, sym["globals"])
    imprimir_ir(nuevo)
    ahorro = len(ir) - len(nuevo)
    resultado(f"{len(ir)} → {len(nuevo)} instrucciones ({ahorro} eliminadas).")
    return nuevo


def fase_codigo_objetivo(ir, sym, registros: int):
    titulo(6, "GENERACIÓN DE CÓDIGO OBJETIVO (ensamblador simulado)",
           "¿qué registros de la CPU usa cada temporal y qué pasa cuando se acaban?",
           f"CPU simulada con {registros} registros (R0..R{registros - 1}), RV para el valor de retorno,\n"
           "FP/SP para el marco de pila. Variables globales en .data, locales en [FP±n].\n"
           "Los temporales ocupan registros; si no hay libres se hace SPILL a la RAM.")
    gen = generar_asm(ir, registros, sym["globals"])
    print("  Asignación de registros:")
    for linea in gen.traza:
        print(f"    {linea}")
    print("\n  Ensamblador generado:")
    for linea in gen.lineas:
        print(f"  {linea}")
    st = gen.stats
    resultado(f"{st['instrucciones']} instrucciones, {st['spills']} spill(s), {st['loads']} recarga(s) desde la RAM.")
    return gen


def fase_ejecucion(ir, sym, path: str):
    titulo(7, "EJECUCIÓN Y MEMORIA (stack y heap)",
           "¿cómo usa la memoria el programa mientras corre?",
           "Se ejecuta el TAC en una máquina virtual. Cada llamada apila un marco\n"
           "(stack frame) con sus parámetros y locales; las listas viven en el heap.\n"
           "Las líneas con │ son eventos de memoria; las demás son la salida del programa.")
    eventos = [0]

    def traza(msg: str):
        eventos[0] += 1
        if eventos[0] <= LIMITE_EVENTOS:
            print(f"  │ {msg}")
        elif eventos[0] == LIMITE_EVENTOS + 1:
            print(f"  │ … (se ocultan los demás eventos de memoria)")

    vm = Interpreter(ir, sym["globals"], traza=traza)
    try:
        vm.run()
    except InterpError as e:
        print(format_runtime_error(path, str(e)))
        detenida(7, "ejecución")
        return False
    resultado(f"Programa terminado. Eventos de memoria: {eventos[0]}, profundidad máxima de la pila: "
              f"{vm.profundidad_max} marco(s), reservas en el heap: {vm.reservas_heap}.")
    return True


def ejecutar_con_fases(source: str, path: str, opt: bool = False, run: bool = True, registros: int = 3) -> int:
    print(f"Compilando {path} con el pipeline completo de MiniB")
    print("Front-end: fases 1–3 · Middle-end: fases 4–5 · Back-end: fases 6–7")
    toks = fase_lexica(source, path)
    if toks is None:
        return 1
    prog = fase_sintactica(toks, source, path)
    if prog is None:
        return 1
    sym = fase_semantica(prog, source, path)
    if sym is None:
        return 1
    ir = fase_ir(prog)
    ir = fase_optimizacion(ir, sym, opt)
    fase_codigo_objetivo(ir, sym, registros)
    if run:
        if not fase_ejecucion(ir, sym, path):
            return 1
    else:
        print("\n(Ejecución omitida por --no-run)")
    print()
    print("═" * ANCHO)
    print(" Pipeline completo: Texto → Tokens → AST → AST validado → TAC → Ensamblador")
    print("═" * ANCHO)
    return 0
