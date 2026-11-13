import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.lexer import Lexer
from src.parser import Parser
from src.semantic import SemanticAnalyzer
from src.ir_gen import IRGenerator
from src.optimizer import optimize
from src.interp import Interpreter, InterpError
from src.py_codegen import generate_python


def compile_pipeline(source: str, opt: bool = False):
    tokens = Lexer(source).tokenize()
    prog = Parser(tokens).parse()
    sym = SemanticAnalyzer().analyze(prog)
    ir = IRGenerator().generate(prog)
    if opt:
        ir = optimize(ir, sym["globals"])
    return prog, sym, ir


def run_source(source: str, opt: bool = False) -> str:
    prog, sym, ir = compile_pipeline(source, opt=opt)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        Interpreter(ir, sym["globals"]).run()
    return buf.getvalue()


def example(name: str) -> str:
    return (ROOT / "examples" / name).read_text(encoding="utf-8")


def run_python(code: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(code, "<generated>", "exec"), {"__name__": "__main__"})
    return buf.getvalue()
