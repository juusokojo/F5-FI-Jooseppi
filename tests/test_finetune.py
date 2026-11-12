"""Tests for scripts/finetune.py with a tiny model on the CPU: the real training loop, files and continuation, but
no base model and no memory to speak of.

    .venv/bin/python -m unittest discover tests
"""
import csv
import os
import random
import sys
import tempfile
import unittest

import numpy as np
import soundfile as sf
import torch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import finetune as ft  # noqa: E402
from f5_tts.model import CFM, DiT  # noqa: E402

VOCAB = {c: i for i, c in enumerate(" abcdefghijklmnopqrstuvwxyzäö.,?")}


def tiny_model(seed=0):
    torch.manual_seed(seed)
    model = CFM(transformer=DiT(dim=64, depth=3, heads=2, dim_head=32, ff_mult=2, text_dim=32, conv_layers=1,
                                text_num_embeds=len(VOCAB), mel_dim=100), vocab_char_map=VOCAB)
    with torch.no_grad():  # DiT starts with zero output layers, which would hide most gradients
        for p in model.parameters():
            p.add_(0.05 * torch.randn_like(p))
    return model


def make_clips(n=12, seed=0):
    rng = np.random.default_rng(seed)
    clips = []
    for i in range(n):
        frames = int(rng.integers(40, 140))
        clips.append(ft.Clip(f"lause_{i:02d}", list("hei maailma, tämä on koe."), torch.randn(frames, 100)))
    return clips


def config(**kw):
    base = dict(steps=6, warmup=2, batch_frames=300, save_every=3, val_every=2, log_every=1, ema_every=1,
                grad_checkpoint=True)
    return ft.Config(**{**base, **kw})


