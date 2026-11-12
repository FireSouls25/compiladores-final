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
        for name in ("hello.mb", "fib.mb", "misc.mb", "loops.mb", "arrays.mb"):
            with self.subTest(example=name):
                self.assertEqual(
                    run_source(example(name), opt=True),
                    run_source(example(name)),
                )


class AdvancedOptimizerTests(unittest.TestCase):
    def test_variable_constant_propagation(self):
        _, _, ir = compile_pipeline("let a = 2; let b = 3; print(a + b);", opt=True)
        calls = [i for i in ir if i.op == "call"]
        self.assertEqual(calls[0].b, [5])

    def test_dead_loop_with_constant_false_variable(self):
        source = 'let run = False; while (run) { print("x"); } print("y");'
        _, _, ir = compile_pipeline(source, opt=True)
        self.assertNotIn("x", str(ir))
        self.assertIn("y", str(ir))
        self.assertEqual(run_source(source, opt=True), "y\n")

    def test_infinite_loop_removes_following_code(self):
        _, _, ir = compile_pipeline("while (True) { print(1); } print(2);", opt=True)
        calls = [i for i in ir if i.op == "call"]
        self.assertEqual([c.b for c in calls], [[1]])

    def test_loop_invariant_code_is_hoisted(self):
        source = (
            "fn f(a: int, b: int) { let i = 0; "
            "while (i < 3) { print(a + b); i = i + 1; } } f(10, 20);"
        )
        _, _, ir = compile_pipeline(source, opt=True)
        header = next(i for i, ins in enumerate(ir) if ins.op == "label")
        sum_idx = next(
            i for i, ins in enumerate(ir)
            if ins.op == "binop" and ins.b == "a" and ins.extra == "b"
        )
        self.assertLess(sum_idx, header)
        self.assertEqual(run_source(source, opt=True), "30\n30\n30\n")

    def test_loop_changing_value_is_not_hoisted(self):
        source = (
            "fn f(a: int) { let i = 0; "
            "while (i < 3) { print(i + a); i = i + 1; } } f(10);"
        )
        _, _, ir = compile_pipeline(source, opt=True)
        header = next(i for i, ins in enumerate(ir) if ins.op == "label")
        changing = next(
            i for i, ins in enumerate(ir)
            if ins.op == "binop" and ins.b == "i" and ins.c == "+"
        )
        self.assertGreater(changing, header)

    def test_division_is_not_hoisted(self):
        source = (
            "fn f(a: int, b: int) { let i = 0; "
            "while (i < 2) { print(a / b); i = i + 1; } } f(10, 2);"
        )
        _, _, ir = compile_pipeline(source, opt=True)
        header = next(i for i, ins in enumerate(ir) if ins.op == "label")
        div = next(i for i, ins in enumerate(ir) if ins.op == "binop" and ins.c == "/")
        self.assertGreater(div, header)

    def test_user_call_does_not_invalidate_parameters(self):
        # `print(a + b)` can still be hoisted: parameters cannot change.
        source = (
            "fn f(a: int, b: int) { let i = 0; "
            "while (i < 2) { print(a + b); i = i + 1; } } f(1, 2);"
        )
        self.assertEqual(run_source(source, opt=True), "3\n3\n")

    def test_user_call_blocks_global_hoisting(self):
        source = (
            "let g = 1; fn change() { g = 2; } "
            "fn f() { let i = 0; while (i < 2) { print(g + 1); change(); i = i + 1; } } "
            "f();"
        )
        # If `g + 1` were hoisted, the output would be 2, 2.
        self.assertEqual(run_source(source, opt=True), "2\n3\n")


if __name__ == "__main__":
    unittest.main()
