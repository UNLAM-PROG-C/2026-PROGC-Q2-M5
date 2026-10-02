"""Regla del proyecto: sin "números mágicos".

1. Dentro de funciones y métodos sólo pueden aparecer los números que no
   necesitan explicación: 0, 1, -1, 2 y 0.5 (nada, uno, el signo, el doble
   y la mitad). Cualquier otro número es una CONSTANTE con nombre.
2. Las constantes se escriben en MAYÚSCULAS, a nivel de módulo o de clase:
   los valores del juego en fdc/config.py, las medidas comunes de la
   interfaz en fdc/ui/layout.py y las propias de cada pantalla o dibujo al
   principio de su módulo o de su clase.
3. Toda constante con números tiene un comentario que dice qué representa
   (en la misma línea, dentro de su definición o en la línea de arriba).

Esta prueba recorre el código fuente (fdc/, tools/, web/ y los .py de la
raíz) y lo verifica.
"""
import ast
import io
import os
import tokenize
import unittest

import helpers  # noqa: F401

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDERS = ("fdc", "tools", "web")      # el juego, las herramientas y el cliente web (más los .py de la raíz)
ALLOWED = {0, 1, -1, 2, 0.5}


def _files():
    for name in sorted(os.listdir(PROJECT)):
        if name.endswith(".py"):
            yield os.path.join(PROJECT, name)
    for folder in FOLDERS:
        for base, _, files in os.walk(os.path.join(PROJECT, folder)):
            for name in sorted(files):
                if name.endswith(".py"):
                    yield os.path.join(base, name)


def _sources():
    for path in _files():
        with open(path, encoding="utf-8") as fh:
            yield os.path.relpath(path, PROJECT), fh.read()


def _is_number(node):
    return (isinstance(node, ast.Constant) and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool))


def magic_numbers(tree):
    """(línea, valor) de cada número no permitido dentro de una función."""
    found = []

    class Visitor(ast.NodeVisitor):
        depth = 0

        def _inside(self, node):
            self.depth += 1
            self.generic_visit(node)
            self.depth -= 1

        visit_FunctionDef = visit_AsyncFunctionDef = visit_Lambda = _inside

        def visit_Constant(self, node):
            if self.depth and _is_number(node) and node.value not in ALLOWED:
                found.append((node.lineno, node.value))

    Visitor().visit(tree)
    return found


IGNORED_TOKENS = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
                  tokenize.ENDMARKER}


def _comment_lines(source):
    """(líneas con comentario, líneas que son SÓLO comentario)."""
    comments, code = set(), set()
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            comments.add(tok.start[0])
        elif tok.type not in IGNORED_TOKENS:
            code.update(range(tok.start[0], tok.end[0] + 1))
    return comments, comments - code


def undocumented_constants(tree, source):
    """Constantes en MAYÚSCULAS con números pero sin un comentario que las explique."""
    comments, comment_only = _comment_lines(source)
    missing = []

    def check(body):
        for node in body:
            targets = []
            if isinstance(node, ast.Assign):
                targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                targets = [node.target.id]
            names = [t for t in targets if t.isupper() and not t.startswith("_")]
            if not names or node.value is None:
                continue
            if not any(_is_number(n) for n in ast.walk(node.value)):
                continue
            # comentario propio: en la misma línea (o dentro de la definición) o en
            # la línea de arriba si ésa es sólo un comentario
            span = set(range(node.lineno, (node.end_lineno or node.lineno) + 1))
            if not (span & comments or node.lineno - 1 in comment_only):
                missing.append((node.lineno, names[0]))
            if isinstance(node, ast.ClassDef):
                check(node.body)
        for node in body:
            if isinstance(node, ast.ClassDef):
                check(node.body)

    check(tree.body)
    return missing


class NoMagicNumbersTest(unittest.TestCase):
    def test_no_magic_numbers_inside_functions(self):
        problems = []
        for rel, source in _sources():
            for line, value in magic_numbers(ast.parse(source)):
                problems.append(f"{rel}:{line}  {value!r}")
        self.assertEqual(problems, [], f"{len(problems)} números sueltos dentro de funciones "
                                       "(tienen que ser constantes con nombre):\n" + "\n".join(problems[:60]))

    def test_every_constant_is_explained(self):
        problems = []
        for rel, source in _sources():
            for line, name in undocumented_constants(ast.parse(source), source):
                problems.append(f"{rel}:{line}  {name}")
        self.assertEqual(problems, [], f"{len(problems)} constantes sin comentario:\n" + "\n".join(problems[:60]))


if __name__ == "__main__":
    unittest.main()
