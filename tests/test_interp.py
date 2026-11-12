import unittest

from tests.support import *
from src.interp import Interpreter, InterpError


class InterpreterTests(unittest.TestCase):
    def test_hello_program(self):
        out = run_source(
            "fn add(a: int, b: int) -> int { return a + b; } "
            'let x: int = 10; print(add(x, 2)); print("hello " + "world");'
        )
        self.assertEqual(out, "12\nhello world\n")

    def test_fibonacci(self):
        out = run_source(example("fib.mb"))
        self.assertEqual(out, "0\n1\n1\n2\n3\n5\n8\n13\n21\n34\n")

    def test_shadowing_is_block_scoped(self):
        out = run_source("let x = 1; { let x = 2; print(x); } print(x);")
        self.assertEqual(out, "2\n1\n")

    def test_global_mutation_from_function(self):
        out = run_source(
            "let g = 0; fn inc() { g = g + 1; } inc(); inc(); print(g);"
        )
        self.assertEqual(out, "2\n")

    def test_deep_recursion_does_not_hit_python_limit(self):
        out = run_source(
            "fn down(n: int) -> int { if (n == 0) { return 0; } return down(n - 1); } "
            "print(down(3000));"
        )
        self.assertEqual(out, "0\n")

    def test_division_by_zero_is_a_clean_error(self):
        _, sym, ir = compile_pipeline("let a = 1; let b = 0; print(a / b);")
        with self.assertRaisesRegex(InterpError, "division by zero"):
            Interpreter(ir, sym["globals"]).run()

    def test_modulo_by_zero_is_a_clean_error(self):
        _, sym, ir = compile_pipeline("print(5 % 0);")
        with self.assertRaisesRegex(InterpError, "division by zero"):
            Interpreter(ir, sym["globals"]).run()

    def test_strings_floats_bools(self):
        out = run_source(
            'let s: str = "ab" * 3; print(s); print(7 / 2); '
            "let ok: bool = not False and True; print(ok); print(len(s));"
        )
        self.assertEqual(out, "ababab\n3.5\nTrue\n6\n")

    def test_optimized_fib_matches(self):
        self.assertEqual(run_source(example("fib.mb"), opt=True),
                         run_source(example("fib.mb")))

    def test_optimized_misc_matches(self):
        self.assertEqual(run_source(example("misc.mb"), opt=True),
                         run_source(example("misc.mb")))

    def test_void_function_and_else_if(self):
        out = run_source(
            "fn grade(n: int) -> str { "
            '  if (n > 90) { return "A"; } else if (n > 80) { return "B"; } '
            '  else { return "C"; } } '
            'print(grade(95)); print(grade(85));'
        )
        self.assertEqual(out, "A\nB\n")

    def test_empty_bare_block(self):
        self.assertEqual(run_source("{ }"), "")


if __name__ == "__main__":
    unittest.main()
