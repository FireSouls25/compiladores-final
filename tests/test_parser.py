import unittest

from tests.support import *
from src import ast_nodes as A
from src.lexer import Lexer
from src.parser import Parser, ParseError


def parse(source):
    return Parser(Lexer(source).tokenize()).parse()


class ParserTests(unittest.TestCase):
    def test_precedence(self):
        prog = parse("let x = 1 + 2 * 3;")
        expr = prog.items[0].expr
        self.assertIsInstance(expr, A.BinOp)
        self.assertEqual(expr.op, "+")
        self.assertIsInstance(expr.right, A.BinOp)
        self.assertEqual(expr.right.op, "*")

    def test_parentheses_override_precedence(self):
        expr = parse("let x = (1 + 2) * 3;").items[0].expr
        self.assertEqual(expr.op, "*")
        self.assertIsInstance(expr.left, A.BinOp)

    def test_comparison_and_logic_levels(self):
        expr = parse("let x = a < b and c;").items[0].expr
        self.assertEqual(expr.op, "and")
        self.assertEqual(expr.left.op, "<")

    def test_function_definition(self):
        fn = parse("fn add(a: int, b: int) -> int { return a + b; }").items[0]
        self.assertIsInstance(fn, A.FuncDef)
        self.assertEqual([p.name for p in fn.params], ["a", "b"])
        self.assertEqual(fn.ret, "int")
        self.assertIsInstance(fn.body[0], A.ReturnStmt)

    def test_void_function(self):
        fn = parse("fn f() { print(1); }").items[0]
        self.assertEqual(fn.ret, "None")

    def test_else_if_chain(self):
        stmt = parse("if (True) { print(1); } else if (False) { print(2); } else { print(3); }").items[0]
        self.assertIsInstance(stmt, A.IfStmt)
        self.assertIsInstance(stmt.else_body[0], A.IfStmt)

    def test_bare_block(self):
        stmt = parse("{ let x = 1; }").items[0]
        self.assertIsInstance(stmt, A.Block)

    def test_missing_semicolon(self):
        with self.assertRaisesRegex(ParseError, r"1:10: expected ';'"):
            parse("let x = 1")

    def test_error_at_eof_is_readable(self):
        with self.assertRaisesRegex(ParseError, "end of file"):
            parse("fn f(a: int")

    def test_unexpected_expression(self):
        with self.assertRaisesRegex(ParseError, "unexpected"):
            parse("let x = ;")


if __name__ == "__main__":
    unittest.main()
