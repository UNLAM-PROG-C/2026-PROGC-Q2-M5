"""Google style with the course overrides: two spaces and short functions.

The shared inventory covers fdc/, tools/, tests/, main.py and deploy/server.py.
Only docstrings and decorators are excluded from function length. Player
facing UI strings may be Spanish; technical logging messages may not.
Quoted UI text and literal paths in English documentation are exempt.
"""
import ast
import importlib.util
import io
import os
import re
import sys
import tokenize
import unittest

import style_files

PROJECT = style_files.PROJECT
if PROJECT not in sys.path:
  sys.path.insert(0, PROJECT)  # Imported project names must resolve to modules.
FOLDERS = style_files.FOLDERS
MAX_FUNCTION_LINES = 15  # Functions must have fewer physical lines.
MAX_LINE_LENGTH = 80  # Maximum characters per physical line.
INDENT = 2  # Exact indentation increase per Python block.
# Standard exceptions for type annotations and compiler feature declarations.
NAME_IMPORT_OK = ("typing", "collections.abc", "__future__")
# Comments may cite localized UI labels, but logging messages may not.
QUOTED = re.compile(r'"[^"]*"|«[^»]*»')
# Paths, CLI flags and the game's proper title are citations, not prose.
REFERENCES = re.compile(
  r'`[^`]*`|<[^>]+>[/\\]\S*|\b[\w./\\-]+[/\\]\S*|--[\w-]+'
  r'|\b[\w-]+\.(?:txt|example|py|csv|json|png|exe|bat)\b'
  r'|Futbol De Cabeza')
# Pillow is optional tooling; these are real modules even when not installed.
OPTIONAL_MODULES = {"PIL.Image", "PIL.ImageDraw", "PIL.ImageFont"}
# A library's sine function is not the Spanish preposition with that spelling.
ENGLISH_API_NAMES = {"math.sin", "np.sin", "numpy.sin"}
SPANISH_CHARS = re.compile("[áéíóúñ¿¡]", re.IGNORECASE)
# Whole tokens avoid matching Spanish fragments inside English words.
SPANISH_VOCABULARY = (
  "que los las del para con una por cada cuando desde hasta esto esta este "
  "pero como sin sobre entre tambien porque donde hace jugador jugadores "
  "partido pelota pantalla sala salas cola colas hilo hilos proceso procesos "
  "arco tecla nombre clave estado listo pausa poder poderes cancha tiempo "
  "puerto torneo ganador ancho alto fila imagen archivo ruta mensaje servidor "
  "cliente prueba semilla duracion perfil botin cabeza registro trafico "
  "conexion mundialito personaje equipo tribuna tope mediciones vineta "
  "prediccion motivo efectos datos tabla subidos lamina disponible captura "
  "capturas modos modo calidad calidades noche iconos comparador mejoras "
  "generar icono sin_prediccion"
).split()
SPANISH_WORDS = re.compile(
  r"\b(" + "|".join(SPANISH_VOCABULARY) + r")\b", re.IGNORECASE)
# Underscores delimit identifier components, not English word substrings.
SPANISH_NAMES = re.compile(
  r"(^|_)(" + "|".join(SPANISH_VOCABULARY) + r")($|_)", re.IGNORECASE)
LOG_METHODS = {"debug", "info", "warning", "warn", "error", "exception",
               "critical", "fatal", "log"}
LOG_OWNERS = {"logging", "log", "logger"}


def _docstring_lines(node):
  """Physical lines occupied by the leading docstring, if present."""
  first = node.body[0]
  if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
      and isinstance(first.value.value, str)):
    return first.end_lineno - first.lineno + 1
  return 0


def long_functions(tree):
  """(line, name, length), counting the signature but not decorators."""
  found = []
  for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
      length = node.end_lineno - node.lineno + 1 - _docstring_lines(node)
      if length >= MAX_FUNCTION_LINES:
        found.append((node.lineno, node.name, length))
  return found


def long_lines(source):
  return [(n, len(line)) for n, line in enumerate(source.splitlines(), 1)
          if len(line) > MAX_LINE_LENGTH]


def bad_indentation(source):
  """Check INDENT increments, not absolute multiples or continuations."""
  bad, levels = [], [0]
  for token in tokenize.generate_tokens(io.StringIO(source).readline):
    if token.type == tokenize.INDENT:
      width = len(token.string.expandtabs())
      if width - levels[-1] != INDENT:
        bad.append((token.start[0], width - levels[-1]))
      levels.append(width)
    elif token.type == tokenize.DEDENT:
      levels.pop()
  return bad


def tab_lines(source):
  """Tabs are forbidden even in comments, strings and continuations."""
  return [line for line, text in enumerate(source.splitlines(), 1)
          if "\t" in text]


def _is_module(name):
  if name in OPTIONAL_MODULES:
    return True
  try:
    return importlib.util.find_spec(name) is not None
  except (ImportError, ValueError):
    return False


