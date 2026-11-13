# MiniB — compilador e intérprete para un lenguaje pequeño

MiniB es un lenguaje de programación tipado, con funciones, bloques, ciclos y
tipos básicos. Este repositorio implementa **todas las fases de un compilador**
en Python, sin dependencias externas:

```text
fuente .mb
   │
   ▼
┌─────────┐   ┌─────────┐   ┌────────────┐   ┌─────────────┐   ┌──────────┐
│  Lexer  │──▶│ Parser  │──▶│ Semántico  │──▶│ Generador   │──▶│ Optimizador│
│ tokens  │   │  AST    │   │ tipos +    │   │ de TAC (IR) │   │ (opcional)│
└─────────┘   └─────────┘   │ scopes     │   └─────────────┘   └────┬─────┘
                            └────────────┘                          │
                                                                    ▼
                                                     ┌────────────────────────┐
                                                     │ Intérprete de TAC      │
                                                     │ o backend a Python 3   │
                                                     └────────────────────────┘
```

## Estructura

| Archivo | Fase | Responsabilidad |
|---|---|---|
| `src/tokens.py` | — | Definición de tokens y palabras reservadas |
| `src/lexer.py` | 1. Léxica | Texto → lista de tokens (con línea/columna) |
| `src/ast_nodes.py` | 2. Sintáctica | Nodos del AST |
| `src/parser.py` | 2. Sintáctica | Parser descendente recursivo (precedencia por niveles) |
| `src/semantic.py` | 3. Semántica | Tabla de símbolos, tipos, scopes, retornos, resolución de nombres |
| `src/ir_gen.py` | 4. IR | AST → código de tres direcciones (TAC) |
| `src/optimizer.py` | 4.5 Optimización | Plegado de constantes, propagación, código muerto |
| `src/interp.py` | 5. Ejecución | Intérprete iterativo del TAC |
| `src/asm_gen.py` | 6. Código objetivo | TAC → ensamblador simulado: registros R0..Rn, spill/LOAD, marcos de pila |
| `src/py_codegen.py` | 6. Backend alterno | AST resuelto → programa Python 3 ejecutable |
| `src/fases.py` | — | Modo `--fases`: narra paso a paso lo que hace cada fase |
| `src/diagnostics.py` | — | Errores con `archivo:línea:columna`, tipo de error y fragmento de código |
| `src/__main__.py` | — | CLI (`python -m src`) |

## Gramática (EBNF)

```ebnf
program     = { func_def | statement } ;
func_def    = "fn" IDENT "(" [ param { "," param } ] ")"
              [ "->" type ] "{" { statement } "}" ;
param       = IDENT [ ":" type ] ;
type        = "int" | "float" | "str" | "bool" | "list" | "None" ;

statement   = let_stmt | assign_stmt | if_stmt | while_stmt | for_stmt
            | break_stmt | continue_stmt | return_stmt | block
            | set_index_stmt | expr_stmt ;
let_stmt    = "let" IDENT [ ":" type ] "=" expr ";" ;
assign_stmt = IDENT "=" expr ";" ;
set_index_stmt = IDENT "[" expr "]" "=" expr ";" ;
if_stmt     = "if" "(" expr ")" block [ "else" ( block | if_stmt ) ] ;
while_stmt  = "while" "(" expr ")" block ;
for_stmt    = "for" "(" for_head ";" expr ";" for_head ")" block ;
for_head    = let_stmt_without_semi | assign_stmt_without_semi | expr ;
break_stmt  = "break" ";" ;
continue_stmt = "continue" ";" ;
return_stmt = "return" [ expr ] ";" ;
block       = "{" { statement } "}" ;
expr_stmt   = expr ";" ;

expr        = or_expr ;
or_expr     = and_expr { "or" and_expr } ;
and_expr    = equality { "and" equality } ;
equality    = comparison { ( "==" | "!=" ) comparison } ;
comparison  = additive { ( "<" | "<=" | ">" | ">=" ) additive } ;
additive    = multiplicative { ( "+" | "-" ) multiplicative } ;
multiplicative = unary { ( "*" | "/" | "%" ) unary } ;
unary       = ( "-" | "not" ) unary | primary ;
primary     = INT | FLOAT | STRING | "True" | "False" | "None"
            | "[" [ expr { "," expr } ] "]"
            | IDENT [ "(" [ expr { "," expr } ] ")" ] { "[" expr "]" }
            | "(" expr ")" ;
```

