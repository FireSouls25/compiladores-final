from dataclasses import dataclass
from typing import Any

FN = "FN"
LET = "LET"
IF = "IF"
ELSE = "ELSE"
WHILE = "WHILE"
FOR = "FOR"
BREAK = "BREAK"
CONTINUE = "CONTINUE"
RETURN = "RETURN"
AND = "AND"
OR = "OR"
NOT = "NOT"
TRUE = "TRUE"
FALSE = "FALSE"
NONE = "NONE"
TYPE_INT = "TYPE_INT"
TYPE_FLOAT = "TYPE_FLOAT"
TYPE_STR = "TYPE_STR"
TYPE_BOOL = "TYPE_BOOL"
TYPE_LIST = "TYPE_LIST"
IDENT = "IDENT"
INT_LIT = "INT_LIT"
FLOAT_LIT = "FLOAT_LIT"
STRING_LIT = "STRING_LIT"
PLUS = "PLUS"
MINUS = "MINUS"
STAR = "STAR"
SLASH = "SLASH"
PERCENT = "PERCENT"
EQ = "EQ"
EQEQ = "EQEQ"
NEQ = "NEQ"
LT = "LT"
LTE = "LTE"
GT = "GT"
GTE = "GTE"
COLON = "COLON"
COMMA = "COMMA"
SEMI = "SEMI"
LPAREN = "LPAREN"
RPAREN = "RPAREN"
LBRACE = "LBRACE"
RBRACE = "RBRACE"
LBRACKET = "LBRACKET"
RBRACKET = "RBRACKET"
ARROW = "ARROW"
EOF = "EOF"

KEYWORDS = {
    "fn": FN,
    "let": LET,
    "if": IF,
    "else": ELSE,
    "while": WHILE,
    "for": FOR,
    "break": BREAK,
    "continue": CONTINUE,
    "return": RETURN,
    "and": AND,
    "or": OR,
    "not": NOT,
    "True": TRUE,
    "False": FALSE,
    "None": NONE,
    "int": TYPE_INT,
    "float": TYPE_FLOAT,
    "str": TYPE_STR,
    "bool": TYPE_BOOL,
    "list": TYPE_LIST,
}


@dataclass
class Token:
    type: str
    lexeme: str
    value: Any
    line: int
    col: int

    def __repr__(self) -> str:
        return f"Token({self.type}, {self.lexeme!r}, {self.line}:{self.col})"
