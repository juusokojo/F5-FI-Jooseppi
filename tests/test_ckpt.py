"""Which checkpoint load_model and the scripts pick when none is given."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import f5fi  # noqa: E402


class ResolveCkptTest(unittest.TestCase):
    def test_default_is_the_finetuned_model_when_present(self):
        with mock.patch("os.path.exists", return_value=True):
            self.assertEqual(f5fi.resolve_ckpt(), f5fi.FINETUNED_CKPT)

    def test_falls_back_to_base_with_a_note(self):
        with mock.patch("os.path.exists", return_value=False), mock.patch("sys.stderr") as err:
            self.assertEqual(f5fi.resolve_ckpt(None), f5fi.BASE_CKPT)
        self.assertTrue(err.write.called)

    def test_base_and_explicit_paths(self):
        self.assertEqual(f5fi.resolve_ckpt("base"), f5fi.BASE_CKPT)
        self.assertEqual(f5fi.resolve_ckpt("/x/malli.safetensors"), "/x/malli.safetensors")

    def test_finetuned_ckpt_is_under_checkpoints(self):
        self.assertTrue(f5fi.FINETUNED_CKPT.startswith(os.path.join(f5fi.ROOT, "checkpoints") + os.sep))


if __name__ == "__main__":
    unittest.main()