def _import_issues(node):
  if node.level:
    return [(node.lineno, "relative import")]
  if node.module in NAME_IMPORT_OK:
    return []
  return [(node.lineno, f"{node.module}.{alias.name}")
          for alias in node.names
          if not _is_module(f"{node.module}.{alias.name}")]


def bad_imports(tree):
  return [issue for node in ast.walk(tree)
          if isinstance(node, ast.ImportFrom) for issue in _import_issues(node)]


def _comments(source):
  tokens = tokenize.generate_tokens(io.StringIO(source).readline)
  return [(tok.start[0], tok.string) for tok in tokens
          if tok.type == tokenize.COMMENT]


def _docstrings(tree):
  nodes = [tree] + [n for n in ast.walk(tree) if isinstance(
    n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
  return [(getattr(n, "lineno", 1), ast.get_docstring(n)) for n in nodes
          if ast.get_docstring(n)]


def looks_spanish(text):
  return bool(SPANISH_CHARS.search(text) or SPANISH_WORDS.search(text))


def spanish_text(tree, source):
  """One finding per comment/docstring; quoted UI and paths are exempt."""
  found = []
  for line, text in _comments(source) + _docstrings(tree):
    prose = REFERENCES.sub("", QUOTED.sub("", text))
    if looks_spanish(prose):
      found.append((line, text.strip()))
  return found


def _string_identifiers(node):
  """Argument destinations and dynamic attributes are code, not UI labels."""
  if isinstance(node, ast.Dict):
    return [value for key, value in zip(node.keys, node.values)
            if isinstance(key, ast.Constant) and key.value == "dest"]
  if isinstance(node, ast.keyword) and node.arg == "dest":
    return [node.value]
  if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
      and node.func.id in {"getattr", "setattr", "hasattr"}):
    return node.args[1:2]
  return []


def _names(tree):
  for node in ast.walk(tree):
    yield from _node_names(node)
    for literal in _string_identifiers(node):
      if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
        yield literal.lineno, literal.value


def _node_names(node):
  if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
    yield node.lineno, node.name
  elif isinstance(node, ast.Name):
    yield node.lineno, node.id
  elif isinstance(node, ast.arg):
    yield node.lineno, node.arg
  elif isinstance(node, ast.Attribute):
    if ast.unparse(node) not in ENGLISH_API_NAMES:
      yield node.lineno, node.attr


def spanish_names(tree):
  """Check uses too: argparse destinations can originate in strings."""
  return sorted({(line, name) for line, name in _names(tree)
                 if SPANISH_NAMES.search(name)})


def spanish_filenames():
  return [os.path.relpath(path, PROJECT) for path in style_files.project_files()
          if SPANISH_NAMES.search(os.path.splitext(os.path.basename(path))[0])]


def _is_logging_call(node):
  if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
    return False
  owner = ast.unparse(node.func.value).split(".")[0]
  return node.func.attr in LOG_METHODS and owner in LOG_OWNERS


def spanish_logs(tree):
  """Inspect literal fragments, including f-strings and format arguments."""
  found = []
  for call in ast.walk(tree):
    if _is_logging_call(call):
      for node in ast.walk(call):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
          if looks_spanish(node.value):
            found.append((node.lineno, node.value))
  return sorted(set(found))


def _report(check):
  problems = []
  for rel, source in style_files.sources():
    for item in check(ast.parse(source), source):
      problems.append(f"{rel}:{item}")
  return problems


def assert_clean(case, problems, what):
  """Do not truncate: every finding must be actionable from the failure."""
  if problems:
    case.fail(f"{len(problems)} {what}:\n" + "\n".join(map(str, problems)))


class CodingStandardTest(unittest.TestCase):
  """One failure per rule with the complete list of current violations."""

  def test_functions_are_short(self):
    assert_clean(self, _report(lambda tree, src: long_functions(tree)),
                 "functions with 15 lines or more")

  def test_lines_fit_in_80_columns(self):
    assert_clean(self, _report(lambda tree, src: long_lines(src)),
                 "lines longer than 80 characters")

  def test_indentation_is_two_spaces(self):
    assert_clean(self, _report(lambda tree, src: bad_indentation(src)),
                 "blocks not indented by exactly 2 spaces")

  def test_no_tabs(self):
    assert_clean(self, _report(lambda tree, src: tab_lines(src)), "tab lines")

  def test_imports_are_absolute_modules(self):
    assert_clean(self, _report(lambda tree, src: bad_imports(tree)),
                 "relative imports or imported names")

  def test_comments_and_docstrings_in_english(self):
    assert_clean(self, _report(spanish_text), "Spanish comments/docstrings")

  def test_names_in_english(self):
    assert_clean(self, _report(lambda tree, src: spanish_names(tree)),
                 "Spanish identifiers")

  def test_filenames_in_english(self):
    assert_clean(self, spanish_filenames(), "Spanish filenames")

  def test_logging_in_english(self):
    assert_clean(self, _report(lambda tree, src: spanish_logs(tree)),
                 "Spanish technical logging strings")


if __name__ == "__main__":
  unittest.main()
