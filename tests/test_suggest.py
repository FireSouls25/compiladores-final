import unittest

from tests.support import *
from src.suggest import closest, distance
from src.parser import ParseError
from src.semantic import SemanticError


class DistanceTests(unittest.TestCase):
    def test_simple_typos(self):
        self.assertEqual(distance("print", "print"), 0)
        self.assertEqual(distance("prnt", "print"), 1)
        self.assertEqual(distance("lenght", "length"), 1)  # transposition

    def test_closest_ignores_far_names(self):
        self.assertEqual(closest("counter", ["counter", "count"]), "count")
        self.assertIsNone(closest("xyz", ["counter", "total"]))
        self.assertIsNone(closest("ab", ["abc"]))


class SemanticSuggestionTests(unittest.TestCase):
    def test_undefined_variable(self):
        with self.assertRaisesRegex(
            SemanticError, r"undefined variable 'cuonter' \(did you mean 'counter'\?"
        ):
            compile_pipeline("let counter = 1; print(cuonter);")

    def test_undefined_variable_in_function(self):
        with self.assertRaisesRegex(
            SemanticError, r"did you mean 'value'\?"
        ):
            compile_pipeline("fn f() { let value = 1; print(vlaue); }")

    def test_undefined_function(self):
        with self.assertRaisesRegex(
            SemanticError, r"undefined function 'factoral' \(did you mean 'factorial'\?"
        ):
            compile_pipeline(
                "fn factorial(n: int) -> int { return n; } print(factoral(3));"
            )

    def test_builtin_typo(self):
        with self.assertRaisesRegex(SemanticError, r"did you mean 'print'\?"):
            compile_pipeline('prnt("hola");')

    def test_no_suggestion_for_unrelated_name(self):
        with self.assertRaisesRegex(SemanticError, r"undefined variable 'zzzzzz'\s*$"):
            compile_pipeline("let counter = 1; print(zzzzzz);")


class ParserSuggestionTests(unittest.TestCase):
    def test_misspelled_keyword(self):
        with self.assertRaisesRegex(
            ParseError, r"unknown keyword 'whil' \(did you mean 'while'\?"
        ):
            compile_pipeline("whil (True) { print(1); }")

    def test_misspelled_type(self):
        with self.assertRaisesRegex(
            ParseError, r"did you mean 'int'\?"
        ):
            compile_pipeline("let x: integ = 1;")

    def test_valid_calls_are_not_reported_as_keywords(self):
        compile_pipeline("fn foo() { print(1); } foo();")
        compile_pipeline("fn lists() { print(1); } lists();")


if __name__ == "__main__":
    unittest.main()
