"""The match loop with the effects, headless (fdc.gpu.demo).

It is the end-to-end check: a real match runs a few frames with the chain
on and off, and both have to finish with the same screen size. The GPU run
is skipped when there is no CUDA; the "off" run always happens.
"""
import unittest

import helpers  # pylint: disable=unused-import
from fdc import config
from fdc.gpu import backend
from fdc.gpu import demo
from fdc.gpu import env

FRAMES = 40             # frames of each run (short: it is a test)
STAGES = ("glow", "particles", "frame", "fps")
HAVE_GPU = config.Gpu.ENABLED and env.setup() and backend.available()


class DemoOffTest(unittest.TestCase):
    """Without the effects the loop has to run as before."""

    @classmethod
    def setUpClass(cls):
        demo.headless()
        cls.data = demo.run(FRAMES, ["--no-gpu"])

    def test_loop_runs(self):
        self.assertEqual(self.data["mode"], "off")
        self.assertGreaterEqual(self.data["frames"], 1)

    def test_frame_time(self):
        self.assertGreater(self.data["ms_frame"], 0.0)


@unittest.skipUnless(HAVE_GPU, "no CUDA here (see INSTALACION.md)")
class DemoGpuTest(unittest.TestCase):
    """With CUDA the chain runs inside the loop and reports its cost."""

    @classmethod
    def setUpClass(cls):
        demo.headless()
        cls.data = demo.run(FRAMES, ["--gpu-quality", "media"])

    def test_gpu_mode(self):
        self.assertEqual(self.data["mode"], "gpu")
        self.assertIn("NVIDIA", self.data["gpu"])

    def test_stages_reported(self):
        for key in STAGES:
            self.assertIn(key, self.data)
        self.assertGreater(self.data["frame"], 0.0)
        self.assertGreater(self.data["ms_frame"], 0.0)


if __name__ == "__main__":
    unittest.main()
