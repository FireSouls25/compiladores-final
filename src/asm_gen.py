from .ir_gen import Instr

OPCODES = {
    "+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV", "%": "MOD",
    "==": "SEQ", "!=": "SNE", "<": "SLT", "<=": "SLE", ">": "SGT", ">=": "SGE",
    "and": "AND", "or": "OR",
}


def es_temporal(x) -> bool:
    return isinstance(x, str) and x.startswith("%")  and not x.startswith("%L")


def es_variable(x) -> bool:
    return isinstance(x, str) and not x.startswith("@") and not x.startswith("%")


def etiqueta(nombre: str) -> str:
    return nombre.lstrip("%")


def lecturas(ins: Instr) -> list:
    op = ins.op
    if op == "binop":
        return [ins.b, ins.extra]
    if op in ("unop", "assign"):
        return [ins.b]
    if op == "ifFalse":
        return [ins.a]
    if op in ("call", "list"):
        return list(ins.b or [])
    if op == "return":
        return [ins.a]
    if op == "index":
        return [ins.b, ins.c]
    if op == "setindex":
        return [ins.a, ins.b, ins.c]
    return []


def escritura(ins: Instr):
    if ins.op in ("binop", "unop", "list", "index", "call", "assign"):
        return ins.a
    return None


class GeneradorASM:
    def __init__(self, registros: int = 3, globales=()):
        self.pool = [f"R{i}" for i in range(max(3, registros))]
        self.globales = set(globales or ())
        self.traza: list[str] = []
        self.lineas: list[str] = []
        self.stats = {"instrucciones": 0, "spills": 0, "loads": 0}

    def generar(self, code: list[Instr]) -> list[str]:
        principal: list[Instr] = []
        funciones: list[list[Instr]] = []
        actual = None
        for ins in code:
            if ins.op == "func_begin":
                actual = [ins]
            elif ins.op == "func_end":
                actual.append(ins)
                funciones.append(actual)
                actual = None
            elif actual is not None:
                actual.append(ins)
            else:
                principal.append(ins)

        self.lineas = [".data"]
        datos = set(self.globales)
        for ins in principal:
            d = escritura(ins)
            if es_variable(d):
                datos.add(d)
        self.globales = datos
        for nombre in sorted(datos):
            self.lineas.append(f"    {nombre}: .word 0")
        self.lineas.append(".text")
        self.traza.append("── Segmento principal (main) ──")
        self._seccion("main", principal, es_main=True)
        for seg in funciones:
            self.traza.append(f"── Función {seg[0].a} ──")
            self._seccion(seg[0].a, seg, es_main=False)
        return self.lineas

    def _seccion(self, nombre: str, seg: list[Instr], es_main: bool):
        self.reg_de: dict[str, str] = {}
        self.ocupado: dict[str, str] = {}
        self.spill: dict[str, int] = {}
        self.slots_libres: list[int] = []
        self.proximo_slot = 0
        self.marco: dict[str, str] = {}
        self.aux = 0
        self._liveness(seg)

        if not es_main:
            params = seg[0].c or []
            for k, p in enumerate(params):
                self.marco[p] = f"[FP+{8 + 4 * k}]"
            locales = []
            for ins in seg:
                d = escritura(ins)
                if es_variable(d) and d not in self.marco and d not in self.globales and d not in locales:
                    locales.append(d)
            for k, v in enumerate(locales):
                self.marco[v] = f"[FP-{4 * (k + 1)}]"
            if self.marco:
                desc = ", ".join(f"{v} → {m}" for v, m in self.marco.items())
                self.traza.append(f"Marco de pila de '{nombre}': {desc}")
            self._etiqueta(nombre)
            self._emitir("PUSH FP", "guarda el marco del llamador")
            self._emitir("MOV FP, SP", "nuevo marco de pila")
            if locales:
                self._emitir(f"SUB SP, #{4 * len(locales)}", f"espacio para {len(locales)} local(es)")
            cuerpo = list(enumerate(seg))[1:-1]
        else:
            self._etiqueta("main")
            cuerpo = list(enumerate(seg))

        for i, ins in cuerpo:
            self._traducir(i, ins, nombre)
            self._liberar_muertos(i)

        if es_main:
            self._emitir("HALT", "fin del programa")

    def _liveness(self, seg: list[Instr]):
        self.usos: dict[str, list[int]] = {}
        definicion: dict[str, int] = {}
        etiquetas: dict[str, int] = {}
        for i, ins in enumerate(seg):
            for x in lecturas(ins):
                if es_temporal(x):
                    self.usos.setdefault(x, []).append(i)
            d = escritura(ins)
            if es_temporal(d):
                definicion.setdefault(d, i)
            if ins.op == "label":
                etiquetas[ins.a] = i
        self.ultimo_uso = {t: max(u) for t, u in self.usos.items()}
        for g, ins in enumerate(seg):
            destino = ins.a if ins.op == "goto" else ins.b if ins.op == "ifFalse" else None
            h = etiquetas.get(destino)
            if h is None or h >= g:
                continue
            for t, usos in self.usos.items():
                if definicion.get(t, -1) < h and any(h <= u <= g for u in usos):
                    self.ultimo_uso[t] = max(self.ultimo_uso[t], g)

    def _emitir(self, instr: str, nota: str = ""):
        self.stats["instrucciones"] += 1
        linea = f"    {instr}"
        if nota:
            linea = f"{linea:<34}; {nota}"
        self.lineas.append(linea)

    def _etiqueta(self, nombre: str):
        self.lineas.append(f"{nombre}:")

    def _memoria(self, nombre: str) -> str:
        return self.marco.get(nombre, f"[{nombre}]")

    def _inmediato(self, v) -> str:
        if isinstance(v, str) and v.startswith("@"):
            return f"#{v[1:]!r}"
        return f"#{v}"

    def _proximo_uso(self, t: str, i: int) -> int:
        for u in self.usos.get(t, []):
            if u > i:
                return u
        return 10 ** 9

    def _asignar(self, t: str, i: int, fijos: set) -> str:
        for r in self.pool:
            if r not in self.ocupado:
                self.reg_de[t] = r
                self.ocupado[r] = t
                if not t.startswith("%aux"):
                    self.traza.append(f"[{i:02d}] {t} → {r} (registro libre)")
                return r
        candidatos = [r for r in self.pool if self.ocupado[r] not in fijos]
        r = max(candidatos, key=lambda reg: self._proximo_uso(self.ocupado[reg], i))
        victima = self.ocupado[r]
        self._expulsar(victima, i, "no hay registros libres")
        self.reg_de[t] = r
        self.ocupado[r] = t
        if not t.startswith("%aux"):
            self.traza.append(f"[{i:02d}] {t} → {r} (reutilizado tras el spill)")
        return r

    def _expulsar(self, t: str, i: int, motivo: str):
        r = self.reg_de.pop(t)
        del self.ocupado[r]
        slot = self.slots_libres.pop(0) if self.slots_libres else self._nuevo_slot()
        self.spill[t] = slot
        self.stats["spills"] += 1
        self._emitir(f"STORE {r}, [SP+{slot}]", f"spill de {t}")
        self.traza.append(f"[{i:02d}] SPILL: {motivo}; {t} sale de {r} hacia la RAM [SP+{slot}]")

    def _nuevo_slot(self) -> int:
        slot = self.proximo_slot
        self.proximo_slot += 4
        return slot

    def _registro_de(self, t: str, i: int, fijos: set) -> str:
        if t in self.reg_de:
            return self.reg_de[t]
        if t in self.spill:
            slot = self.spill.pop(t)
            r = self._asignar(t, i, fijos)
            self.slots_libres.append(slot)
            self.stats["loads"] += 1
            self._emitir(f"LOAD {r}, [SP+{slot}]", f"recarga {t}")
            self.traza.append(f"[{i:02d}] LOAD: {t} vuelve de [SP+{slot}] a {r}")
            return r
        return self._memoria(t)

    def _operando(self, x, i: int, fijos: set) -> str:
        if es_temporal(x):
            return self._registro_de(x, i, fijos)
        if es_variable(x):
            return self._memoria(x)
        return self._inmediato(x)

    def _a_registro(self, x, i: int, fijos: set) -> str:
        op = self._operando(x, i, fijos)
        if op in self.pool:
            return op
        self.aux += 1
        aux = f"%aux{self.aux}"
        r = self._asignar(aux, i, fijos | {aux})
        fijos.add(aux)
        self._emitir(f"MOV {r}, {op}", self._nota(x))
        return r

    def _nota(self, x) -> str:
        return x if es_variable(x) and x in self.marco else ""

    def _liberar(self, t: str, i: int):
        r = self.reg_de.pop(t, None)
        if r is not None:
            del self.ocupado[r]
            if not t.startswith("%aux"):
                self.traza.append(f"[{i:02d}] {r} liberado: {t} ya no se usa")
        if t in self.spill:
            self.slots_libres.append(self.spill.pop(t))

    def _liberar_muertos(self, i: int):
        for t in list(self.reg_de) + list(self.spill):
            if t.startswith("%aux") or self.ultimo_uso.get(t, -1) <= i:
                self._liberar(t, i)

    def _muere_aqui(self, t, i: int) -> bool:
        return es_temporal(t) and self.ultimo_uso.get(t, -1) <= i

    def _traducir(self, i: int, ins: Instr, funcion: str):
        op = ins.op
        fijos = {x for x in lecturas(ins) if es_temporal(x)}

        if op == "label":
            self._etiqueta(etiqueta(ins.a))
        elif op == "goto":
            self._emitir(f"JMP {etiqueta(ins.a)}")
        elif op == "ifFalse":
            c = self._operando(ins.a, i, fijos)
            self._emitir(f"CMP {c}, #0", "¿condición falsa?")
            self._emitir(f"JE {etiqueta(ins.b)}")
        elif op == "binop":
            a = self._operando(ins.b, i, fijos)
            b = self._operando(ins.extra, i, fijos)
            if self._muere_aqui(ins.b, i) and ins.b != ins.extra:
                self._liberar(ins.b, i)
                fijos.discard(ins.b)
            r = self._asignar(ins.a, i, fijos)
            if r != a:
                self._emitir(f"MOV {r}, {a}", self._nota(ins.b))
            codigo = OPCODES.get(ins.c, ins.c.upper())
            if ins.c == "+" and any(isinstance(x, str) and x.startswith("@") for x in (ins.b, ins.extra)):
                codigo = "CONCAT"
            self._emitir(f"{codigo} {r}, {b}", self._nota(ins.extra))
        elif op == "unop":
            a = self._operando(ins.b, i, fijos)
            if self._muere_aqui(ins.b, i):
                self._liberar(ins.b, i)
                fijos.discard(ins.b)
            r = self._asignar(ins.a, i, fijos)
            if r != a:
                self._emitir(f"MOV {r}, {a}", self._nota(ins.b))
            self._emitir(f"{'NEG' if ins.c == '-' else 'NOT'} {r}")
        elif op == "assign":
            if es_temporal(ins.a):
                v = self._operando(ins.b, i, fijos)
                r = self._asignar(ins.a, i, fijos)
                self._emitir(f"MOV {r}, {v}")
            else:
                v = self._operando(ins.b, i, fijos)
                if v.startswith("["):
                    v = self._a_registro(ins.b, i, fijos)
                self._emitir(f"MOV {self._memoria(ins.a)}, {v}", self._nota(ins.a))
        elif op == "call":
            args = list(ins.b or [])
            for x in reversed(args):
                self._emitir(f"PUSH {self._operando(x, i, fijos)}", self._nota(x))
            for t in list(self.reg_de):
                if self.ultimo_uso.get(t, -1) > i:
                    self._expulsar(t, i, f"CALL {ins.c} puede usar todos los registros")
            for x in args:
                if self._muere_aqui(x, i):
                    self._liberar(x, i)
            self._emitir(f"CALL {ins.c}")
            if args:
                self._emitir(f"ADD SP, #{4 * len(args)}", "descarta los argumentos")
            if ins.a:
                r = self._asignar(ins.a, i, set())
                self._emitir(f"MOV {r}, RV", "valor de retorno")
        elif op == "return":
            if ins.a is not None:
                self._emitir(f"MOV RV, {self._operando(ins.a, i, fijos)}", "valor de retorno")
            else:
                self._emitir("MOV RV, #None")
            self._emitir("MOV SP, FP", "destruye el marco")
            self._emitir("POP FP")
            self._emitir("RET")
        elif op == "list":
            items = list(ins.b or [])
            r = self._asignar(ins.a, i, fijos)
            fijos.add(ins.a)
            self._emitir(f"ALLOC {r}, #{len(items)}", f"reserva {len(items)} celda(s) en el heap")
            for k, x in enumerate(items):
                v = self._operando(x, i, fijos)
                if v.startswith("["):
                    v = self._a_registro(x, i, fijos)
                self._emitir(f"MOV [{r}+{k}], {v}")
                if self.ocupado.get(v, "").startswith("%aux"):
                    self._liberar(self.ocupado[v], i)
        elif op == "index":
            base = self._a_registro(ins.b, i, fijos)
            idx = self._operando(ins.c, i, fijos)
            if idx.startswith("["):
                idx = self._a_registro(ins.c, i, fijos)
            r = self._asignar(ins.a, i, fijos)
            self._emitir(f"MOV {r}, [{base}+{idx}]", "lectura del heap")
        elif op == "setindex":
            base = self._a_registro(ins.a, i, fijos)
            idx = self._operando(ins.b, i, fijos)
            if idx.startswith("["):
                idx = self._a_registro(ins.b, i, fijos)
            val = self._operando(ins.c, i, fijos)
            if val.startswith("["):
                val = self._a_registro(ins.c, i, fijos)
            self._emitir(f"MOV [{base}+{idx}], {val}", "escritura en el heap")
        else:
            self._emitir(f"; {ins}")


def generar_asm(code: list[Instr], registros: int = 3, globales=()) -> GeneradorASM:
    gen = GeneradorASM(registros, globales)
    gen.generar(code)
    return gen
