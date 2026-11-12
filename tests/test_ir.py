import unittest

from tests.support import *
from src.ir_gen import Instr


def generate(source):
    _, _, ir = compile_pipeline(source)
    return ir


class IRTests(unittest.TestCase):
    def test_function_markers(self):
        ir = generate("fn add(a: int, b: int) -> int { return a + b; }")
        self.assertEqual(ir[0].op, "func_begin")
        self.assertEqual(ir[0].a, "add")
        self.assertEqual(ir[0].c, ["a", "b"])
        self.assertEqual(ir[-1].op, "func_end")

    def test_temporaries_and_labels_use_reserved_prefix(self):
        ir = generate("fn f(n: int) -> int { return n + 1; } print(f(2));")
        temps = [i.a for i in ir if isinstance(i.a, str) and i.a.startswith("%")]
        self.assertTrue(temps)
        self.assertTrue(all(t[1:2] in ("t", "L") for t in temps))

    def test_user_variable_named_like_old_temp_is_safe(self):
        # Regression: `t1` used to collide with generated temporaries.
        ir = generate("let t1 = 5; print(t1 + 1);")
        self.assertIn("t1", [i.a for i in ir if i.op == "assign"])
        self.assertNotIn("t2", [i.a for i in ir if i.op == "assign"])

    def test_shadowed_variable_uses_resolved_name(self):
        ir = generate("let x = 1; { let x = 2; print(x); }")
        assigned = [i.a for i in ir if i.op == "assign"]
        self.assertIn("x", assigned)
        self.assertIn("x$1", assigned)

    def test_while_generates_labels_and_jumps(self):
        ir = generate("let i = 0; while (i < 3) { i = i + 1; }")
        ops = [i.op for i in ir]
        self.assertIn("label", ops)
        self.assertIn("ifFalse", ops)
        self.assertIn("goto", ops)

    def test_string_constants_are_encoded(self):
        ir = generate('print("hi");')
        call = next(i for i in ir if i.op == "call")
        self.assertEqual(call.b, ["@hi"])

    def test_void_function_gets_implicit_return(self):
        ir = generate("fn f() { print(1); }")
        returns = [i for i in ir if i.op == "return"]
        self.assertEqual(len(returns), 1)
        self.assertIsNone(returns[0].a)


if __name__ == "__main__":
    unittest.main()