class DataTest(unittest.TestCase):
    def test_val_split_is_by_name_only(self):
        names = [f"lukeminen_1_{i:03d}.wav" for i in range(2000)]
        val = [n for n in names if ft.is_val(n)]
        self.assertTrue(60 < len(val) < 140, len(val))  # about one in twenty
        self.assertEqual(ft.is_val("/a/b/lauseet1_07.wav"), ft.is_val("lauseet1_07.wav"))
        self.assertEqual([ft.is_val(n) for n in names[:50]], [ft.is_val(n) for n in names[:50]])

    def test_batches_cover_all_within_budget(self):
        rng = random.Random(3)
        lengths = [rng.randint(60, 900) for _ in range(200)] + [2000]
        batches = ft.make_batches(lengths, 1600, 8, random.Random(1))
        self.assertEqual(sorted(i for b in batches for i in b), list(range(len(lengths))))
        for b in batches:
            self.assertLessEqual(len(b), 8)
            if len(b) > 1:
                self.assertLessEqual(ft.batch_cost(b, lengths), 1600)
        self.assertIn([200], batches)  # the clip longer than the budget is alone
        self.assertNotEqual(batches, ft.make_batches(lengths, 1600, 8, random.Random(2)))

    def test_heaviest_first(self):
        lengths = [100, 100, 100, 100, 900, 50, 50]
        batches = [[5, 6], [4], [0, 1, 2, 3]]
        first = ft.heaviest_first(batches, lengths)
        self.assertEqual(first[0], [4])  # most padded frames and the longest clip
        self.assertEqual(sorted(map(tuple, first)), sorted(map(tuple, batches)))
        lengths[4] = 350
        self.assertEqual(ft.heaviest_first(batches, lengths)[:2], [[0, 1, 2, 3], [4]])

    def test_load_clips_filters(self):
        d = tempfile.mkdtemp()
        rows = []
        for name, seconds, sr in [("ok", 1.0, 24000), ("lyhyt", 0.1, 24000), ("pitka", 3.0, 24000), ("taajuus", 1.0, 16000)]:
            path = os.path.join(d, name + ".wav")
            sf.write(path, np.zeros(int(seconds * sr), np.float32), sr)
            rows.append((path, "teksti"))
        rows += [(os.path.join(d, "puuttuu.wav"), "teksti"), (rows[0][0], " ")]
        clips, skipped = ft.load_clips(rows, lambda w: torch.zeros(len(w) // 256, 100), list, 2.0, log=lambda *_: None)
        self.assertEqual([c.name for c in clips], ["ok"])
        self.assertEqual(clips[0].text, list("teksti"))
        self.assertEqual(clips[0].frames, 24000 // 256)
        self.assertEqual([n for n, _ in skipped], ["lyhyt", "pitka", "taajuus", "puuttuu", "ok"])

    def test_read_metadata(self):
        path = os.path.join(tempfile.mkdtemp(), "metadata.csv")
        with open(path, "w", encoding="utf-8") as f:
            f.write("audio_file|text\n/a/b.wav|hän sanoi \"joo\", eikö?\n")
        self.assertEqual(ft.read_metadata(path), [("/a/b.wav", 'hän sanoi "joo", eikö?')])

    def test_lr(self):
        cfg = ft.Config(lr=1e-5, warmup=100)
        self.assertAlmostEqual(ft.lr_at(1, cfg), 1e-7)
        self.assertAlmostEqual(ft.lr_at(50, cfg), 5e-6)
        self.assertAlmostEqual(ft.lr_at(100, cfg), 1e-5)
        self.assertAlmostEqual(ft.lr_at(5000, cfg), 1e-5)


class EmaTest(unittest.TestCase):
    def test_follows_the_model(self):
        model = torch.nn.Linear(4, 4)
        ema = ft.Ema(model, beta=0.9, every=1)
        with torch.no_grad():
            model.weight.fill_(1.0)
        before = ema.shadow["weight"].clone()
        for step in range(1, 200):
            ema.update(model, step)
        self.assertFalse(torch.allclose(before, ema.shadow["weight"]))
        self.assertTrue(torch.allclose(ema.shadow["weight"], model.weight, atol=1e-4))

    def test_only_every_nth_step(self):
        model = torch.nn.Linear(2, 2)
        ema = ft.Ema(model, every=10)
        with torch.no_grad():
            model.weight.add_(1.0)
        for step in range(1, 10):
            ema.update(model, step)
        self.assertEqual(ema.updates, 0)
        ema.update(model, 10)
        self.assertEqual(ema.updates, 1)

    def test_swap_twice_restores(self):
        model = torch.nn.Linear(3, 3)
        ema = ft.Ema(model)
        average = {k: v.clone() for k, v in ema.shadow.items()}
        with torch.no_grad():
            model.weight.add_(1.0)
        weights = {k: v.clone() for k, v in model.state_dict().items()}
        ema.swap(model)
        self.assertTrue(torch.equal(model.weight, average["weight"]))
        self.assertTrue(torch.equal(ema.shadow["weight"], weights["weight"]))
        ema.swap(model)
        self.assertTrue(torch.equal(model.weight, weights["weight"]))
        self.assertTrue(torch.equal(ema.shadow["weight"], average["weight"]))


class GradCheckpointTest(unittest.TestCase):
    def grads(self, device, on):
        model = tiny_model().to(device)
        model.train()
        ft.grad_checkpoint(model, on, device)
        ft.seed_all(5)
        mel = torch.randn(2, 120, 100, device=device)
        loss, _, _ = model(mel, text=[list("hei maailma"), list("toinen lause")],
                           lens=torch.tensor([120, 90], device=device))
        loss.backward()
        after = torch.rand(3, device=device).cpu()  # where the random stream is after the step
        return torch.cat([p.grad.flatten().cpu() for p in model.parameters() if p.grad is not None]), after

    def check(self, device):
        plain, after_plain = self.grads(device, False)
        saved, after_saved = self.grads(device, True)
        self.assertGreater(float(plain.norm()), 0.01)
        self.assertLess(float((plain - saved).abs().max()), 1e-7)
        self.assertTrue(torch.equal(after_plain, after_saved))

    def test_same_gradients_cpu(self):
        self.check("cpu")

    @unittest.skipUnless(torch.backends.mps.is_available(), "ei MPS-laitetta")
    def test_same_gradients_mps(self):
        # without the fix in grad_checkpoint the dropout masks of the recomputation differ and this fails (1e-3)
        self.check("mps")


class TrainTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        clips = make_clips()
        self.train_clips, self.val_clips = clips[:10], clips[10:]
        self.lines = []

    def run_train(self, model=None, **kw):
        cfg = kw.pop("cfg", None) or config()
        return ft.train(model or tiny_model(), self.train_clips, self.val_clips, self.dir, cfg, "cpu",
                        log=self.lines.append, **kw)

    def log_rows(self):
        return ft.read_log(self.dir)

    def test_trains_and_writes_files(self):
        model = tiny_model()
        start = {k: v.clone() for k, v in model.state_dict().items()}
        sampled = []
        step, why = self.run_train(model, sample_fn=lambda s: sampled.append((s, model.training)))
        self.assertEqual((step, why), (6, "valmis"))
        self.assertTrue(any(not torch.equal(v, start[k]) for k, v in model.state_dict().items()))
        self.assertEqual(sampled, [(3, False), (6, False)])  # samples are spoken in eval mode
        self.assertTrue(model.training)
        for name in ("malli_000003.safetensors", "malli_000006.safetensors", ft.STATE, ft.LOG):
            self.assertTrue(os.path.exists(os.path.join(self.dir, name)), name)
        rows = self.log_rows()
        self.assertEqual([int(r["step"]) for r in rows], [1, 2, 3, 4, 5, 6])
        self.assertTrue(all(np.isfinite(float(r["loss"])) for r in rows))
        self.assertEqual([bool(r["val"]) for r in rows], [False, True, True, True, False, True])
        self.assertEqual([bool(r["val_ema"]) for r in rows], [False, False, True, False, False, True])
        self.assertEqual(rows[0]["lr"], "5.00e-06")
        self.assertEqual(rows[-1]["lr"], "1.00e-05")

    def test_saved_model_loads_like_the_base_model(self):
        from f5_tts.infer.utils_infer import load_checkpoint
        from safetensors.torch import load_file

        model = tiny_model()
        self.run_train(model)
        path = ft.model_path(self.dir, 6)
        saved = load_file(path)
        self.assertEqual(set(saved), {"ema_model." + k for k in model.state_dict()})
        fresh = load_checkpoint(tiny_model(seed=9), path, "cpu", use_ema=True)  # as F5 and f5fi.load_model do
        ema = ft.Ema(tiny_model())
        ft.load_state(self.dir, tiny_model(), ema, torch.optim.AdamW(tiny_model().parameters()))
        for k, v in fresh.state_dict().items():
            self.assertTrue(torch.equal(v, ema.shadow[k]), k)
        # the saved model is the average, not the last weights
        self.assertTrue(any(not torch.equal(v, model.state_dict()[k]) for k, v in fresh.state_dict().items()))

    def test_continues_from_state(self):
        step, _ = self.run_train(cfg=config(steps=3))
        self.assertEqual(step, 3)
        model = tiny_model(seed=7)  # other weights: the state must replace them
        step, why = self.run_train(model, cfg=config(steps=6))
        self.assertEqual((step, why), (6, "valmis"))
        self.assertIn("Jatketaan askeleesta 3.", self.lines)
        self.assertEqual([int(r["step"]) for r in self.log_rows()], [1, 2, 3, 4, 5, 6])
        state = torch.load(os.path.join(self.dir, ft.STATE), weights_only=True)
        self.assertEqual(state["step"], 6)
        self.assertEqual({int(s["step"]) for s in state["optimizer"]["state"].values()}, {6})
        self.assertEqual(state["ema"]["updates"], 6)

    def test_state_restores_weights_average_and_optimizer(self):
        # a continued run shuffles its batches anew, so it is not the unbroken run bit for bit; what must hold is
        # that everything training depends on comes back exactly
        a = tiny_model()
        self.run_train(a, cfg=config(steps=3))
        b = tiny_model(seed=7)
        ema = ft.Ema(b)
        optimizer = torch.optim.AdamW(b.parameters(), lr=1.0)
        self.assertEqual(ft.load_state(self.dir, b, ema, optimizer), 3)
        for k, v in a.state_dict().items():
            self.assertTrue(torch.equal(v, b.state_dict()[k]), k)
        saved = torch.load(os.path.join(self.dir, ft.STATE), weights_only=True)
        for k, v in saved["ema"]["shadow"].items():
            self.assertTrue(torch.equal(v, ema.shadow[k]), k)
        moments = [s["exp_avg"] for s in optimizer.state_dict()["state"].values()]
        self.assertEqual(len(moments), len(list(b.parameters())))
        self.assertTrue(any(float(m.abs().sum()) > 0 for m in moments))

    def test_nothing_to_do_when_already_there(self):
        self.run_train(cfg=config(steps=3))
        before = os.path.getmtime(os.path.join(self.dir, ft.STATE))
        step, why = self.run_train(cfg=config(steps=3))
        self.assertEqual((step, why), (3, "valmis"))
        self.assertEqual(os.path.getmtime(os.path.join(self.dir, ft.STATE)), before)

    def test_stop_saves_state(self):
        stop = ft.Stop()
        calls = []

        def log(line):
            calls.append(line)
            if line.startswith("askel 2/"):
                stop.asked = True

        step, why = ft.train(tiny_model(), self.train_clips, self.val_clips, self.dir, config(steps=6), "cpu",
                             stop=stop, log=log)
        self.assertEqual((step, why), (2, "pysäytetty"))
        self.assertEqual(torch.load(os.path.join(self.dir, ft.STATE), weights_only=True)["step"], 2)
        self.assertFalse(os.path.exists(ft.model_path(self.dir, 2)))
        step, why = self.run_train(cfg=config(steps=6))
        self.assertEqual((step, why), (6, "valmis"))

    def test_accumulation(self):
        step, why = self.run_train(cfg=config(steps=4, accum=2, batch_frames=150))
        self.assertEqual((step, why), (4, "valmis"))
        with self.assertRaises(ValueError):
            self.run_train(cfg=config(steps=8, accum=500))

    def test_evaluate_is_repeatable_and_keeps_mode(self):
        model = tiny_model()
        model.train()
        lengths = [c.frames for c in self.val_clips]
        batches = ft.make_batches(lengths, 300, 32, random.Random(0))
        first = ft.evaluate(model, self.val_clips, batches, "cpu")
        torch.rand(10)
        self.assertEqual(first, ft.evaluate(model, self.val_clips, batches, "cpu"))
        self.assertTrue(model.training)
        self.assertIsNone(ft.evaluate(model, [], [], "cpu"))

    def test_page_lists_saved_models(self):
        texts = ["Ensimmäinen <lause>.", "Toinen."]
        for step in (0, 3):
            os.makedirs(ft.samples_dir(self.dir, step))
            for i in range(2):
                sf.write(os.path.join(ft.samples_dir(self.dir, step), f"lause{i + 1:02d}.wav"), np.zeros(240), 24000)
        ft.append_log(self.dir, {"step": 3, "val": "0.5000", "val_ema": "0.4000"})
        ft.write_page(self.dir, texts, "koe")
        with open(os.path.join(self.dir, "index.html"), encoding="utf-8") as f:
            page = f.read()
        self.assertIn("lähtömalli", page)
        self.assertIn("askel 3", page)
        self.assertIn("validointi 0.4000", page)
        self.assertIn('src="naytteet/askel_000003/lause02.wav"', page)
        self.assertIn("Ensimmäinen &lt;lause&gt;.", page)


class MemoryTest(unittest.TestCase):
    def test_parse_free_percent(self):
        text = "The system has 17179869184 (1048576 pages with a page size of 16384).\n\nSystem-wide memory free percentage: 72%\n"
        self.assertEqual(ft.parse_free_percent(text), 72)
        self.assertIsNone(ft.parse_free_percent("jotain muuta"))

    def test_free_memory_is_plausible(self):
        free, top = ft.free_memory_gb()
        if free is not None:
            self.assertTrue(0 < free < 4096)
            self.assertTrue(all(gb >= 0 and name for gb, name in top))


class MetadataCheckTest(unittest.TestCase):
    def test_stale_metadata_is_noticed(self):
        import prepare_dataset
        from unittest import mock

        d = tempfile.mkdtemp()
        with open(os.path.join(d, "lauseet1.tsv"), "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["file", "status", "written"], delimiter="\t")
            w.writeheader()
            w.writerow({"file": "lauseet1_01.wav", "status": "käytössä", "written": "Hei maailma."})
            w.writerow({"file": "", "status": "hylätty käsin", "written": "Ei mukaan."})
        with mock.patch.object(prepare_dataset.f5fi, "normalize_text", side_effect=str.lower):
            self.assertEqual(prepare_dataset.rebuild_metadata(d), 1)
            self.assertTrue(ft.metadata_is_current(d))
        with mock.patch.object(prepare_dataset.f5fi, "normalize_text", side_effect=str.upper):  # the rules changed
            self.assertFalse(ft.metadata_is_current(d))


if __name__ == "__main__":
    unittest.main()
