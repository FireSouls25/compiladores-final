"""Phase 1: Lexer (lexical analysis). Source text -> list[Token]."""
from . import tokens as T
from .tokens import Token


class LexError(Exception):
    pass


class Lexer:
    def __init__(self, source: str):
        # Tolerate a UTF-8 BOM (common on Windows editors).
        if source.startswith("\ufeff"):
            source = source[1:]
        self.src = source
        self.n = len(source)
        self.i = 0
        self.line = 1
        self.col = 1
        self.toks: list[Token] = []

    def error(self, msg: str) -> LexError:
        return LexError(f"{self.line}:{self.col}: {msg}")

    def peek(self) -> str:
        return self.src[self.i] if self.i < self.n else "\0"

    def peek2(self) -> str:
        return self.src[self.i + 1] if self.i + 1 < self.n else "\0"

    def advance(self) -> str:
        ch = self.src[self.i]
        self.i += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def add(self, type_: str, lexeme: str, value=None, line=None, col=None):
        self.toks.append(Token(type_, lexeme, value, line, col))

    def tokenize(self) -> list[Token]:
        while self.i < self.n:
            ch = self.peek()
            if ch in " \t\r\n":
                self.advance()
            elif ch == "#":
                while self.i < self.n and self.peek() != "\n":
                    self.advance()
            elif ch.isdigit():
                self.lex_number()
            elif ch.isalpha() or ch == "_":
                self.lex_ident()
            elif ch in ("'", '"'):
                self.lex_string()
            else:
                self.lex_symbol()
        self.toks.append(Token(T.EOF, "", None, self.line, self.col))
        return self.toks

    def lex_number(self):
        line, col = self.line, self.col
        start = self.i
        while self.peek().isdigit():
            self.advance()
        if self.peek() == "." and self.peek2().isdigit():
            self.advance()  # consume '.'
            while self.peek().isdigit():
                self.advance()
            lex = self.src[start:self.i]
            self.add(T.FLOAT_LIT, lex, float(lex), line, col)
        else:
            lex = self.src[start:self.i]
            self.add(T.INT_LIT, lex, int(lex), line, col)

    def lex_ident(self):
        line, col = self.line, self.col
        start = self.i
        while self.peek().isalnum() or self.peek() == "_":
            self.advance()
        lex = self.src[start:self.i]
        type_ = T.KEYWORDS.get(lex, T.IDENT)
        self.add(type_, lex, lex, line, col)

    def lex_string(self):
        line, col = self.line, self.col
        quote = self.advance()
        buf: list[str] = []
        while True:
            if self.i >= self.n:
                raise self.error("unterminated string literal")
            ch = self.advance()
            if ch == quote:
                break
            if ch == "\\":
                if self.i >= self.n:
                    raise self.error("unterminated string escape")
                e = self.advance()
                buf.append({"n": "\n", "t": "\t", "r": "\r",
                            "\\": "\\", "'": "'", '"': '"',
                            "0": "\0"}.get(e, e))
            elif ch == "\n":
                raise self.error("unterminated string literal (newline)")
            else:
                buf.append(ch)
        self.add(T.STRING_LIT, quote + "".join(buf) + quote, "".join(buf), line, col)

    def lex_symbol(self):
        line, col = self.line, self.col
        ch = self.peek()
        nxt = self.peek2()
        two = ch + nxt
        if two in ("==", "!=", "<=", ">=", "->"):
            self.advance()
            self.advance()
            m = {"==": T.EQEQ, "!=": T.NEQ, "<=": T.LTE,
                 ">=": T.GTE, "->": T.ARROW}
            self.add(m[two], two, two, line, col)
            return
        single = {
            "+": T.PLUS, "-": T.MINUS, "*": T.STAR, "/": T.SLASH,
            "%": T.PERCENT, "=": T.EQ, "<": T.LT, ">": T.GT,
            ":": T.COLON, ",": T.COMMA, ";": T.SEMI,
            "(": T.LPAREN, ")": T.RPAREN,
            "{": T.LBRACE, "}": T.RBRACE,
        }
        if ch in single:
            self.advance()
            self.add(single[ch], ch, ch, line, col)
            return
        if ch == "!":
            raise self.error("unexpected '!' (did you mean '!='?)")
        raise self.error(f"unexpected character {ch!r}")
