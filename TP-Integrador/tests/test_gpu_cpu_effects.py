"""FDC_GPU only decides about CUDA: without it the effects run on the CPU.

The Mac, the notebooks of the demo and the "Windows CPU" exe have no CUDA,
and there FULL has to show the effects with the numpy backend (slower but
complete); OPTIMIZADO is the light version. `FDC_GPU=0` must not turn the
chain off: the "no effects" mode is explicit (`FDC_EFECTOS=0` or
"--sin-efectos").

Every case runs in a fresh interpreter (tests/check_effects_env.py), so the
variables are read the way the game reads them at start up.
"""
import json
import os
import subprocess
import sys
import unittest

import helpers  # pylint: disable=unused-import
from fdc import config
from fdc.gpu import demo

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = os.path.join(PROJECT, "tests", "check_effects_env.py")
HIDDEN = ("FDC_GPU", "FDC_EFECTOS", "FDC_TEST_NO_PYCUDA",
          "FDC_TEST_QUALITY", "FDC_GPU_QUALITY")
TIMEOUT = 180           # s for the fresh interpreter
NO_PYCUDA = "1"         # hides PyCUDA, like a machine without NVIDIA


def probe(**wanted):
    """Runs the helper in a fresh interpreter and returns its report."""
    env = {key: value for key, value in os.environ.items()
           if key not in HIDDEN}
    env.update(extra_env(wanted))
    out = subprocess.run([sys.executable, CHECK], cwd=PROJECT, env=env,
                         capture_output=True, text=True, timeout=TIMEOUT)
    return json.loads(out.stdout.strip().splitlines()[-1])


def extra_env(wanted):
    """Environment of the child: strings, as the shell would pass them."""
    return {key: str(value) for key, value in wanted.items()}


class FdcGpuMeansCudaTest(unittest.TestCase):
    """FDC_GPU=0 is "no CUDA", never "no effects"."""

    @classmethod
    def setUpClass(cls):
        cls.full = probe(FDC_GPU=0)
        cls.optimized = probe(FDC_GPU=0, FDC_TEST_QUALITY="optimizado")

    def test_full_keeps_the_effects(self):
        self.assertTrue(self.full["wanted"])
        self.assertEqual(self.full["quality_mode"], "FULL")

    def test_full_runs_on_the_cpu(self):
        self.assertEqual(self.full["backend"], "Cpu")
        self.assertEqual(self.full["mode"], "cpu")
        self.assertEqual(self.full["device"], "CPU")
        self.assertFalse(self.full["cuda_allowed"])

    def test_full_keeps_the_richest_stage(self):
        self.assertEqual(self.full["stage"], "alta")

    def test_optimized_keeps_the_effects(self):
        self.assertTrue(self.optimized["wanted"])
        self.assertEqual(self.optimized["stage"], "baja")

    def test_pycuda_is_never_imported(self):
        self.assertFalse(self.full["pycuda_loaded"])
        self.assertFalse(self.optimized["pycuda_loaded"])

    def test_no_error_reported(self):
        self.assertIsNone(self.full["error"])


class WithoutPycudaTest(unittest.TestCase):
    """A machine without PyCUDA falls back to the CPU by itself."""

    @classmethod
    def setUpClass(cls):
        cls.cuda_off = probe(FDC_GPU=0, FDC_TEST_NO_PYCUDA=NO_PYCUDA)
        cls.cuda_on = probe(FDC_GPU=1, FDC_TEST_NO_PYCUDA=NO_PYCUDA)

    def test_missing_pycuda_is_not_an_error(self):
        self.assertIsNone(self.cuda_on["error"])
        self.assertTrue(self.cuda_on["wanted"])

    def test_missing_pycuda_uses_the_cpu(self):
        self.assertEqual(self.cuda_on["backend"], "Cpu")
        self.assertEqual(self.cuda_on["mode"], "cpu")

    def test_fdc_gpu_0_without_pycuda_keeps_the_effects(self):
        self.assertTrue(self.cuda_off["wanted"])
        self.assertEqual(self.cuda_off["backend"], "Cpu")


class EffectsOffTest(unittest.TestCase):
    """The explicit "no effects" switch: FDC_EFECTOS=0."""

    def test_fdc_efectos_0_turns_the_chain_off(self):
        data = probe(FDC_EFECTOS=0)
        self.assertFalse(data["effects_enabled"])
        self.assertFalse(data["wanted"])
        self.assertIsNone(data["backend"])

    def test_sin_efectos_is_the_same_switch(self):
        self.assertTrue(helpers.main_options(["--sin-efectos"]).no_gpu)


class NoCudaDemoTest(unittest.TestCase):
    """The demo measures one backend when there is no CUDA for it."""

    def test_one_pass_without_cuda(self):
        saved = config.Gpu.ENABLED
        config.Gpu.ENABLED = False
        try:
            options = helpers.main_options(["--demo"])
            self.assertEqual(demo._passes(options), ["cpu"])
        finally:
            config.Gpu.ENABLED = saved


if __name__ == "__main__":
    unittest.main()
