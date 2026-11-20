"""Regression fixtures for the style detectors, independent of project debt."""
import ast
import os
import unittest

import cuda_style
import style_files
import test_constants
import test_style

# Continuations deliberately align at non-block columns.
PY_ALIGNED = 'def draw():\n  call(\n       1,\n       2)\n  return 0\n'
# A four-space block must fail even though four is a multiple of two.
PY_FOUR = 'def draw():\n    if True:\n        return 0\n'
# Existing nested indentation must be checked as a delta, not a column.
PY_MIXED = 'def draw():\n  if True:\n      return 0\n'
# Every numeric declaration form here is an explicitly named constant.
PY_CONSTANTS = 'A: int = 13\n_B = 17\nC, D = 19, 23\nclass Item:\n  E = 29\n'
# Module calls and class expressions are not constant declarations.
PY_LOOSE = 'build(13)\nclass Item:\n  value = 17\n  DEFAULT = 23\n'
# Structural float suffixes, exponents, hexadecimal values and named constants.
CU_NUMBERS = '''#define LIMIT 255.0f
constexpr float GAIN = 13.0f;
const unsigned int MASK = 0xffu;
const float TABLE[] = {17.0f, 19.0f};
__device__ float shade()
{
  return 0.5f + 1.0f + 2.0f + 1e0f + 255.0f + 0xffu + 1e-3f;
}
'''
# Braces and numbers in comments/strings are not executable CUDA.
CU_DATA = '''__device__ void fill()
{
  const char *text = "} 255 tribuna {";
  // English comment: {255}
  float table[] = {1, 2};
  consume(table);
}
'''
# The signature and expression continuations are not indentation levels.
CU_ALIGNED = '''__device__ float shade(float light,
                          float gain)
{
  if (light > 0)
    return light
           * gain;
  return 0;
}
'''
# A block opening on the control line violates Allman.
CU_INLINE = '__device__ void fill()\n{\n  if (true) {\n    return;\n  }\n}\n'


class PythonStyleRulesTest(unittest.TestCase):

  def test_block_delta_not_absolute_multiple(self):
    self.assertEqual(test_style.bad_indentation(PY_FOUR), [(2, 4), (3, 4)])
    self.assertEqual(test_style.bad_indentation(PY_MIXED), [(3, 4)])

  def test_continuations_are_not_blocks(self):
    self.assertEqual(test_style.bad_indentation(PY_ALIGNED), [])

  def test_tabs_anywhere_are_reported(self):
    self.assertEqual(test_style.tab_lines('#\tcomment\nx = "\t"\n'), [1, 2])

  def test_function_boundary_includes_signature(self):
    short = 'def run():\n' + '  pass\n' * 13
    long = short + '  pass\n'
    self.assertEqual(test_style.long_functions(ast.parse(short)), [])
    self.assertEqual(test_style.long_functions(ast.parse(long)),
                     [(1, 'run', 15)])

  def test_docstrings_and_decorators_are_excluded(self):
    source = '@wrapper\ndef run():\n  """One.\n  Two."""\n' + '  pass\n' * 13
    self.assertEqual(test_style.long_functions(ast.parse(source)), [])

  def test_spanish_identifiers_at_definitions_and_uses(self):
    source = ('MEDICIONES_DIR = 1\ndef tribuna(tope):\n'
              '  return args.sin_prediccion')
    names = {name for _, name in test_style.spanish_names(ast.parse(source))}
    self.assertEqual(names,
                     {'MEDICIONES_DIR', 'tribuna', 'tope', 'sin_prediccion'})

  def test_localized_ui_is_exempt_but_logging_is_not(self):
    source = 'label = "GPU no disponible"\nlogger.warning("GPU no disponible")'
    self.assertEqual(test_style.spanish_text(ast.parse(source), source), [])
    self.assertEqual(test_style.spanish_logs(ast.parse(source)),
                     [(2, 'GPU no disponible')])

  def test_english_words_quotes_and_paths_are_not_spanish(self):
    source = '# Show "Partido listo" from mediciones/run.csv in the shader.\n'
    self.assertEqual(test_style.spanish_text(ast.parse(source), source), [])
    self.assertFalse(test_style.SPANISH_NAMES.search('window_state_capstone'))

  def test_named_constants_exempt_at_module_and_class_scope(self):
    self.assertEqual(test_constants.magic_numbers(
      ast.parse(PY_CONSTANTS), module_scope=True), [])

  def test_module_and_class_calls_are_not_exempt(self):
    self.assertEqual(test_constants.magic_numbers(
      ast.parse(PY_LOOSE), module_scope=True), [(1, 13), (3, 17)])

  def test_function_constants_and_defaults_are_still_checked(self):
    source = 'def run(value=13):\n  LOCAL = 17\n  return -19\n'
    self.assertEqual(test_constants.magic_numbers(ast.parse(source)),
                     [(1, 13), (2, 17), (3, -19)])

  def test_source_inventory_matches_scope(self):
    paths = [os.path.relpath(path, style_files.PROJECT)
             for path in style_files.project_files()]
    self.assertEqual(paths[:2], ['main.py', 'server.py'])
    self.assertFalse(any(path.startswith(('web/', 'assets/', 'landing/'))
                         for path in paths))
    self.assertTrue(any(path.startswith('tests/') for path in paths))

  def test_math_api_is_english_but_local_preposition_is_not(self):
    source = 'value = math.sin(0) + np.sin(0)\nsin = 1\n'
    self.assertEqual(test_style.spanish_names(ast.parse(source)), [(2, 'sin')])

  def test_dynamic_names_and_argument_destinations(self):
    source = 'opts = {"dest": "sin_prediccion"}\ngetattr(opts, "tribuna")'
    self.assertEqual(test_style.spanish_names(ast.parse(source)),
                     [(1, 'sin_prediccion'), (2, 'tribuna')])

  def test_import_exceptions_are_modules_not_arbitrary_names(self):
    source = 'from PIL import Image\nfrom os import path\nfrom os import getcwd'
    self.assertEqual(test_style.bad_imports(ast.parse(source)),
                     [(3, 'os.getcwd')])
    self.assertEqual(test_style.bad_imports(ast.parse('from . import thing')),
                     [(1, 'relative import')])

  def test_prose_references_are_exempt(self):
    source = '# Futbol De Cabeza uses --calidad and servidor.txt.\n'
    self.assertEqual(test_style.spanish_text(ast.parse(source), source), [])
    self.assertTrue(test_style.looks_spanish('tribuna animada'))

  def test_lambda_in_a_constant_is_still_function_code(self):
    tree = ast.parse('ACTION = lambda: 13\n')
    self.assertEqual(test_constants.magic_numbers(tree), [(1, 13)])
    self.assertEqual(test_constants.magic_numbers(tree, module_scope=True), [])

  def test_signed_structural_values_are_distinct(self):
    source = 'def run():\n  return -1, -2, -0.5, 2, 0.5\n'
    self.assertEqual(test_constants.magic_numbers(ast.parse(source)),
                     [(2, -2), (2, -0.5)])

  def test_constant_comments_remain_required(self):
    source = '# Speed in pixels per second.\nSPEED = 13\nLIMIT = 17\n'
    self.assertEqual(test_constants.undocumented_constants(
      ast.parse(source), source), [(3, 'LIMIT')])


