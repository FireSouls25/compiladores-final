import argparse
import sys

from .lexer import Lexer, LexError
from .parser import Parser, ParseError
from .semantic import SemanticAnalyzer, SemanticError
from .ir_gen import IRGenerator
from .optimizer import optimize
from .interp import Interpreter, InterpError
from .py_codegen import generate_python
from .asm_gen import generar_asm
from .fases import ejecutar_con_fases
from .diagnostics import format_diagnostics, format_runtime_error

EXIT_OK = 0
EXIT_COMPILE = 1
EXIT_IO = 2

TIPO_ERROR = {LexError: "léxico", ParseError: "sintáctico", SemanticError: "semántico"}

_ARGPARSE_ES = {
    "usage: ": "uso: ",
    "positional arguments": "argumentos posicionales",
    "options": "opciones",
    "show this help message and exit": "muestra esta ayuda y termina",
    "the following arguments are required: %s": "faltan argumentos obligatorios: %s",
    "unrecognized arguments: %s": "argumentos no reconocidos: %s",
    "%(prog)s: error: %(message)s\n": "%(prog)s: error: %(message)s\n",
    "argument %(argument_name)s: %(message)s": "argumento %(argument_name)s: %(message)s",
    "invalid %(type)s value: %(value)r": "valor %(type)s inválido: %(value)r",
    "expected one argument": "se esperaba un argumento",
}
argparse._ = lambda texto: _ARGPARSE_ES.get(texto, texto)


def compile_source(source: str, dump_tokens=False, dump_ast=False, dump_ir=False, opt=False):
    toks = Lexer(source).tokenize()
    if dump_tokens:
        print("== TOKENS ==")
        for t in toks:
            print(f"  {t.type:10} {t.lexeme!r} ({t.line}:{t.col})")
    prog = Parser(toks).parse()
    if dump_ast:
        print("== AST ==")
        for it in prog.items:
            print(f"  {it}")
    sym = SemanticAnalyzer().analyze(prog)
    ir = IRGenerator().generate(prog)
    if opt:
        ir = optimize(ir, sym["globals"])
    if dump_ir:
        print("== IR (TAC) ==" if not opt else "== IR (TAC optimizado) ==")
        for ins in ir:
            print(ins)
    return prog, sym, ir


def construir_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="minib", description="Compilador e intérprete didáctico de MiniB")
    ap.add_argument("file", metavar="archivo", help="archivo fuente (.mb)")
    ap.add_argument("--fases", action="store_true",
                    help="muestra paso a paso cómo trabaja cada fase del compilador")
    ap.add_argument("--dump-tokens", action="store_true", help="imprime la lista de tokens")
    ap.add_argument("--dump-ast", action="store_true", help="imprime el AST")
    ap.add_argument("--dump-ir", action="store_true", help="imprime el código de tres direcciones")
    ap.add_argument("--opt", action="store_true", help="optimiza el TAC antes de ejecutar")
    ap.add_argument("--no-run", action="store_true", help="solo compila, no ejecuta")
    ap.add_argument("--emit-asm", action="store_true",
                    help="genera el ensamblador simulado (registros y spill) en lugar de ejecutar")
    ap.add_argument("--registros", type=int, default=3, metavar="N",
                    help="cantidad de registros de la CPU simulada (mínimo 3, por defecto 3)")
    ap.add_argument("--emit-py", action="store_true", help="genera código Python en lugar de ejecutar")
    ap.add_argument("-o", "--output", metavar="ARCHIVO",
                    help="escribe la salida de --emit-py o --emit-asm en ARCHIVO")
    return ap


def escribir(texto: str, destino: str | None) -> int:
    if not destino:
        print(texto, end="")
        return EXIT_OK
    try:
        with open(destino, "w", encoding="utf-8") as f:
            f.write(texto)
    except OSError as e:
        print(f"error: no se puede escribir {destino}: {e}", file=sys.stderr)
        return EXIT_IO
    return EXIT_OK


def main(argv=None):
    args = construir_parser().parse_args(argv)

    try:
        with open(args.file, "r", encoding="utf-8-sig") as f:
            source = f.read()
    except OSError as e:
        print(f"error: no se puede leer {args.file}: {e}", file=sys.stderr)
        return EXIT_IO

    if args.fases:
        return ejecutar_con_fases(source, args.file, opt=args.opt, run=not args.no_run,
                                  registros=max(3, args.registros))

    try:
        prog, sym, ir = compile_source(
            source,
            dump_tokens=args.dump_tokens,
            dump_ast=args.dump_ast,
            dump_ir=args.dump_ir,
            opt=args.opt,
        )
    except (LexError, ParseError, SemanticError) as e:
        print(format_diagnostics(args.file, source, str(e), TIPO_ERROR[type(e)]), file=sys.stderr)
        return EXIT_COMPILE

    if args.emit_asm:
        gen = generar_asm(ir, max(3, args.registros), sym["globals"])
        return escribir("\n".join(gen.lineas) + "\n", args.output)

    if args.emit_py:
        return escribir(generate_python(prog), args.output)

    if not args.no_run:
        try:
            Interpreter(ir, sym["globals"]).run()
        except InterpError as e:
            print(format_runtime_error(args.file, str(e)), file=sys.stderr)
            return EXIT_COMPILE
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