Los comentarios empiezan con `#` y llegan hasta el final de la línea.
Las cadenas aceptan comillas simples o dobles y escapes (`\n`, `\t`, `\\`, `\"`).

## Semántica

- **Tipos:** `int`, `float`, `str`, `bool`, `list`, `None`; una anotación omitida se infiere.
- **Promoción:** `int` se puede asignar/pasar donde se espera `float`, pero no al revés.
- **Operadores:** `+` concatena `str` y suma números; `*` repite `str * int`; `%` y `/`
  son numéricos (`/` siempre devuelve `float`); `<`, `<=`, `>`, `>=` requieren números;
  `and`, `or`, `not` requieren `bool`.
- **Listas:** `[1, 2, 3]` crea una lista; `a[i]` lee (también sirve para `str`) y
  `a[i] = v` escribe. El índice debe ser `int`; el tipo del elemento no se restringe.
- **Scopes:** `let` es local al bloque; la variable de un `for` vive solo en el bucle.
  Las variables sombreadas se renombran (`x$1`), así que el shadowing funciona
  también en el IR plano y en Python.
- **Bucles:** `while`, `for (init; cond; update)` y `break` / `continue`. En un
  `for`, `continue` ejecuta el `update` antes de volver a evaluar la condición.
- **Funciones:** se pueden llamar antes de definirse; se valida aridad, tipos de
  parámetros y de retorno. Una función con retorno distinto de `None` debe
  retornar en **todos** los caminos.
- **Builtins:** `print(...)`, `len(str | list)`, `input()` / `input(prompt)`.
- **Globales:** una asignación dentro de una función a una global existente
  modifica la global.

## Uso

Requiere Python 3.10 o superior. No hay dependencias para ejecutar el compilador
(pytest solo se usa para las pruebas).

```powershell
# Ejecutar un programa
python -m src examples\hello.mb

# Ver cómo trabaja cada fase, paso a paso (tokens, AST, ámbitos y tipos,
# cuádruplas, registros/spill, stack y heap en ejecución)
python -m src examples\hello.mb --fases
python -m src examples\registros.mb --fases --opt

# Volcados crudos de cada fase
python -m src examples\fib.mb --dump-tokens --dump-ast --dump-ir --no-run

# Ensamblador simulado (por defecto 3 registros)
python -m src examples\registros.mb --emit-asm
python -m src examples\registros.mb --emit-asm --registros 4

# Optimizar antes de ejecutar y ver el TAC resultante
python -m src examples\misc.mb --opt --dump-ir

# Compilar a Python 3
python -m src examples\hello.mb --emit-py
python -m src examples\hello.mb --emit-py -o hello.py
python hello.py
```

Códigos de salida: `0` correcto, `1` error de compilación o de ejecución,
`2` error de lectura/escritura de archivos.

### Ejemplo de IR

Para `fn add(a: int, b: int) -> int { return a + b; }`:

```text
func add(a, b):
  %t1 = a + b
  return %t1
endfunc add
```

Los temporales (`%tN`) y etiquetas (`%LN`) usan prefijos imposibles en un
identificador MiniB, por lo que nunca chocan con variables del usuario.

### Optimizador

`--opt` aplica, hasta punto fijo: plegado de constantes, propagación de
temporales y de variables constantes, eliminación de condiciones constantes,
**movimiento de código invariante fuera de los bucles (LICM)**, eliminación de
bucles muertos (condición constante), bloques inalcanzables y temporales
muertos. Las llamadas nunca se eliminan porque pueden tener efectos (por ejemplo
`print`), y la división/módulo no se mueven porque pueden fallar en ejecución.

