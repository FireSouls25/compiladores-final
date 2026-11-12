import unittest

from tests.support import *
from src.py_codegen import generate_python


class BackendTests(unittest.TestCase):
    def test_generates_valid_python(self):
        prog, _, _ = compile_pipeline(
            "fn add(a: int, b: int) -> int { return a + b; } print(add(2, 3));"
        )
        code = generate_python(prog)
        self.assertIn("def add(a, b) -> int:", code)
        self.assertEqual(run_python(code), "5\n")

    def test_all_examples_match_interpreter(self):
        for name in ("hello.mb", "fib.mb", "misc.mb", "scope.mb"):
            with self.subTest(example=name):
                source = example(name)
                prog, _, _ = compile_pipeline(source)
                self.assertEqual(run_python(generate_python(prog)), run_source(source))

    def test_global_writes_emit_global_statement(self):
        source = (
            "let counter = 0; fn bump() { counter = counter + 1; } "
            "bump(); bump(); print(counter);"
        )
        prog, _, _ = compile_pipeline(source)
        code = generate_python(prog)
        self.assertIn("global counter", code)
        self.assertEqual(run_python(code), run_source(source))

    def test_shadowing_is_renamed(self):
        source = "let x = 1; { let x = 2; print(x); } print(x);"
        prog, _, _ = compile_pipeline(source)
        code = generate_python(prog)
        self.assertIn("x__1", code)
        self.assertEqual(run_python(code), run_source(source))

    def test_renaming_avoids_user_name_collisions(self):
        source = "let x = 1; let x__1 = 100; { let x = 2; print(x); } print(x__1);"
        prog, _, _ = compile_pipeline(source)
        code = generate_python(prog)
        self.assertIn("x__1_2", code)
        self.assertEqual(run_python(code), run_source(source))

    def test_else_if_chain(self):
        source = (
            "fn f(n: int) -> str { if (n > 1) { return \"a\"; } "
            "else if (n == 1) { return \"b\"; } else { return \"c\"; } } "
            "print(f(2)); print(f(1)); print(f(0));"
        )
        prog, _, _ = compile_pipeline(source)
        code = generate_python(prog)
        self.assertIn("elif", code)
        self.assertEqual(run_python(code), "a\nb\nc\n")

    def test_empty_function_gets_pass(self):
        prog, _, _ = compile_pipeline("fn noop() { } noop();")
        self.assertIn("pass", generate_python(prog))

    def test_booleans_and_none_literals(self):
        prog, _, _ = compile_pipeline("let a = True; let b = not False; print(a and b);")
        self.assertEqual(run_python(generate_python(prog)), "True\n")


if __name__ == "__main__":
    unittest.main()
