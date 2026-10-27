"""Project rule: no "magic numbers".

1. Inside functions and methods only the numbers that need no explanation
   may appear: 0, 1, -1, 2 and 0.5 (nothing, one, the sign, double and
   half). Any other number is a named CONSTANT.
2. Constants are written in UPPER CASE, at module or class level: the game
   values in fdc/config.py, the common interface measures in
   fdc/ui/layout.py and the ones of each screen or drawing at the top of
   its module or class.
3. Every constant with numbers has a comment that says what it means (on
   the same line, inside its definition or on the line above).

This test walks the source code (fdc/, tools/, web/ and the .py files of
the root) and checks it.
"""
import ast
import io
import os
import tokenize
import unittest

# Adds the project root to the path.
import helpers  # pylint: disable=unused-import

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The game, the tools and the web client (plus the .py files of the root).
FOLDERS = ("fdc", "tools", "web")
ALLOWED = {0, 1, -1, 2, 0.5}   # numbers that need no name
MAX_SHOWN = 60                  # problems listed in a failure message


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
    return (isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool))


class _NumberVisitor(ast.NodeVisitor):
    """Collects the numbers not allowed inside functions and lambdas."""

    def __init__(self):
        self.depth = 0
        self.found = []

    def _inside(self, node):
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1

    # pylint: disable-next=invalid-name
    visit_FunctionDef = visit_AsyncFunctionDef = visit_Lambda = _inside

    def visit_Constant(self, node):  # pylint: disable=invalid-name
        if self.depth and _is_number(node) and node.value not in ALLOWED:
            self.found.append((node.lineno, node.value))


def magic_numbers(tree):
    """(line, value) of each number not allowed inside a function."""
    visitor = _NumberVisitor()
    visitor.visit(tree)
    return visitor.found


IGNORED_TOKENS = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                  tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER}


def _comment_lines(source):
    """(lines with a comment, lines that are ONLY a comment)."""
    comments, code = set(), set()
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            comments.add(tok.start[0])
        elif tok.type not in IGNORED_TOKENS:
            code.update(range(tok.start[0], tok.end[0] + 1))
    return comments, comments - code


def _constant_names(node):
    """UPPER CASE names assigned by a statement (if any)."""
    targets = []
    if isinstance(node, ast.Assign):
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        targets = [node.target.id]
    return [t for t in targets if t.isupper() and not t.startswith("_")]


def _needs_comment(node):
    names = _constant_names(node)
    value = getattr(node, "value", None)
    return bool(names) and value is not None and any(
        _is_number(n) for n in ast.walk(value))


def _commented(node, comments, comment_only):
    """Own comment: on the same line (or inside the definition) or on the
    line above if that one is only a comment."""
    span = set(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return bool(span & comments) or node.lineno - 1 in comment_only


def undocumented_constants(tree, source):
    """UPPER CASE constants with numbers but no comment that explains
    them (at module level and inside classes)."""
    comments, comment_only = _comment_lines(source)
    missing = []
    bodies = [tree.body]
    while bodies:
        for node in bodies.pop():
            if isinstance(node, ast.ClassDef):
                bodies.append(node.body)
            elif (_needs_comment(node)
                  and not _commented(node, comments, comment_only)):
                missing.append((node.lineno, _constant_names(node)[0]))
    return missing


class NoMagicNumbersTest(unittest.TestCase):
    def test_no_magic_numbers_inside_functions(self):
        problems = [f"{rel}:{line}  {value!r}" for rel, source in _sources()
                    for line, value in magic_numbers(ast.parse(source))]
        self.assertEqual(problems, [], f"{len(problems)} loose numbers inside "
                         "functions (they must be named constants):\n"
                         + "\n".join(problems[:MAX_SHOWN]))

    def test_every_constant_is_explained(self):
        problems = [f"{rel}:{line}  {name}" for rel, source in _sources()
                    for line, name in undocumented_constants(
                        ast.parse(source), source)]
        self.assertEqual(problems, [], f"{len(problems)} constants without "
                         "a comment:\n" + "\n".join(problems[:MAX_SHOWN]))


if __name__ == "__main__":
    unittest.main()