```text
# sin --opt
%t1 = 3 * 4
%t2 = 2 + %t1
call print(%t2)

# con --opt
call print(14)
```

### Código objetivo (ensamblador simulado)

`--emit-asm` traduce el TAC a un ensamblador didáctico. No se ejecuta en hardware
real: simula las decisiones del back-end de la Semana 10.

- **Selección de instrucciones:** `ADD`, `SUB`, `MUL`, `DIV`, `SLT`, `CMP`/`JE`, `JMP`, `CALL`/`RET`, `CONCAT`...
- **Asignación de registros:** cada temporal `%tN` recibe el primer registro libre;
  al terminar su vida útil (*liveness*) el registro se libera y se reutiliza.
- **Spill:** si no quedan registros, se expulsa el temporal cuyo próximo uso está
  más lejos (`STORE Rk, [SP+n]`) y se recarga cuando vuelve a usarse (`LOAD`).
- **Memoria:** globales en `.data`; parámetros en `[FP+8]...` y locales en `[FP-4]...`
  dentro del marco de pila (`PUSH FP / MOV FP, SP ... MOV SP, FP / POP FP / RET`);
  las listas se reservan en el heap con `ALLOC`.

```text
    STORE R0, [SP+0]              ; spill de %t3
    ...
    LOAD R1, [SP+0]               ; recarga %t3
```

### Backend Python

`--emit-py` traduce el AST ya resuelto a Python 3. El código generado es
ejecutable y conserva el comportamiento del intérprete (los tests lo comparan
para todos los ejemplos). El renombrado de variables sombreadas evita las
diferencias entre el alcance por bloques de MiniB y el alcance por funciones de
Python.

## Errores

Los errores de compilación muestran el archivo, la posición y la línea exacta:

```text
examples\error.mb:2:1: error semántico: no se puede asignar 'str' a 'int' en 'let x'
   2 > let x: int = "ups";
       ^
```

Cada mensaje indica la fase que lo detectó: `error léxico`, `error sintáctico`,
`error semántico` o `error de ejecución`.

La fase semántica reporta **todos** los errores que encuentra, no solo el primero.
Los errores de ejecución se reportan como `error de ejecución` (por ejemplo,
división por cero). Los nombres mal escritos incluyen una sugerencia:

```text
examples\typo.mb:3:7: error semántico: variable no definida 'cuonter' (¿quisiste decir 'counter'?)
```

## Pruebas

```powershell
python -m pytest
# o, sin pytest:
python -m unittest discover -s tests -t .
```

La suite cubre lexer, parser, semántica, IR, optimizador, intérprete, backend,
sugerencias y CLI (130+ casos, incluidos los ejemplos completos).

## Ejemplos incluidos

| Archivo | Demuestra |
|---|---|
| `examples/hello.mb` | funciones, llamadas, concatenación |
| `examples/fib.mb` | recursión y `while` |
| `examples/misc.mb` | tipos, `if/else`, floats, strings, bools |
| `examples/scope.mb` | shadowing, `else if`, estado global |
| `examples/loops.mb` | `for`, `break`, `continue`, bucles anidados |
| `examples/arrays.mb` | listas, índices, mutación, `len` |
| `examples/registros.mb` | presión de registros: provoca spill con 3 registros |
| `examples/error.mb` | diagnóstico semántico |
| `examples/typo.mb` | sugerencia por nombre mal escrito |

## Limitaciones y siguientes pasos

- Las listas no tienen tipo de elemento ni funciones propias (`push`, `pop`, ...);
  se accede con índice y `len`.
- El optimizador no hace análisis interprocedimental: una llamada a una función
  dentro de un bucle impide mover invariantes que dependan de globales.
- El ensamblador es simulado (no se ensambla ni se ejecuta); la asignación de
  registros es local y lineal, no por coloreado de grafos (Chaitin-Briggs).
- No hay ejecución de ambos caminos ni verificación formal de tipos.
