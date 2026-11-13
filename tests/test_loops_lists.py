import unittest

from tests.support import *
from src import ast_nodes as A
from src.lexer import Lexer
from src.parser import Parser
from src.semantic import SemanticError
from src.py_codegen import generate_python
from src.interp import InterpError


def parse(source):
    return Parser(Lexer(source).tokenize()).parse()


class LoopAndListParserTests(unittest.TestCase):
    def test_for_statement(self):
        stmt = parse("for (let i = 0; i < 3; i = i + 1) { print(i); }").items[0]
        self.assertIsInstance(stmt, A.ForStmt)
        self.assertIsInstance(stmt.init, A.LetStmt)
        self.assertIsInstance(stmt.update, A.AssignStmt)
        self.assertEqual(len(stmt.body), 1)

    def test_break_and_continue(self):
        body = parse("while (True) { break; continue; }").items[0].body
        self.assertIsInstance(body[0], A.BreakStmt)
        self.assertIsInstance(body[1], A.ContinueStmt)

    def test_list_literal(self):
        expr = parse("let a = [1, 2, 3];").items[0].expr
        self.assertIsInstance(expr, A.ListLit)
        self.assertEqual(len(expr.items), 3)

    def test_empty_list(self):
        expr = parse("let a: list = [];").items[0].expr
        self.assertIsInstance(expr, A.ListLit)
        self.assertEqual(expr.items, [])

    def test_index_expression(self):
        expr = parse("let x = a[1 + 1];").items[0].expr
        self.assertIsInstance(expr, A.Index)
        self.assertEqual(expr.target.name, "a")

    def test_index_assignment(self):
        stmt = parse("a[0] = 5;").items[0]
        self.assertIsInstance(stmt, A.SetIndexStmt)
        self.assertEqual(stmt.target.name, "a")

    def test_invalid_assignment_target(self):
        with self.assertRaisesRegex(Exception, "destino de asignación inválido"):
            parse("1 + 2 = 3;")

    def test_break_requires_semicolon(self):
        with self.assertRaisesRegex(Exception, "se esperaba ';'"):
            parse("while (True) { break }")

    def test_for_syntax_errors(self):
        with self.assertRaisesRegex(Exception, "';' después del inicializador del 'for'"):
            parse("for (let i = 0 i < 3; i = i + 1) { }")


class LoopAndListSemanticTests(unittest.TestCase):
    def assert_error(self, source, pattern):
        with self.assertRaisesRegex(SemanticError, pattern):
            compile_pipeline(source)

    def test_break_and_continue_only_in_loops(self):
        self.assert_error("break;", "'break' fuera de un ciclo")
        self.assert_error("continue;", "'continue' fuera de un ciclo")
        compile_pipeline("while (True) { break; }")
        compile_pipeline("for (let i = 0; i < 2; i = i + 1) { continue; }")
        compile_pipeline("for (let i = 0; i < 2; i = i + 1) { while (True) { break; } }")

    def test_for_condition_must_be_bool(self):
        self.assert_error("for (let i = 0; i; i = i + 1) { }", "la condición del 'for' debe ser bool")

    def test_for_variable_is_scoped_to_loop(self):
        self.assert_error("for (let i = 0; i < 2; i = i + 1) { } print(i);",
                          "variable no definida 'i'")

    def test_list_type(self):
        analyze = compile_pipeline("let a: list = [1, 2]; print(len(a));")
        self.assertIsNotNone(analyze)

    def test_list_cannot_be_assigned_to_int(self):
        self.assert_error("let a: int = [1, 2];", "no se puede asignar 'list' a 'int'")

    def test_index_requires_int(self):
        self.assert_error('let a = [1]; print(a["x"]);', "índice debe ser int")

    def test_cannot_index_int(self):
        self.assert_error("let a = 1; print(a[0]);", "no se puede indexar un valor de tipo 'int'")

    def test_set_index_requires_list(self):
        self.assert_error("let a: str = \"x\"; a[0] = 1;", "no se puede asignar a un índice de 'str'")

    def test_len_requires_str_or_list(self):
        self.assert_error("print(len(1));", "'len' espera 'str' o 'list'")


