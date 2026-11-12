"""Phase 2: Parser (syntactic analysis). Tokens -> AST (recursive descent)."""
from . import tokens as T
from . import ast_nodes as A


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, toks: list):
        self.toks = toks
        self.i = 0

    # -- helpers --
    def peek(self):
        return self.toks[self.i]

    def previous(self):
        return self.toks[self.i - 1]

    def at_end(self):
        return self.peek().type == T.EOF

    def check(self, *types):
        return self.peek().type in types

    def advance(self):
        if not self.at_end():
            self.i += 1
        return self.previous()

    def match(self, *types):
        if self.check(*types):
            return self.advance()
        return None

    def expect(self, type_, what):
        if self.check(type_):
            return self.advance()
        t = self.peek()
        raise ParseError(f"{t.line}:{t.col}: expected {what}, found {t.lexeme!r}")

    # -- entry --
    def parse(self) -> A.Program:
        items = []
        while not self.at_end():
            if self.check(T.FN):
                items.append(self.func_def())
            else:
                items.append(self.stmt())
        return A.Program(items)

    # fn name(a: int, b: int) -> int { ... }
    def func_def(self) -> A.FuncDef:
        fn = self.expect(T.FN, "'fn'")
        name = self.expect(T.IDENT, "function name")
        self.expect(T.LPAREN, "'('")
        params: list[A.Param] = []
        if not self.check(T.RPAREN):
            params.append(self.param())
            while self.match(T.COMMA):
                params.append(self.param())
        self.expect(T.RPAREN, "')'")
        ret = "None"
        if self.match(T.ARROW):
            ret = self.type_name()
        self.expect(T.LBRACE, "'{'")
        body = self.stmt_list()
        self.expect(T.RBRACE, "'}'")
        return A.FuncDef(name.lexeme, params, ret, body, fn.line, fn.col)

    def param(self) -> A.Param:
        t = self.expect(T.IDENT, "parameter name")
        ann = None
        if self.match(T.COLON):
            ann = self.type_name()
        return A.Param(t.lexeme, ann, t.line, t.col)

    def type_name(self) -> str:
        t = self.advance()
        m = {T.TYPE_INT: "int", T.TYPE_FLOAT: "float", T.TYPE_STR: "str",
             T.TYPE_BOOL: "bool", T.NONE: "None"}
        if t.type in m:
            return m[t.type]
        raise ParseError(f"{t.line}:{t.col}: expected a type (int/float/str/bool/None), found {t.lexeme!r}")

    def stmt_list(self) -> list:
        out = []
        while not self.check(T.RBRACE, T.EOF):
            out.append(self.stmt())
        return out

    def stmt(self):
        if self.check(T.LET):
            return self.let_stmt()
        if self.check(T.IF):
            return self.if_stmt()
        if self.check(T.WHILE):
            return self.while_stmt()
        if self.check(T.RETURN):
            return self.return_stmt()
        if self.check(T.LBRACE):
            return self.block_stmt()
        # assign vs expression-statement: IDENT '=' (and next is not '==')
        if self.check(T.IDENT) and self.i + 1 < len(self.toks):
            nxt = self.toks[self.i + 1]
            if nxt.type == T.EQ:
                return self.assign_stmt()
        return self.expr_stmt()

    def block_stmt(self):
        lb = self.expect(T.LBRACE, "'{'")
        stmts = self.stmt_list()
        self.expect(T.RBRACE, "'}'")
        return A.Block(stmts, lb.line, lb.col)

    def let_stmt(self):
        kw = self.expect(T.LET, "'let'")
        name = self.expect(T.IDENT, "variable name")
        ann = None
        if self.match(T.COLON):
            ann = self.type_name()
        self.expect(T.EQ, "'='")
        e = self.expr()
        self.expect(T.SEMI, "';'")
        return A.LetStmt(name.lexeme, ann, e, kw.line, kw.col)

    def assign_stmt(self):
        name = self.expect(T.IDENT, "variable name")
        self.expect(T.EQ, "'='")
        e = self.expr()
        self.expect(T.SEMI, "';'")
        return A.AssignStmt(name.lexeme, e, name.line, name.col)

    def if_stmt(self):
        kw = self.expect(T.IF, "'if'")
        self.expect(T.LPAREN, "'(' after 'if'")
        cond = self.expr()
        self.expect(T.RPAREN, "')'")
        self.expect(T.LBRACE, "'{'")
        then_b = self.stmt_list()
        self.expect(T.RBRACE, "'}'")
        else_b: list = []
        if self.match(T.ELSE):
            if self.check(T.IF):
                else_b = [self.if_stmt()]  # else-if chain
            else:
                self.expect(T.LBRACE, "'{' after 'else'")
                else_b = self.stmt_list()
                self.expect(T.RBRACE, "'}'")
        return A.IfStmt(cond, then_b, else_b, kw.line, kw.col)

    def while_stmt(self):
        kw = self.expect(T.WHILE, "'while'")
        self.expect(T.LPAREN, "'(' after 'while'")
        cond = self.expr()
        self.expect(T.RPAREN, "')'")
        self.expect(T.LBRACE, "'{'")
        body = self.stmt_list()
        self.expect(T.RBRACE, "'}'")
        return A.WhileStmt(cond, body, kw.line, kw.col)

    def return_stmt(self):
        kw = self.expect(T.RETURN, "'return'")
        e = None
        if not self.check(T.SEMI):
            e = self.expr()
        self.expect(T.SEMI, "';'")
        return A.ReturnStmt(e, kw.line, kw.col)

    def expr_stmt(self):
        e = self.expr()
        t = self.peek()
        self.expect(T.SEMI, "';'")
        line = getattr(e, "line", t.line)
        col = getattr(e, "col", t.col)
        return A.ExprStmt(e, line, col)

    # -- expressions (precedence climbing) --
    def expr(self):
        return self.or_expr()

    def or_expr(self):
        e = self.and_expr()
        while self.match(T.OR):
            op = self.previous()
            rhs = self.and_expr()
            e = A.BinOp("or", e, rhs, op.line, op.col)
        return e

    def and_expr(self):
        e = self.equality()
        while self.match(T.AND):
            op = self.previous()
            rhs = self.equality()
            e = A.BinOp("and", e, rhs, op.line, op.col)
        return e

    def equality(self):
        e = self.comparison()
        while True:
            op = self.match(T.EQEQ, T.NEQ)
            if not op:
                return e
            rhs = self.comparison()
            e = A.BinOp(op.lexeme, e, rhs, op.line, op.col)

    def comparison(self):
        e = self.additive()
        while True:
            op = self.match(T.LT, T.LTE, T.GT, T.GTE)
            if not op:
                return e
            rhs = self.additive()
            e = A.BinOp(op.lexeme, e, rhs, op.line, op.col)

    def additive(self):
        e = self.multiplicative()
        while True:
            op = self.match(T.PLUS, T.MINUS)
            if not op:
                return e
            rhs = self.multiplicative()
            e = A.BinOp(op.lexeme, e, rhs, op.line, op.col)

    def multiplicative(self):
        e = self.unary()
        while True:
            op = self.match(T.STAR, T.SLASH, T.PERCENT)
            if not op:
                return e
            rhs = self.unary()
            e = A.BinOp(op.lexeme, e, rhs, op.line, op.col)

    def unary(self):
        op = self.match(T.MINUS, T.NOT)
        if op:
            sub = self.unary()
            name = "not" if op.type == T.NOT else "-"
            return A.UnaryOp(name, sub, op.line, op.col)
        return self.primary()

    def primary(self):
        t = self.peek()
        if self.match(T.INT_LIT):
            return A.Literal(t.value, "int", t.line, t.col)
        if self.match(T.FLOAT_LIT):
            return A.Literal(t.value, "float", t.line, t.col)
        if self.match(T.STRING_LIT):
            return A.Literal(t.value, "str", t.line, t.col)
        if self.match(T.TRUE):
            return A.Literal(True, "bool", t.line, t.col)
        if self.match(T.FALSE):
            return A.Literal(False, "bool", t.line, t.col)
        if self.match(T.NONE):
            return A.Literal(None, "None", t.line, t.col)
        if self.match(T.IDENT):
            if self.check(T.LPAREN):
                self.advance()  # '('
                args = []
                if not self.check(T.RPAREN):
                    args.append(self.expr())
                    while self.match(T.COMMA):
                        args.append(self.expr())
                self.expect(T.RPAREN, "')'")
                return A.Call(t.lexeme, args, t.line, t.col)
            return A.Var(t.lexeme, t.line, t.col)
        if self.match(T.LPAREN):
            e = self.expr()
            self.expect(T.RPAREN, "')'")
            return e
        raise ParseError(f"{t.line}:{t.col}: unexpected {t.lexeme!r} in expression")
