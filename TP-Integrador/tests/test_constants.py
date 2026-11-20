"""No unexplained numeric literals in functions or module/class code.

Named UPPER_CASE assignments are declarative constants, not magic numbers.
Only structural 0, 1, -1, 2 and 0.5 need no name. Tests use numeric fixtures
and are excluded from this rule, but not from the ordinary style checks.
"""
import ast
import io
import tokenize
import unittest

import style_files

ALLOWED = {0, 1, -1, 2, 0.5}  # Structural literals with self-evident meaning.
IGNORED_TOKENS = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                  tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER}


def _sources():
  return style_files.sources(include_tests=False)


def _is_number(node):
  return (isinstance(node, ast.Constant)
          and isinstance(node.value, (int, float))
          and not isinstance(node.value, bool))


def _target_names(target):
  if isinstance(target, ast.Name):
    return [target.id]
  if isinstance(target, (ast.Tuple, ast.List)):
    return [name for item in target.elts for name in _target_names(item)]
  return []


def _constant_names(node):
  targets = getattr(node, "targets", [getattr(node, "target", None)])
  names = [name for target in targets for name in _target_names(target)]
  return [name for name in names if name.isupper()]


def _constant_assignment(node):
  targets = getattr(node, "targets", [getattr(node, "target", None)])
  names = [name for target in targets for name in _target_names(target)]
  return bool(names) and all(name.isupper() for name in names)


class _NumberVisitor(ast.NodeVisitor):
  """Separate function literals from module/class initialization code."""

  def __init__(self, module_scope=False):
    self.depth = 0
    self.module_scope = module_scope
    self.found = []

  def _inside(self, node):
    self.depth += 1
    self.generic_visit(node)
    self.depth -= 1

  # AST dispatch requires these exact method names.
  visit_FunctionDef = visit_AsyncFunctionDef = visit_Lambda = _inside

  def visit_Assign(self, node):  # pylint: disable=invalid-name
    # Only declarations outside functions may contain arbitrary numeric data.
    if not self.module_scope or self.depth or not _constant_assignment(node):
      self.generic_visit(node)

  visit_AnnAssign = visit_Assign

  def _record(self, node, value):
    in_scope = (self.depth == 0) if self.module_scope else self.depth > 0
    if in_scope and value not in ALLOWED:
      self.found.append((node.lineno, value))

  def visit_Constant(self, node):  # pylint: disable=invalid-name
    if _is_number(node):
      self._record(node, node.value)

  def visit_UnaryOp(self, node):  # pylint: disable=invalid-name
    # The sign belongs to a literal: -2 is not the allowed structural +2.
    if isinstance(node.op, (ast.USub, ast.UAdd)) and _is_number(node.operand):
      sign = -1 if isinstance(node.op, ast.USub) else 1
      self._record(node, sign * node.operand.value)
    else:
      self.generic_visit(node)


def magic_numbers(tree, module_scope=False):
  visitor = _NumberVisitor(module_scope)
  visitor.visit(tree)
  return visitor.found


def _comment_lines(source):
  """Return all comment lines and comment-only lines."""
  comments, code = set(), set()
  for token in tokenize.generate_tokens(io.StringIO(source).readline):
    if token.type == tokenize.COMMENT:
      comments.add(token.start[0])
    elif token.type not in IGNORED_TOKENS:
      code.update(range(token.start[0], token.end[0] + 1))
  return comments, comments - code


def _needs_comment(node):
  names = _constant_names(node)
  value = getattr(node, "value", None)
  return bool(names) and value is not None and any(
    _is_number(child) for child in ast.walk(value))


def _commented(node, comments, comment_only):
  span = set(range(node.lineno, (node.end_lineno or node.lineno) + 1))
  return bool(span & comments) or node.lineno - 1 in comment_only


def _declarations(body):
  """Walk module/class blocks without entering functions or lambdas."""
  for node in body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
      continue
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
      yield node
    for _, value in ast.iter_fields(node):
      if isinstance(value, list):
        yield from _declarations([n for n in value if isinstance(n, ast.stmt)])


def undocumented_constants(tree, source):
  comments, comment_only = _comment_lines(source)
  return [(node.lineno, _constant_names(node)[0])
          for node in _declarations(tree.body) if _needs_comment(node)
          and not _commented(node, comments, comment_only)]


def number_problems(module_scope=False):
  return [f"{rel}:{line}  {value!r}" for rel, source in _sources()
          for line, value in magic_numbers(ast.parse(source), module_scope)]


def constant_problems():
  return [f"{rel}:{line}  {name}" for rel, source in _sources()
          for line, name in undocumented_constants(ast.parse(source), source)]


def _assert_clean(case, problems, label):
  # Complete output is intentional: this red suite is the remediation baseline.
  if problems:
    case.fail(f"{len(problems)} {label}:\n" + "\n".join(problems))


class NoMagicNumbersTest(unittest.TestCase):

  def test_no_magic_numbers_inside_functions(self):
    _assert_clean(self, number_problems(), "loose numbers inside functions")

  def test_no_magic_numbers_at_module_or_class_level(self):
    _assert_clean(self, number_problems(module_scope=True),
                  "loose numbers at module/class level")

  def test_every_constant_is_explained(self):
    _assert_clean(self, constant_problems(), "constants without a comment")


if __name__ == "__main__":
  unittest.main()