class CudaStyleRulesTest(unittest.TestCase):

  def test_numeric_suffixes_and_declarations(self):
    self.assertEqual([text for _, _, text in cuda_style.magic_numbers(
      CU_NUMBERS)], ['255.0f', '0xffu', '1e-3f'])

  def test_comments_strings_and_initializers_are_not_blocks(self):
    self.assertEqual(cuda_style.bad_braces(CU_DATA), [])
    self.assertEqual(cuda_style.magic_numbers(CU_DATA), [])
    self.assertEqual(cuda_style.bad_indentation(CU_DATA), [])

  def test_aligned_continuations_and_unbraced_control(self):
    self.assertEqual(cuda_style.bad_indentation(CU_ALIGNED), [])
    self.assertEqual(cuda_style.bad_braces(CU_ALIGNED), [])

  def test_four_space_cuda_blocks_fail(self):
    source = '__global__ void run()\n{\n    if (true)\n        return;\n}\n'
    self.assertEqual(cuda_style.bad_indentation(source),
                     [(3, 4, 2), (4, 8, 6)])

  def test_allman_reports_inline_openings_and_columns(self):
    self.assertEqual(cuda_style.bad_braces(CU_INLINE), [
      (3, 'opening brace must stand alone'), (5, 'brace column != 12')])

  def test_nested_braces_determine_function_end(self):
    source = ('__device__ void run()\n{\n  if (true)\n  {\n'
              + '    work();\n' * 9)
    self.assertEqual(cuda_style.long_functions(source + '  }\n}\n'),
                     [(1, 'run', 15)])

  def test_cuda_short_function_boundary(self):
    source = '__global__ void run()\n{\n' + '  work();\n' * 11 + '}\n'
    self.assertEqual(cuda_style.long_functions(source), [])

  def test_cuda_english_detectors_do_not_read_strings(self):
    source = '// tribuna animada\nfloat tope;\nchar *s = "tribuna";\n'
    self.assertEqual(cuda_style.spanish_names(source, test_style.SPANISH_NAMES),
                     [(2, 'tope')])
    self.assertEqual(cuda_style.spanish_comments(
      source, test_style.looks_spanish), [(1, '// tribuna animada')])

  def test_cuda_unary_signs_are_not_subtraction(self):
    source = 'return -1.0f + -2.0f + -0.5f + light - 2.0f;'
    self.assertEqual([text for _, _, text in cuda_style.magic_numbers(source)],
                     ['-2.0f', '-0.5f'])

  def test_preprocessor_is_not_statement_indentation(self):
    source = ('#define LIMIT \\\n    (13 + 17)\n'
              '__global__ void run()\n{\n  work();\n}\n')
    self.assertEqual(cuda_style.bad_indentation(source), [])

  def test_multiline_defines_and_constants_are_exempt(self):
    source = '#define LIMIT \\\n  (13 + 17)\nconst float GAIN =\n  19.0f;\n'
    self.assertEqual(cuda_style.magic_numbers(source), [])


if __name__ == '__main__':
  unittest.main()
