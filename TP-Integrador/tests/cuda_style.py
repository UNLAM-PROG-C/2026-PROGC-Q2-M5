"""Small lexical CUDA checks, not a C++ compiler or a semantic validator.

Comments/strings are masked without moving lines or columns. Initializer
braces are data, not Allman blocks. Parenthesized and expression continuations
are alignment, not block indentation. Numeric suffixes are parsed as literals,
so 1.0f is structural while 255.0f is reported. Only named uppercase constant
and macro declarations may contain arbitrary numeric values.
"""
import collections
import re

MAX_FUNCTION_LINES = 15  # Signature through closing brace, inclusive.
INDENT = 2  # Spaces per CUDA block or unbraced control statement.
ALLOWED = {0, 1, -1, 2, 0.5}  # Self-evident structural numeric values.
IGNORED = re.compile(
  r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
NUMBER = r'(?:0[xX][\da-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)'
TOKEN = re.compile(NUMBER + r'[fFuUlL]*|[A-Za-z_]\w*|[^\s]')
FUNCTION = re.compile(
  r'\b(?:__global__|__device__)\s+(?:[\w:*]+\s+)*?'
  r'(\w+)\s*\([^;{}]*\)\s*\{')
PREPROCESSOR = re.compile(r'^[ \t]*#(?:\\\n|[^\n])*', re.M)
MACRO = re.compile(
  r'^[ \t]*#\s*define\s+[A-Z_][A-Z_\d]*\b(?:\\\n|[^\n])*', re.M)
CONSTANT = re.compile(
  r'\b(?:constexpr|const)\s+(?:[\w:*]+\s+)*?'
  r'[A-Z_][A-Z_\d]*\s*(?:\[[^;]*?\])?\s*=\s*[^;]+;')
CONTROL = {"if", "for", "while", "switch"}
UNARY_AFTER = {"(", "[", "{", "=", ",", ";", "return", "?", ":",
               "+", "-", "*", "/", "<", ">", "!"}
Token = collections.namedtuple("Token", "text line column offset")


def _blank(match):
  return "".join("\n" if char == "\n" else " " for char in match.group())


def clean_source(source):
  return IGNORED.sub(_blank, source)


def tokens(source):
  clean = clean_source(source)
  result = []
  for match in TOKEN.finditer(clean):
    offset = match.start()
    line = clean.count("\n", 0, offset) + 1
    column = offset - clean.rfind("\n", 0, offset) - 1
    result.append(Token(match.group(), line, column, offset))
  return result


def brace_pairs(source):
  """(opening, closing, is_block), excluding data initializers recursively."""
  stack, pairs, previous = [], [], ""
  for token in tokens(source):
    if token.text == "{":
      block = previous != "=" and (not stack or stack[-1][1])
      stack.append((token, block))
    elif token.text == "}" and stack:
      opening, block = stack.pop()
      pairs.append((opening, token, block))
    previous = token.text
  return sorted(pairs, key=lambda pair: pair[0].offset)


def bad_braces(source):
  clean = clean_source(source).splitlines()
  found = []
  for opening, closing, block in brace_pairs(source):
    if block:
      if clean[opening.line - 1].strip() != "{":
        found.append((opening.line, "opening brace must stand alone"))
      if clean[closing.line - 1].strip() != "}":
        found.append((closing.line, "closing brace must stand alone"))
      if opening.column != closing.column:
        found.append((closing.line, f"brace column != {opening.column}"))
  return found


def long_functions(source):
  clean = clean_source(source)
  closes = {op.offset: cl for op, cl, block in brace_pairs(source) if block}
  found = []
  for match in FUNCTION.finditer(clean):
    start = clean.count("\n", 0, match.start()) + 1
    closing = closes[match.end() - 1]
    length = closing.line - start + 1
    if length >= MAX_FUNCTION_LINES:
      found.append((start, match.group(1), length))
  return found


def _control_end(items, start):
  depth = 0
  for index in range(start + 1, len(items)):
    text = items[index].text
    depth += (text == "(") - (text == ")")
    if text == ")" and depth == 0:
      return index
  return start


def _unbraced_indents(items, lines):
  expected = {}
  for index, token in enumerate(items[:-1]):
    end = _control_end(items, index) if token.text in CONTROL else index
    if token.text in CONTROL | {"else", "do"}:
      following = items[end + 1]
      if following.text != "{" and following.line != token.line:
        text = lines[token.line - 1]
        expected[following.line] = len(text) - len(text.lstrip()) + INDENT
  return expected


def _line_indent(line, text, depth, expected):
  wanted = expected.get(line, depth * INDENT)
  actual = len(text) - len(text.lstrip())
  return [] if actual == wanted else [(line, actual, wanted)]


def _indent_source(source):
  # Preprocessor bodies are declarations, not CUDA statement indentation.
  return PREPROCESSOR.sub(_blank, clean_source(source))


def bad_indentation(source):
  clean = _indent_source(source)
  lines, items = clean.splitlines(), tokens(clean)
  expected = _unbraced_indents(items, lines)
  states = _line_states(items)
  return [issue for line, (depth, continuation) in states.items()
          if not continuation and lines[line - 1].strip()
          for issue in _line_indent(line, lines[line - 1], depth, expected)]


def _advance_stack(stack, text, previous):
  if text == "{":
    stack.append(previous != "=" and (not stack or stack[-1]))
  elif text == "}" and stack:
    stack.pop()


def _line_states(items):
  """State at line start, excluding data and expression continuations."""
  states, stack, parens, previous = {}, [], 0, ";"
  for token in items:
    text = token.text
    closing_block = text == "}" and bool(stack) and stack[-1]
    depth = sum(stack) - closing_block
    continuation = parens > 0 or (bool(stack) and not stack[-1])
    continuation |= previous not in {";", "{", "}", ")"} and text != "{"
    states.setdefault(token.line, (depth, continuation))
    _advance_stack(stack, text, previous)
    parens += (text in {"(", "["}) - (text in {")", "]"})
    previous = text
  return states


def _literal_value(text):
  if text.lower().startswith("0x"):
    return int(re.sub(r'[uUlL]+$', '', text), 16)
  return float(re.sub(r'[fFuUlL]+$', '', text))


def _signed_number(items, index):
  token = items[index]
  if index > 0 and items[index - 1].text == "-":
    if index == 1 or items[index - 2].text in UNARY_AFTER:
      return items[index - 1]._replace(text="-" + token.text)
  return token


def _numbers(source):
  items = tokens(source)
  for index, token in enumerate(items):
    if re.fullmatch(NUMBER + r'[fFuUlL]*', token.text):
      signed = _signed_number(items, index)
      value = _literal_value(token.text) * (-1 if signed != token else 1)
      yield signed, value


def magic_numbers(source):
  clean = clean_source(source)
  exempt = [(match.start(), match.end()) for pattern in (MACRO, CONSTANT)
            for match in pattern.finditer(clean)]
  return [(token.line, token.column + 1, token.text)
          for token, value in _numbers(source) if value not in ALLOWED
          and not any(start <= token.offset < end for start, end in exempt)]


def spanish_comments(source, detector):
  return [(source.count("\n", 0, match.start()) + 1, match.group().strip())
          for match in IGNORED.finditer(source)
          if match.group().startswith(("//", "/*")) and detector(match.group())]


def spanish_names(source, pattern):
  return [(token.line, token.text) for token in tokens(source)
          if re.fullmatch(r'[A-Za-z_]\w*', token.text)
          and pattern.search(token.text)]