class LoopAndListIRTests(unittest.TestCase):
    def test_for_generates_loop_labels(self):
        _, _, ir = compile_pipeline("for (let i = 0; i < 3; i = i + 1) { print(i); }")
        ops = [i.op for i in ir]
        self.assertIn("label", ops)
        self.assertIn("ifFalse", ops)
        self.assertIn("goto", ops)

    def test_break_and_continue_are_gotos(self):
        _, _, ir = compile_pipeline(
            "while (True) { break; continue; }"
        )
        gotos = [i for i in ir if i.op == "goto"]
        self.assertGreaterEqual(len(gotos), 3)

    def test_list_instructions(self):
        _, _, ir = compile_pipeline("let a = [1, 2]; a[0] = a[1]; print(a[0]);")
        ops = [i.op for i in ir]
        self.assertIn("list", ops)
        self.assertIn("index", ops)
        self.assertIn("setindex", ops)

    def test_continue_in_for_targets_update_label(self):
        _, _, ir = compile_pipeline(
            "for (let i = 0; i < 3; i = i + 1) { continue; }"
        )
        labels = [i.a for i in ir if i.op == "label"]
        gotos = [i.a for i in ir if i.op == "goto"]
        self.assertIn(labels[-2], gotos)


class LoopAndListInterpreterTests(unittest.TestCase):
    def test_loops_example(self):
        self.assertEqual(
            run_source(example("loops.mb")),
            "18\n0\n2\n10\n12\n20\n22\n",
        )

    def test_arrays_example(self):
        self.assertEqual(
            run_source(example("arrays.mb")),
            "10\n20\n30\n40\n99\nana y luis\nh\n2\n",
        )

    def test_continue_runs_for_update(self):
        out = run_source(
            "let n = 0; "
            "for (let i = 0; i < 5; i = i + 1) { if (i == 2) { continue; } n = n + 1; } "
            "print(n);"
        )
        self.assertEqual(out, "4\n")

    def test_set_index_on_parameter(self):
        out = run_source(
            "fn fill(a: list) { a[0] = 7; } let xs = [1, 2]; fill(xs); print(xs[0]);"
        )
        self.assertEqual(out, "7\n")

    def test_index_out_of_range(self):
        _, sym, ir = compile_pipeline("let a = [1]; print(a[3]);")
        with self.assertRaisesRegex(InterpError, "fuera de rango"):
            Interpreter(ir, sym["globals"]).run()

    def test_optimized_loops_and_arrays_match(self):
        for name in ("loops.mb", "arrays.mb"):
            with self.subTest(example=name):
                self.assertEqual(run_source(example(name), opt=True),
                                 run_source(example(name)))


class LoopAndListBackendTests(unittest.TestCase):
    def test_examples_match_interpreter(self):
        for name in ("loops.mb", "arrays.mb"):
            with self.subTest(example=name):
                source = example(name)
                prog, _, _ = compile_pipeline(source)
                self.assertEqual(run_python(generate_python(prog)), run_source(source))

    def test_continue_in_for_emits_update(self):
        source = (
            "let n = 0; "
            "for (let i = 0; i < 5; i = i + 1) { if (i == 2) { continue; } n = n + 1; } "
            "print(n);"
        )
        prog, _, _ = compile_pipeline(source)
        code = generate_python(prog)
        self.assertIn("i = (i + 1)\n        continue", code)
        self.assertEqual(run_python(code), "4\n")

    def test_break_and_nested_loops(self):
        source = (
            "for (let i = 0; i < 3; i = i + 1) { "
            "  for (let j = 0; j < 3; j = j + 1) { "
            "    if (j == 1) { break; } print(i * 10 + j); } }"
        )
        prog, _, _ = compile_pipeline(source)
        self.assertEqual(run_python(generate_python(prog)), run_source(source))
