"""MiniB driver: source.mb -> lexer -> parser -> semantic -> IR -> run."""
import argparse
import sys

from .lexer import Lexer, LexError
from .parser import Parser, ParseError
from .semantic import SemanticAnalyzer, SemanticError
from .ir_gen import IRGenerator
from .interp import Interpreter, InterpError
from .diagnostics import format_diagnostics, format_runtime_error

EXIT_OK = 0
EXIT_COMPILE = 1
EXIT_IO = 2


def compile_source(source: str, dump_tokens=False, dump_ast=False, dump_ir=False):
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
    if dump_ir:
        print("== IR ==")
        for ins in ir:
            print(ins)
    return prog, sym, ir


def main(argv=None):
    ap = argparse.ArgumentParser(prog="minib", description="MiniB compiler/interpreter")
    ap.add_argument("file", help="source file (.mb)")
    ap.add_argument("--dump-tokens", action="store_true", help="print the token stream")
    ap.add_argument("--dump-ast", action="store_true", help="print the AST")
    ap.add_argument("--dump-ir", action="store_true", help="print the generated TAC")
    ap.add_argument("--no-run", action="store_true", help="compile only, do not execute")
    args = ap.parse_args(argv)

    try:
        with open(args.file, "r", encoding="utf-8-sig") as f:
            source = f.read()
    except OSError as e:
        print(f"error: cannot read {args.file}: {e}", file=sys.stderr)
        return EXIT_IO

    try:
        _, sym, ir = compile_source(
            source,
            dump_tokens=args.dump_tokens,
            dump_ast=args.dump_ast,
            dump_ir=args.dump_ir,
        )
    except (LexError, ParseError, SemanticError) as e:
        print(format_diagnostics(args.file, source, str(e)), file=sys.stderr)
        return EXIT_COMPILE

    if not args.no_run:
        try:
            Interpreter(ir, sym["globals"]).run()
        except InterpError as e:
            print(format_runtime_error(args.file, str(e)), file=sys.stderr)
            return EXIT_COMPILE
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
