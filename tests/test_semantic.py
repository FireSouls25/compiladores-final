import unittest

from tests.support import *
from src import ast_nodes as A
from src.semantic import SemanticError


def analyze(source):
    return compile_pipeline(source)


class SemanticTests(unittest.TestCase):
    def assert_error(self, source, pattern):
        with self.assertRaisesRegex(SemanticError, pattern):
            analyze(source)

    def test_valid_program(self):
        prog, sym, _ = analyze(
            "fn add(a: int, b: int) -> int { return a + b; } "
            "let x: int = add(1, 2); print(x);"
        )
        self.assertIn("add", sym["functions"])
        self.assertEqual(sym["globals"], ["x"])

    def test_undefined_variable(self):
        self.assert_error("print(y);", "variable no definida 'y'")

    def test_redeclaration_same_scope(self):
        self.assert_error("let x = 1; let x = 2;", "redeclaración de 'x'")

    def test_shadowing_gets_resolved_name(self):
        prog, _, _ = analyze("let x = 1; { let x = 2; print(x); } print(x);")
        block = prog.items[1]
        self.assertIsInstance(block, A.Block)
        inner_let = block.stmts[0]
        inner_print_var = block.stmts[1].expr.args[0]
        outer_print_var = prog.items[2].expr.args[0]
        self.assertEqual(inner_let.resolved_name, "x$1")
        self.assertEqual(inner_print_var.resolved, "x$1")
        self.assertEqual(outer_print_var.resolved, "x")

    def test_type_mismatch_in_let(self):
        self.assert_error('let x: int = "oops";', "no se puede asignar 'str' a 'int'")

    def test_int_to_float_promotion(self):
        analyze("let f: float = 1; print(f);")

    def test_float_to_int_is_rejected(self):
        self.assert_error("let i: int = 1.5;", "no se puede asignar 'float' a 'int'")

    def test_arity_check(self):
        self.assert_error(
            "fn f(a: int) -> int { return a; } print(f());",
            "espera 1 argumento\\(s\\), se obtuvieron 0",
        )

    def test_undefined_function(self):
        self.assert_error("print(nope(1));", "función no definida 'nope'")

    def test_forward_call_is_allowed(self):
        analyze("print(f(2)); fn f(a: int) -> int { return a; }")

    def test_non_void_must_return_on_all_paths(self):
        self.assert_error(
            "fn f(a: int) -> int { if (a > 0) { return 1; } }",
            "debe retornar 'int' en todos los caminos",
        )

    def test_if_else_returns_on_all_paths(self):
        analyze(
            "fn f(a: int) -> int { if (a > 0) { return 1; } else { return 0; } }"
        )

    def test_while_true_with_return_is_accepted(self):
        analyze("fn f() -> int { while (True) { return 1; } }")

    def test_return_type_mismatch(self):
        self.assert_error(
            'fn f() -> int { return "x"; }', "tipo de retorno incorrecto"
        )

    def test_bare_return_in_non_void(self):
        self.assert_error("fn f() -> int { return; }", "el return está vacío")

    def test_condition_must_be_bool(self):
        self.assert_error("if (1) { print(1); }", "debe ser bool")
        self.assert_error("while (0) { print(1); }", "debe ser bool")

    def test_logical_operators_require_bools(self):
        self.assert_error("let x = 1 and 2;", "requiere bool")

    def test_string_concatenation_and_repetition(self):
        analyze('let a = "x" + "y"; let b = "ab" * 3; print(len(a + b));')

    def test_builtin_cannot_be_redefined(self):
        self.assert_error("let print = 1;", "es una función integrada")
        self.assert_error("fn len() { }", "redefinición de la función 'len'")

    def test_variable_cannot_shadow_function(self):
        self.assert_error("fn f() { } let f = 1;", "ya es una función")

    def test_duplicate_parameter(self):
        self.assert_error("fn f(a: int, a: int) { }", "parámetro duplicado 'a'")

    def test_return_outside_function(self):
        self.assert_error("return 1;", "'return' fuera de una función")

    def test_undefined_variable_inside_function(self):
        self.assert_error("fn f() { print(z); }", "variable no definida 'z'")


if __name__ == "__main__":
    unittest.main()
