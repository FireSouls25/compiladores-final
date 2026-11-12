import unittest

from tests.support import *
from src.optimizer import optimize
from src.interp import InterpError


def opcodes(ir):
    return [i.op for i in ir]


class OptimizerTests(unittest.TestCase):
    def test_constant_folding_and_propagation(self):
        _, _, ir = compile_pipeline("print(2 + 3 * 4);", opt=True)
        calls = [i for i in ir if i.op == "call"]
        self.assertEqual(calls[0].b, [14])
        self.assertNotIn("binop", opcodes(ir))

    def test_dead_temporaries_are_removed(self):
        _, _, ir = compile_pipeline("print(2 + 3);", opt=True)
        self.assertEqual([i.op for i in ir], ["call"])

    def test_constant_condition_is_folded(self):
        _, _, ir = compile_pipeline(
            'if (True) { print("yes"); } else { print("no"); }', opt=True
        )
        self.assertNotIn("no", str(ir))
        self.assertNotIn("ifFalse", opcodes(ir))

    def test_unreachable_code_is_removed(self):
        _, _, ir = compile_pipeline(
            'fn f() -> int { return 1; print("dead"); }', opt=True
        )
        self.assertNotIn("dead", str(ir))

    def test_division_by_zero_is_not_folded(self):
        _, _, ir = compile_pipeline("let x = 1 / 0;", opt=True)
        self.assertIn("binop", opcodes(ir))
        _, sym, ir = compile_pipeline("let x = 1 / 0;", opt=True)
        from src.interp import Interpreter
        with self.assertRaisesRegex(InterpError, "division by zero"):
            Interpreter(ir, sym["globals"]).run()

    def test_optimizer_is_idempotent(self):
        _, _, ir = compile_pipeline(example("misc.mb"), opt=True)
        self.assertEqual(optimize(ir), ir)

    def test_labels_are_preserved(self):
        _, _, ir = compile_pipeline(
            "let i = 0; while (i < 3) { i = i + 1; }", opt=True
        )
        labels = {i.a for i in ir if i.op == "label"}
        jumps = {i.a for i in ir if i.op == "goto"}
        self.assertTrue(jumps <= labels)

    def test_optimizations_do_not_change_output(self):
        for name in ("hello.mb", "fib.mb", "misc.mb"):
            with self.subTest(example=name):
                self.assertEqual(
                    run_source(example(name), opt=True),
                    run_source(example(name)),
                )


if __name__ == "__main__":
    unittest.main()
