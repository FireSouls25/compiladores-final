import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from tests.support import ROOT
from src.__main__ import main
from src.diagnostics import format_diagnostics, format_runtime_error

HELLO = str(ROOT / "examples" / "hello.mb")
ERROR = str(ROOT / "examples" / "error.mb")


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def test_compile_only_success(self):
        code, _, err = run_cli([HELLO, "--no-run"])
        self.assertEqual((code, err), (0, ""))

    def test_run_prints_program_output(self):
        code, out, _ = run_cli([HELLO])
        self.assertEqual(code, 0)
        self.assertIn("12", out)
        self.assertIn("hola mundo", out)

    def test_semantic_error_has_snippet(self):
        code, _, err = run_cli([ERROR])
        self.assertEqual(code, 1)
        self.assertIn("error semántico: no se puede asignar 'str' a 'int'", err)
        self.assertIn("let x: int", err)
        self.assertIn("^", err)

    def test_missing_file_exit_code(self):
        code, _, err = run_cli(["does-not-exist.mb"])
        self.assertEqual(code, 2)
        self.assertIn("no se puede leer", err)

    def test_dump_flags(self):
        code, out, _ = run_cli([HELLO, "--dump-tokens", "--dump-ast", "--dump-ir", "--no-run"])
        self.assertEqual(code, 0)
        for header in ("== TOKENS ==", "== AST ==", "== IR (TAC) =="):
            self.assertIn(header, out)
        self.assertIn("func add(a, b):", out)

    def test_opt_dump_is_labeled(self):
        code, out, _ = run_cli([HELLO, "--dump-ir", "--opt", "--no-run"])
        self.assertEqual(code, 0)
        self.assertIn("== IR (TAC optimizado) ==", out)

    def test_emit_python_to_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "hello.py"
            code, out, _ = run_cli([HELLO, "--emit-py", "-o", str(target)])
            self.assertEqual((code, out), (0, ""))
            generated = target.read_text(encoding="utf-8")
            self.assertIn("def add(a, b) -> int:", generated)

    def test_emit_python_to_stdout(self):
        code, out, _ = run_cli([HELLO, "--emit-py"])
        self.assertEqual(code, 0)
        self.assertIn("Generado por MiniB", out)


class DiagnosticsTests(unittest.TestCase):
    SOURCE = "fn f() {\n  let x: int = \"bad\";\n}\n"

    def test_snippet_and_caret(self):
        text = format_diagnostics("p.mb", self.SOURCE, '2:3: no se puede asignar \'str\' a \'int\'')
        self.assertIn("p.mb:2:3: error: no se puede asignar", text)
        self.assertIn('2 >   let x: int = "bad";', text)
        self.assertIn("^", text)

    def test_multiple_errors(self):
        text = format_diagnostics("p.mb", self.SOURCE, "1:1: first\n2:3: second")
        self.assertIn("first", text)
        self.assertIn("second", text)
        self.assertEqual(text.count("^"), 2)

    def test_non_positional_message(self):
        text = format_diagnostics("p.mb", self.SOURCE, "weird")
        self.assertIn("p.mb: error: weird", text)

    def test_runtime_error(self):
        self.assertEqual(
            format_runtime_error("p.mb", "división por cero"),
            "p.mb: error de ejecución: división por cero",
        )


if __name__ == "__main__":
    unittest.main()
