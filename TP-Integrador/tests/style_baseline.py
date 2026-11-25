"""Print machine-readable style debt, including every untruncated finding.

Run from the repository: python3 -B tests/style_baseline.py > baseline.json
The collector uses the real test methods, so zero-count rules stay visible.
"""
import json
import sys
import unittest

import test_constants
import test_style
import test_style_cuda


def _failure(cls, name):
  case = cls(name)
  try:
    getattr(case, name)()
  except AssertionError as error:
    return str(error).splitlines()
  return []


def collect():
  reports = {}
  classes = (test_style.CodingStandardTest, test_constants.NoMagicNumbersTest,
             test_style_cuda.CudaStyleTest)
  for cls in classes:
    for name in unittest.defaultTestLoader.getTestCaseNames(cls):
      lines = _failure(cls, name)
      reports[f"{cls.__name__}.{name}"] = {
        "count": int(lines[0].split()[0]) if lines else 0,
        "problems": lines[1:]}
  return reports


def main():
  reports = collect()
  for report in reports.values():
    assert report["count"] == len(report["problems"]), "Truncated findings"
  if "--summary" in sys.argv:
    for name, report in reports.items():
      print(f"{name}: {report['count']}")
  else:
    print(json.dumps(reports, indent=2, ensure_ascii=False))


if __name__ == "__main__":
  main()
