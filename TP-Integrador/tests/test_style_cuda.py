"""Course rules for CUDA source; no driver, compiler or GPU is required."""
import os
import unittest

import cuda_style
import style_files
import test_style

KERNELS = os.path.join(style_files.PROJECT, "fdc", "gpu", "kernels.cu")


def kernel_source():
  with open(KERNELS, encoding="utf-8") as stream:
    return stream.read()


def rule_problems(check):
  return [f"fdc/gpu/kernels.cu:{item}" for item in check(kernel_source())]


class CudaStyleTest(unittest.TestCase):

  def check_rule(self, check, label):
    test_style.assert_clean(self, rule_problems(check), label)

  def test_allman_braces(self):
    self.check_rule(cuda_style.bad_braces, "CUDA Allman brace problems")

  def test_two_space_indentation(self):
    self.check_rule(cuda_style.bad_indentation, "CUDA indentation problems")

  def test_no_tabs(self):
    self.check_rule(test_style.tab_lines, "CUDA tab lines")

  def test_functions_are_short(self):
    self.check_rule(cuda_style.long_functions, "CUDA functions >=15 lines")

  def test_no_magic_numbers(self):
    self.check_rule(cuda_style.magic_numbers, "CUDA magic numeric literals")

  def test_comments_in_english(self):
    self.check_rule(lambda src: cuda_style.spanish_comments(
      src, test_style.looks_spanish), "CUDA Spanish comments")

  def test_names_in_english(self):
    self.check_rule(lambda src: cuda_style.spanish_names(
      src, test_style.SPANISH_NAMES), "CUDA Spanish identifiers")


if __name__ == "__main__":
  unittest.main()
