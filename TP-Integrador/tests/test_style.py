"""Coding standard of the project (Google Python Style Guide + course rules).

Checks every Python file of the project (fdc/, tools/, web/, tests/ and the
root scripts):
  1. functions and methods have fewer than 15 lines (the docstring is not
     counted, the signature is);
  2. lines have at most 80 characters;
  3. indentation uses 4 spaces, never tabs;
  4. imports are absolute and import modules, not classes or functions
     (typing and collections.abc are allowed, as the guide says);
  5. comments, docstrings and names are written in English (the texts the
     player sees are in Spanish, so string literals are not checked, and
     comments may quote them between double quotes).
"""
import ast
import importlib.util
import io
import os
import re
import sys
import tokenize
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)     # to check that imported names are modules
FOLDERS = ("fdc", "tools", "web", "tests")
MAX_FUNCTION_LINES = 15     # a function must have FEWER lines than this
MAX_LINE_LENGTH = 80        # characters per line
INDENT = 4                  # spaces per indentation level
# Modules whose names may be imported directly (the guide allows it).
NAME_IMPORT_OK = ("typing", "collections.abc", "__future__")
# Quoted texts are what the player sees (in Spanish): they may be cited.
QUOTED = re.compile(r'"[^"]*"|«[^»]*»')
# Letters and words that only appear in Spanish text.
SPANISH_CHARS = re.compile("[áéíóúñ¿¡]", re.IGNORECASE)
SPANISH_WORDS = re.compile(
    r"\b(que|los|las|del|para|con|una|por|cada|cuando|desde|hasta|esto|"
    r"esta|este|pero|como|sin|sobre|entre|tambien|porque|donde|hace|"
    r"jugador|partido|pelota|pantalla|sala|salas|cola|colas|hilo|hilos|"
    r"proceso|procesos|arco|tecla|nombre|clave|estado|listo|pausa)\b",
    re.IGNORECASE)
SPANISH_NAMES = re.compile(
    r"(^|_)(sala|salas|jugador|jugadores|partido|pelota|arco|nombre|clave|"
    r"proceso|hilo|cola|pantalla|tecla|poder|poderes|cancha|tiempo|puerto|"
    r"estado|listo|pausa|torneo|ganador|ancho|alto|fila|imagen|archivo|"
    r"ruta|mensaje|servidor|cliente|prueba|semilla|duracion|perfil|botin|"
    r"cabeza|registro|trafico|conexion|mundialito|personaje|equipo)"
    r"($|_)", re.IGNORECASE)


def project_files():
    """Paths of every Python file checked by the rules."""
    for name in sorted(os.listdir(PROJECT)):
        if name.endswith(".py"):
            yield os.path.join(PROJECT, name)
    for folder in FOLDERS:
        for base, _, files in os.walk(os.path.join(PROJECT, folder)):
            for name in sorted(files):
                if name.endswith(".py"):
                    yield os.path.join(base, name)


def _docstring_lines(node):
    """Number of lines of the function's docstring (0 if it has none)."""
    first = node.body[0]
    if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)):
        return first.end_lineno - first.lineno + 1
    return 0


def long_functions(tree):
    """(line, name, length) of every function with too many lines."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.decorator_list[0].lineno if node.decorator_list \
                else node.lineno
            length = node.end_lineno - start + 1 - _docstring_lines(node)
            if length >= MAX_FUNCTION_LINES:
                found.append((node.lineno, node.name, length))
    return found


def long_lines(source):
    """(line, length) of every line longer than the limit."""
    return [(n, len(line)) for n, line in enumerate(source.splitlines(), 1)
            if len(line) > MAX_LINE_LENGTH]


def bad_indentation(source):
    """Lines that open a block with an indentation that is not 4 spaces."""
    bad = []
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    for tok in tokens:
        if tok.type == tokenize.INDENT:
            text = tok.string
            if "\t" in text or len(text) % INDENT:
                bad.append(tok.start[0])
    return bad


def _is_module(name):
    """True if `name` is an importable module or package."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def bad_imports(tree):
    """(line, text) of relative imports and imports of names."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            found.append((node.lineno, "relative import"))
            continue
        if node.module in NAME_IMPORT_OK:
            continue
        for alias in node.names:
            if not _is_module(f"{node.module}.{alias.name}"):
                found.append((node.lineno, f"{node.module}.{alias.name}"))
    return found


def _comments(source):
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    return [(tok.start[0], tok.string) for tok in tokens
            if tok.type == tokenize.COMMENT]


def _docstrings(tree):
    nodes = [tree] + [n for n in ast.walk(tree) if isinstance(
        n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    return [(getattr(n, "lineno", 1), ast.get_docstring(n)) for n in nodes
            if ast.get_docstring(n)]


def spanish_text(tree, source):
    """(line, text) of comments and docstrings that look Spanish."""
    found = []
    for line, text in _comments(source) + _docstrings(tree):
        text = QUOTED.sub("", text)
        if SPANISH_CHARS.search(text) or SPANISH_WORDS.search(text):
            found.append((line, text.strip()[:60]))
    return found


def _names(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            yield node.lineno, node.name
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            yield node.lineno, node.id
        elif isinstance(node, ast.arg):
            yield node.lineno, node.arg
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx,
                                                             ast.Store):
            yield node.lineno, node.attr


def spanish_names(tree):
    """(line, name) of identifiers made of Spanish words."""
    return [(line, name) for line, name in _names(tree)
            if SPANISH_NAMES.search(name)]


def _report(check):
    """Runs `check(rel_path, tree, source)` on every file and joins issues."""
    problems = []
    for path in project_files():
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        rel = os.path.relpath(path, PROJECT)
        for item in check(ast.parse(source), source):
            problems.append(f"{rel}:{item}")
    return problems


class CodingStandardTest(unittest.TestCase):
    """Each rule of the coding standard, checked on the whole project."""

    def _assert_clean(self, problems, what):
        listing = "\n".join(problems[:60])
        self.assertEqual(problems, [], f"{len(problems)} {what}:\n{listing}")

    def test_functions_are_short(self):
        problems = _report(lambda tree, src: long_functions(tree))
        self._assert_clean(problems, "functions with 15 lines or more")

    def test_lines_fit_in_80_columns(self):
        problems = _report(lambda tree, src: long_lines(src))
        self._assert_clean(problems, "lines longer than 80 characters")

    def test_indentation_is_four_spaces(self):
        problems = _report(lambda tree, src: bad_indentation(src))
        self._assert_clean(problems, "blocks not indented with 4 spaces")

    def test_imports_are_absolute_modules(self):
        problems = _report(lambda tree, src: bad_imports(tree))
        self._assert_clean(problems, "relative imports or imported names")

    def test_comments_and_docstrings_in_english(self):
        problems = _report(spanish_text)
        self._assert_clean(problems, "comments or docstrings in Spanish")

    def test_names_in_english(self):
        problems = _report(lambda tree, src: spanish_names(tree))
        self._assert_clean(problems, "identifiers in Spanish")


if __name__ == "__main__":
    unittest.main()
