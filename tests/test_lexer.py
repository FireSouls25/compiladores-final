import unittest

from tests.support import *
from src import tokens as T
from src.lexer import Lexer, LexError


def types(source):
    return [t.type for t in Lexer(source).tokenize()]


class LexerTests(unittest.TestCase):
    def test_basic_tokens(self):
        self.assertEqual(
            types("let x: int = 1 + 2;"),
            [T.LET, T.IDENT, T.COLON, T.TYPE_INT, T.EQ, T.INT_LIT,
             T.PLUS, T.INT_LIT, T.SEMI, T.EOF],
        )

    def test_float_literal(self):
        toks = Lexer("1.5 2 3.0").tokenize()
        self.assertEqual(toks[0].type, T.FLOAT_LIT)
        self.assertEqual(toks[0].value, 1.5)
        self.assertEqual(toks[1].type, T.INT_LIT)
        self.assertEqual(toks[2].value, 3.0)

    def test_comment_is_skipped(self):
        self.assertEqual(types("# hola\nlet x = 1;")[0], T.LET)

    def test_string_escapes(self):
        tok = Lexer(r'let s = "a\nb\t\"c";').tokenize()[3]
        self.assertEqual(tok.type, T.STRING_LIT)
        self.assertEqual(tok.value, 'a\nb\t"c')

    def test_positions(self):
        toks = Lexer("let\n  x = 1;").tokenize()
        x = toks[1]
        self.assertEqual((x.line, x.col), (2, 3))

    def test_bom_is_ignored(self):
        self.assertEqual(types("\ufefflet x = 1;")[0], T.LET)

    def test_keywords_are_case_sensitive(self):
        toks = Lexer("let Let True true").tokenize()
        self.assertEqual(toks[1].type, T.IDENT)
        self.assertEqual(toks[3].type, T.IDENT)

    def test_unexpected_character(self):
        with self.assertRaisesRegex(LexError, r"1:1: carácter no reconocido"):
            Lexer("@").tokenize()

    def test_unterminated_string(self):
        with self.assertRaisesRegex(LexError, "cadena sin cerrar"):
            Lexer('"abc').tokenize()


if __name__ == "__main__":
    unittest.main()
