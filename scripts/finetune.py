"""Fine-tune F5-TTS Finnish on the clips of data/aineisto/metadata.csv.

    .venv/bin/python scripts/finetune.py --name oma-v1                  # new run from the base model
    .venv/bin/python scripts/finetune.py --name oma-v1                  # the same command continues a stopped run
    .venv/bin/python scripts/finetune.py --name oma-v1 --steps 5000     # ... or trains it further
    .venv/bin/python scripts/finetune.py --name oma-v2 --init checkpoints/oma-v1/malli_003000.safetensors

A run lives in checkpoints/<name>/:
    malli_000500.safetensors   weights for speaking (speak.py --ckpt, f5fi.load_model), one per --save-every steps
    tila.pt                    training state for continuing (weights, optimizer, average), overwritten
    loki.csv                   loss, validation loss, speed and memory by step
    asetukset.json             settings and every session of the run (data size, device)
    naytteet/, index.html      the same test sentences spoken by every saved model: the local page for listening

The data is read anew at every start, so new recordings are used as soon as prepare_dataset.py has added them to
metadata.csv: continue the run or start a new one. One clip in twenty is held out for validation, picked by the
clip's name, so a clip stays on its side when the data grows.

Written for a 16 GB M3 Mac, runs on any device torch finds:
- The loop is our own instead of F5's Trainer: that one keeps a second copy of the model on the device, writes
  5 GB checkpoints with the optimizer in each and needs the data in its own format.
- The loss is F5's own (CFM.forward: random span to fill in, classifier-free guidance drops). Texts go through
  the same character conversion as at inference (convert_char_to_pinyin, which also puts spaces inside words
  after ä and ö), since that is what the base model has learned.
- Activations are recomputed on the way back (gradient checkpointing, --no-grad-checkpoint for a GPU with
  room), the averaged weights are kept on the CPU and a batch holds --batch-frames padded mel frames (1600 is
  about 17 s of audio). On MPS torch does not restore the random state for the recomputation, so dropout would
  differ from the forward pass and the gradients would be slightly wrong; grad_checkpoint() restores it.
- The two heaviest batches are run first, so running out of memory shows in the first minute and not at night.
- If memory runs out and the machine starts swapping, steps slow down tenfold: the run then saves its state and
  stops. Ctrl-C also saves and stops; the same command continues.

The page and the audio are local: do not publish them. The fine-tuned weights are derived from the base model
and carry its licence (CC BY-NC 4.0).
"""
import argparse
import csv
import hashlib
import html
import json
import math
import os
import random
import shutil
import signal
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field

import soundfile as sf
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SR = 24000
HOP = 256
FRAMES_PER_S = SR / HOP
MIN_CLIP_S = 0.3  # as F5's own dataset filter
VAL_PER_MILLE = 50  # one clip in twenty is validation
STATE = "tila.pt"
LOG = "loki.csv"
SETTINGS = "asetukset.json"
LOG_FIELDS = ["step", "time", "epoch", "loss", "lr", "val", "val_ema", "s_per_step", "mem_gb"]
NEED_FREE_GB = 9.0  # free memory wanted before a run on a machine without a separate GPU memory (see README)
SLOW_FACTOR = 8.0  # a step this many times slower than the median ...
SLOW_MIN_S = 20.0  # ... and at least this slow ...
SLOW_STEPS = 3  # ... this many times in a row means the machine is swapping

# Sentences the model has not been trained on, from the listening rounds of docs/aantamishavainnot.md: stress on a
# new term, a connective, a list, a comma before a subordinate clause, a question and a short line.
SAMPLE_TEXTS = [
    "Ilmiöstä käytetään nimeä metakognitiivinen laiskuus.",
    "Pysähdytään silti vaikeampaan kysymykseen.",
    "Tekoäly voi luonnostella, ideoida ja haastaa.",
    "Kielimallin rakentamista ei tarvitse ymmärtää.",
    "Mitä minun pitää tässä ymmärtää itse?",
    "Kiitos avusta.",
]


@dataclass
class Config:
    steps: int = 3000
    lr: float = 1e-5
    warmup: int = 200
    batch_frames: int = 1600
    max_samples: int = 32
    accum: int = 1
    max_grad_norm: float = 1.0
    ema_beta: float = 0.999
    ema_every: int = 10
    save_every: int = 500
    val_every: int = 100
    log_every: int = 25
    seed: int = 1
    grad_checkpoint: bool = True


@dataclass
class Clip:
    name: str
    text: list  # characters as the model gets them
    mel: torch.Tensor  # [frames, mel channels], on the CPU
    frames: int = field(init=False)

    def __post_init__(self):
        self.frames = self.mel.shape[0]


# ---------------------------------------------------------------- data


def read_metadata(path):
    with open(path, encoding="utf-8", newline="") as f:
        return [(r["audio_file"], r["text"]) for r in csv.DictReader(f, delimiter="|")]


def is_val(name, per_mille=VAL_PER_MILLE):
    """Whether the clip is held out for validation. Decided by its name alone, so a clip never changes sides when
    more recordings are added."""
    return int(hashlib.sha1(os.path.basename(name).encode("utf-8")).hexdigest(), 16) % 1000 < per_mille


def load_clips(rows, mel_fn, to_chars, max_clip_s, log=print):
    """Clips with their mel spectrograms. Returns (clips, skipped) where skipped is [(name, reason)]."""
    clips, skipped = [], []
    for path, text in rows:
        name = os.path.splitext(os.path.basename(path))[0]
        if not os.path.exists(path):
            skipped.append((name, "tiedosto puuttuu"))
            continue
        wave, sr = sf.read(path, dtype="float32", always_2d=True)
        seconds = len(wave) / sr
        if sr != SR:
            skipped.append((name, f"näytetaajuus {sr}, pitää olla {SR}"))
        elif not text.strip():
            skipped.append((name, "teksti puuttuu"))
        elif seconds < MIN_CLIP_S:
            skipped.append((name, f"liian lyhyt ({seconds:.1f} s)"))
        elif seconds > max_clip_s:
            skipped.append((name, f"liian pitkä ({seconds:.1f} s > {max_clip_s:g} s)"))
        else:
            clips.append(Clip(name, to_chars(text), mel_fn(torch.from_numpy(wave.mean(axis=1)))))
    for name, why in skipped:
        log(f"  ohitettu {name}: {why}")
    return clips, skipped


def make_batches(lengths, batch_frames, max_samples, rng):
    """Batches of clip indices. Clips of similar length go together, so little is wasted on padding: a batch costs
    its clip count times its longest clip, and that stays within batch_frames. A clip longer than batch_frames is a
    batch of its own. The order of batches and the clips in them change with rng."""
    order = list(range(len(lengths)))
    rng.shuffle(order)
    pool = max(max_samples * 4, 64)
    batches = []
    for i in range(0, len(order), pool):
        batch, longest = [], 0
        for j in sorted(order[i:i + pool], key=lambda k: lengths[k]):
            if batch and ((len(batch) + 1) * max(longest, lengths[j]) > batch_frames or len(batch) >= max_samples):
                batches.append(batch)
                batch, longest = [], 0
            batch.append(j)
            longest = max(longest, lengths[j])
        if batch:
            batches.append(batch)
    rng.shuffle(batches)
    return batches


def batch_cost(batch, lengths):
    return len(batch) * max(lengths[i] for i in batch)


def heaviest_first(batches, lengths):
    """The batch with the most padded frames and the one with the longest clip moved to the front."""
    if not batches:
        return batches
    big = max(range(len(batches)), key=lambda b: batch_cost(batches[b], lengths))
    long = max(range(len(batches)), key=lambda b: max(lengths[i] for i in batches[b]))
    front = [big] + ([long] if long != big else [])
    return [batches[b] for b in front] + [x for b, x in enumerate(batches) if b not in front]


def collate(clips, batch, device):
    mels = [clips[i].mel for i in batch]
    lens = torch.tensor([m.shape[0] for m in mels], device=device)
    mel = torch.nn.utils.rnn.pad_sequence(mels, batch_first=True).to(device)
    return mel, [clips[i].text for i in batch], lens


# ---------------------------------------------------------------- averaged weights


class Ema:
    """Running average of the weights, kept on the CPU so that it takes no device memory. The saved models are this
    average: it evens out the noise of small batches. Updated every `every` steps with the decay of that many
    single steps, and following the model faster at the start of a run ((1 + n) / (10 + n) on update n)."""

    def __init__(self, model, beta=0.999, every=10):
        self.beta, self.every, self.updates = beta, every, 0
        self.shadow = {k: v.detach().to("cpu", copy=True) for k, v in model.state_dict().items()}

    def update(self, model, step):
        if step % self.every:
            return
        self.updates += 1
        decay = min(self.beta ** self.every, (1 + self.updates) / (10 + self.updates))
        with torch.no_grad():
            for k, v in model.state_dict().items():
                if v.dtype.is_floating_point:
                    self.shadow[k].lerp_(v.detach().to("cpu"), 1 - decay)
                else:
                    self.shadow[k].copy_(v)

    def swap(self, model):
        """Exchange the model's weights and the average, in place. A second call puts both back."""
        with torch.no_grad():
            for k, v in model.state_dict().items():
                mine = self.shadow[k]
                self.shadow[k] = v.detach().to("cpu", copy=True)
                v.copy_(mine)

    def state(self):
        return {"shadow": self.shadow, "updates": self.updates}

    def load(self, state):
        self.shadow, self.updates = state["shadow"], state["updates"]


# ---------------------------------------------------------------- files of a run


def save_state(run_dir, step, model, ema, optimizer):
    """Everything needed to continue. Written beside and renamed, so a crash never leaves a half-written state."""
    path = os.path.join(run_dir, STATE)
    # tensors are written from the device as they are: a CPU copy of the whole model first would take 1.35 GB more
    torch.save({"step": step, "model": model.state_dict(), "ema": ema.state(),
                "optimizer": optimizer.state_dict()}, path + ".tmp")
    os.replace(path + ".tmp", path)


def load_state(run_dir, model, ema, optimizer):
    state = torch.load(os.path.join(run_dir, STATE), map_location="cpu", weights_only=True)
    model.load_state_dict(state["model"])
    ema.load(state["ema"])
    optimizer.load_state_dict(state["optimizer"])
    return state["step"]


def model_path(run_dir, step):
    return os.path.join(run_dir, f"malli_{step:06d}.safetensors")


def save_model(run_dir, step, ema):
    """The averaged weights in the format of the base model (keys ema_model.*), which F5 and f5fi.load_model read."""
    from safetensors.torch import save_file

    path = model_path(run_dir, step)
    save_file({"ema_model." + k: v.contiguous() for k, v in ema.shadow.items()}, path + ".tmp")
    os.replace(path + ".tmp", path)
    return path


def read_log(run_dir):
    path = os.path.join(run_dir, LOG)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def append_log(run_dir, row):
    path = os.path.join(run_dir, LOG)
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in LOG_FIELDS})


# ---------------------------------------------------------------- training


def lr_at(step, cfg):
    """Learning rate of update `step` (1-based): a linear warm-up, then constant. No decay towards an end, so a run
    can be trained further without its past changing."""
    return cfg.lr * min(1.0, step / max(1, cfg.warmup))


def seed_all(seed):
    random.seed(seed)  # CFM.forward draws its guidance drops from here
    torch.manual_seed(seed)


def evaluate(model, clips, batches, device, seed=1234, repeats=2):
    """Mean loss over the validation clips with the same noise, masks and times every time, so values compare."""
    if not batches:
        return None
    was_training = model.training
    model.eval()
    total, n = 0.0, 0
    with torch.no_grad():
        for r in range(repeats):
            seed_all(seed + r)
            for batch in batches:
                mel, text, lens = collate(clips, batch, device)
                loss, _, _ = model(mel, text=text, lens=lens)
                total += loss.item() * len(batch)
                n += len(batch)
    model.train(was_training)
    return total / n


def release_memory(device):
    """Give back the device memory torch keeps for reuse. Batches differ in shape, so the kept blocks pile up:
    in the first long run the process grew from 6.6 to 7.6 GB in 600 steps and the steps slowed down by a third."""
    if str(device).startswith("mps"):
        torch.mps.empty_cache()
    elif str(device).startswith("cuda"):
        torch.cuda.empty_cache()


def memory_gb(device):
    device = str(device)
    if device.startswith("mps"):
        return torch.mps.driver_allocated_memory() / 2 ** 30
    if device.startswith("cuda"):
        return torch.cuda.max_memory_allocated() / 2 ** 30
    try:
        import psutil
        return psutil.Process().memory_info().rss / 2 ** 30
    except ImportError:
        return 0.0


def grad_checkpoint(model, on, device):
    """Turn F5's activation checkpointing on or off. With it a block's activations are not kept for the backward
    pass but computed again, which needs the same dropout masks as the first time. torch.utils.checkpoint restores
    the random state for the CPU and CUDA but not for MPS, so there the block wrapper does it itself."""
    transformer = getattr(model, "transformer", None)
    if transformer is None or not hasattr(transformer, "checkpoint_activations"):
        return
    transformer.checkpoint_activations = on
    if on and str(device).startswith("mps"):
        def wrapper(block):
            saved = []

            def run(x, t, mask, rope):
                if not saved:  # the forward pass
                    saved.append(torch.mps.get_rng_state())
                    return block(x, t, mask=mask, rope=rope)
                now = torch.mps.get_rng_state()  # the recomputation: same masks, and the stream goes on untouched
                torch.mps.set_rng_state(saved[0])
                try:
                    return block(x, t, mask=mask, rope=rope)
                finally:
                    torch.mps.set_rng_state(now)

            return run

        transformer.ckpt_wrapper = wrapper


class Stop:
    """Ctrl-C asks the run to stop after the current step; a second Ctrl-C stops at once."""

    def __init__(self):
        self.asked = False

    def __call__(self, *_):
        if self.asked:
            raise KeyboardInterrupt
        self.asked = True
        print("\nPysäytetään tämän askeleen jälkeen ja tallennetaan tila (toinen Ctrl-C keskeyttää heti).", flush=True)


def train(model, train_clips, val_clips, run_dir, cfg, device, sample_fn=None, stop=None, log=print):
    """Train `model` until cfg.steps updates and return (step reached, why it ended). Continues from the state in
    run_dir if there is one. sample_fn(step) is called with the averaged weights in the model after each saved
    model; its return value is ignored. `why` is "valmis", "pysäytetty" or "hidas"."""
    os.makedirs(run_dir, exist_ok=True)
    stop = stop or Stop()
    grad_checkpoint(model, cfg.grad_checkpoint, device)
    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(params, lr=cfg.lr)
    ema = Ema(model, cfg.ema_beta, cfg.ema_every)
    step = 0
    if os.path.exists(os.path.join(run_dir, STATE)):
        step = load_state(run_dir, model, ema, optimizer)
        log(f"Jatketaan askeleesta {step}.")
    if step >= cfg.steps:
        log(f"Ajo on jo askeleessa {step} (tavoite {cfg.steps}). Anna suurempi --steps, jos haluat jatkaa.")
        return step, "valmis"

    lengths = [c.frames for c in train_clips]
    val_lengths = [c.frames for c in val_clips]
    val_batches = sorted(make_batches(val_lengths, cfg.batch_frames, cfg.max_samples, random.Random(0)))
    steps_per_epoch = len(make_batches(lengths, cfg.batch_frames, cfg.max_samples, random.Random(0))) // cfg.accum
    if steps_per_epoch < 1:
        raise ValueError(f"Aineistosta tulee vähemmän eriä kuin --accum {cfg.accum}. Pienennä --accum-arvoa.")

    def checkpoint():
        """Save the state and the averaged model, speak the samples with it. Returns its validation loss."""
        save_state(run_dir, step, model, ema, optimizer)
        path = save_model(run_dir, step, ema)
        ema.swap(model)
        try:
            val_ema = evaluate(model, val_clips, val_batches, device)
            if sample_fn:
                grad_checkpoint(model, False, device)  # nothing to recompute without gradients
                model.eval()
                try:
                    sample_fn(step)
                finally:
                    model.train()
                    grad_checkpoint(model, cfg.grad_checkpoint, device)
        finally:
            ema.swap(model)
        log(f"  tallennettu {os.path.basename(path)}")
        return val_ema

    model.train()
    seed_all(cfg.seed * 100003 + step)
    session_start, first_epoch = step, True
    losses, times, slow = [], [], 0
    why = "valmis"
    optimizer.zero_grad(set_to_none=True)
    try:
        while step < cfg.steps and why == "valmis":
            batches = make_batches(lengths, cfg.batch_frames, cfg.max_samples, random.Random(f"{cfg.seed}-{step}"))
            if first_epoch:
                batches, first_epoch = heaviest_first(batches, lengths), False
            for k in range(0, len(batches) - cfg.accum + 1, cfg.accum):
                t0 = time.monotonic()
                for g in optimizer.param_groups:
                    g["lr"] = lr_at(step + 1, cfg)
                loss_sum = 0.0
                for batch in batches[k:k + cfg.accum]:
                    mel, text, lens = collate(train_clips, batch, device)
                    loss, _, _ = model(mel, text=text, lens=lens)
                    (loss / cfg.accum).backward()
                    loss_sum += loss.item()
                if not math.isfinite(loss_sum):
                    raise RuntimeError(f"Häviö ei ole luku askeleessa {step + 1}. Viimeisin tallennettu tila on "
                                       "ehjä; kokeile pienempää --lr-arvoa.")
                if cfg.max_grad_norm > 0:
                    torch.nn.utils.clip_grad_norm_(params, cfg.max_grad_norm)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                step += 1
                ema.update(model, step)
                losses.append(loss_sum / cfg.accum)
                if str(device).startswith("mps"):
                    torch.mps.synchronize()
                dt = time.monotonic() - t0

                if step - session_start == 2:
                    log(f"  raskaimmat erät mahtuivat muistiin ({memory_gb(device):.1f} Gt)")
                # swapping shows as steps that take many times longer than usual
                if len(times) >= 5 and dt > max(SLOW_MIN_S, SLOW_FACTOR * statistics.median(times)):
                    slow += 1
                else:
                    slow = 0
                    times.append(dt)
                saving = step % cfg.save_every == 0 or step == cfg.steps
                val = val_ema = None
                if saving or step % cfg.val_every == 0:
                    val = evaluate(model, val_clips, val_batches, device)
                if saving:
                    val_ema = checkpoint()
                if val is not None:
                    seed_all(cfg.seed * 100003 + step)  # evaluation and samples reseed; training goes on from here
                if saving or val is not None or step % cfg.log_every == 0:
                    mem = memory_gb(device)  # read before the release below, so the log shows what was in use
                    release_memory(device)
                    row = {"step": step, "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                           "epoch": round(step / steps_per_epoch, 2), "loss": fmt(statistics.fmean(losses)),
                           "lr": f"{lr_at(step, cfg):.2e}", "val": fmt(val), "val_ema": fmt(val_ema),
                           "s_per_step": round(statistics.median(times[-50:]), 2) if times else "",
                           "mem_gb": round(mem, 1)}
                    append_log(run_dir, row)
                    log(f"askel {step}/{cfg.steps}  häviö {row['loss']}"
                        + (f"  validointi {row['val']}" if val is not None else "")
                        + (f"  keskiarvomallilla {row['val_ema']}" if val_ema is not None else "")
                        + f"  {row['s_per_step']} s/askel  {row['mem_gb']} Gt"
                        + f"  jäljellä {duration((cfg.steps - step) * (row['s_per_step'] or 0))}")
                    losses = []
                if step >= cfg.steps:
                    break
                if slow >= SLOW_STEPS:
                    why = "hidas"
                    break
                if stop.asked:
                    why = "pysäytetty"
                    break
    except KeyboardInterrupt:
        why = "pysäytetty"
    if why != "valmis" and step > session_start:
        save_state(run_dir, step, model, ema, optimizer)
        log(f"Tila tallennettu askeleessa {step}.")
    return step, why


def fmt(x):
    return "" if x is None else f"{x:.4f}"


def duration(seconds):
    m = int(seconds // 60)
    return f"{m // 60} h {m % 60} min" if m >= 60 else f"{m} min"


# ---------------------------------------------------------------- listening page


def samples_dir(run_dir, step):
    return os.path.join(run_dir, "naytteet", f"askel_{step:06d}")


def write_page(run_dir, texts, name):
    """index.html of the run: every test sentence spoken by every saved model, oldest first."""
    e = html.escape
    root = os.path.join(run_dir, "naytteet")
    steps = sorted(int(d.split("_")[1]) for d in os.listdir(root) if d.startswith("askel_")) if os.path.isdir(root) else []
    val = {int(r["step"]): r for r in read_log(run_dir) if r.get("val_ema")}
    head = "".join(f"<th>{'lähtömalli' if s == 0 else f'askel {s}'}"
                   + (f"<div class=note>validointi {e(val[s]['val_ema'])}</div>" if s in val else "") + "</th>"
                   for s in steps)
    rows = []
    for i, text in enumerate(texts):
        cells = []
        for s in steps:
            wav = os.path.join(samples_dir(run_dir, s), f"lause{i + 1:02d}.wav")
            src = os.path.relpath(wav, run_dir)
            cells.append(f'<td><audio controls preload="none" src="{e(src)}"></audio></td>' if os.path.exists(wav)
                         else "<td class=note>ei näytettä</td>")
        rows.append(f"<tr><th class=text>{e(text)}</th>{''.join(cells)}</tr>")
    page = f"""<!doctype html><html lang="fi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Hienosäätö {e(name)}</title>
<style>
:root{{--bg:#f6f3ec;--fg:#1f2a26;--muted:#5c6862;--card:#fff;--line:#d9d3c7}}
@media (prefers-color-scheme:dark){{:root{{--bg:#191c1b;--fg:#e7e4dc;--muted:#a3aba6;--card:#232826;--line:#3a403d}}}}
body{{font:15px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--fg);margin:0;padding:16px}}
.wrap{{overflow-x:auto}} table{{border-collapse:collapse;background:var(--card)}}
th,td{{border:1px solid var(--line);padding:8px;vertical-align:top;text-align:left}}
th.text{{min-width:14em;max-width:22em;font-weight:500}} audio{{width:230px}}
.note{{color:var(--muted);font-size:.85rem;font-weight:400}}
</style></head><body>
<h1>Hienosäätö {e(name)}</h1>
<p>Jokainen sarake on yksi tallennettu malli ja jokainen rivi sama lause samalla viitteellä ja siemenellä.
Kuuntele vasemmalta oikealle: äänen pitäisi muuttua omaksesi ja pysyä selkeänä. Jos myöhempi malli alkaa
kuulostaa huonommalta (sotkeutuvia sanoja, tasaisempaa luentaa), aiempi malli on parempi valinta, vaikka sen häviö
olisi suurempi. Validointiluku on häviö pätkillä, joita malli ei ole nähnyt: pienempi on parempi, mutta korva
ratkaisee. Sivu on paikallinen tiedosto: älä julkaise sitä tai ääntä verkkoon.</p>
<div class=wrap><table><tr><th>Lause</th>{head}</tr>{''.join(rows)}</table></div>
</body></html>
"""
    with open(os.path.join(run_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)


# ---------------------------------------------------------------- command line


def free_memory_gb():
    """(free memory in GB or None, the five processes using most). On macOS the figure is the one the system itself
    reports as free (memory_pressure): free, inactive and purgeable pages. psutil's "available" leaves out memory
    macOS gives up readily and shows about half of it."""
    try:
        import psutil
    except ImportError:
        return None, []
    top = []
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            top.append((p.info["memory_info"].rss / 2 ** 30, p.info["name"]))
        except (psutil.Error, AttributeError, TypeError):
            pass
    top = sorted(top, reverse=True)[:5]
    vm = psutil.virtual_memory()
    if sys.platform == "darwin" and shutil.which("memory_pressure"):
        try:
            out = subprocess.run(["memory_pressure"], capture_output=True, text=True, timeout=20).stdout
            percent = parse_free_percent(out)
            if percent is not None:
                return vm.total / 2 ** 30 * percent / 100, top
        except (OSError, subprocess.SubprocessError):
            pass
    return vm.available / 2 ** 30, top


def parse_free_percent(text):
    """The number in memory_pressure's line 'System-wide memory free percentage: 72%', or None."""
    for line in text.splitlines():
        if "free percentage" in line:
            digits = "".join(c for c in line.split(":")[-1] if c.isdigit())
            return int(digits) if digits else None
    return None


def metadata_is_current(dataset):
    """Whether metadata.csv is what prepare_dataset.py would write now from the .tsv files and the current text
    rules. A stale file would teach the model other spellings than it gets when speaking."""
    import prepare_dataset

    return read_metadata(os.path.join(dataset, "metadata.csv")) == prepare_dataset.metadata_rows(dataset)


def main():
    import f5fi

    d = Config()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True, help="name of the run: checkpoints/<name>/")
    ap.add_argument("--dataset", default=os.path.join(f5fi.ROOT, "data", "aineisto"), help="folder with metadata.csv")
    ap.add_argument("--init", default=f5fi.BASE_CKPT, help="weights a new run starts from (default: the base model)")
    ap.add_argument("--steps", type=int, default=d.steps, help=f"updates in all, also when continuing (default {d.steps})")
    ap.add_argument("--lr", type=float, default=d.lr)
    ap.add_argument("--warmup", type=int, default=d.warmup, help="updates over which the learning rate rises")
    ap.add_argument("--batch-frames", type=int, default=d.batch_frames,
                    help=f"padded mel frames in a batch, {FRAMES_PER_S:.0f} per second (default {d.batch_frames})")
    ap.add_argument("--accum", type=int, default=d.accum, help="batches per update; with a smaller --batch-frames")
    ap.add_argument("--max-clip-s", type=float, default=15.0, help="longer clips are left out (memory)")
    ap.add_argument("--save-every", type=int, default=d.save_every, help="updates between saved models and samples")
    ap.add_argument("--val-every", type=int, default=d.val_every)
    ap.add_argument("--seed", type=int, default=d.seed)
    ap.add_argument("--no-grad-checkpoint", action="store_true", help="keep activations in memory: faster, needs a GPU with room")
    ap.add_argument("--samples", help="text file with the test sentences, one per line (default: six built in)")
    ap.add_argument("--no-samples", action="store_true", help="do not speak the test sentences")
    ap.add_argument("--sample-ref", default=f5fi.DEFAULT_REF, help="reference clip of the samples")
    ap.add_argument("--no-metadata-check", action="store_true", help="train even if metadata.csv is not up to date")
    ap.add_argument("--force", action="store_true", help="start even if little memory is free")
    args = ap.parse_args()
    cfg = Config(steps=args.steps, lr=args.lr, warmup=args.warmup, batch_frames=args.batch_frames, accum=args.accum,
                 save_every=args.save_every, val_every=args.val_every, seed=args.seed,
                 grad_checkpoint=not args.no_grad_checkpoint)

    run_dir = os.path.join(f5fi.ROOT, "checkpoints", args.name)
    resuming = os.path.exists(os.path.join(run_dir, STATE))
    if not os.path.exists(os.path.join(args.dataset, "metadata.csv")):
        sys.exit(f"{args.dataset}/metadata.csv puuttuu. Aja ensin prepare_dataset.py.")
    if not args.no_metadata_check and not metadata_is_current(args.dataset):
        sys.exit("metadata.csv ei vastaa .tsv-tiedostoja tai nykyisiä tekstisääntöjä. Kokoa se uudelleen:\n"
                 "  .venv/bin/python scripts/prepare_dataset.py --rebuild\n"
                 "(--no-metadata-check ohittaa tarkistuksen.)")

    free, top = free_memory_gb()
    if free is not None and not torch.cuda.is_available():
        print(f"Vapaata muistia {free:.1f} Gt.")
        if free < NEED_FREE_GB:
            print(f"Hienosäätö tarvitsee noin {NEED_FREE_GB:g} Gt. Sulje muistia vievät ohjelmat ennen ajoa. "
                  "Eniten muistia käyttävät nyt:")
            for gb, pname in top:
                print(f"  {gb:4.1f} Gt  {pname}")
            if not args.force:
                sys.exit("Ajo ei käynnistynyt. Sulje ohjelmia ja aja komento uudelleen, tai ohita tarkistus valitsimella --force.")

    texts = SAMPLE_TEXTS
    if args.samples:
        with open(args.samples, encoding="utf-8") as f:
            texts = [line.strip() for line in f if line.strip()]

    from f5_tts.model.utils import convert_char_to_pinyin

    init = args.init
    t0 = time.monotonic()
    tts = f5fi.load_model(init)  # a continued run overwrites these weights with its state
    model, device = tts.ema_model, tts.device
    print(f"Malli ladattu {time.monotonic() - t0:.0f} s, laite {device}.")

    rows = read_metadata(os.path.join(args.dataset, "metadata.csv"))
    with torch.no_grad():
        clips, skipped = load_clips(rows, lambda w: model.mel_spec(w[None].to(device))[0].T.cpu(),
                                    lambda t: convert_char_to_pinyin([t])[0], args.max_clip_s)
    unknown = sorted({c for clip in clips for c in clip.text if c not in model.vocab_char_map})
    if unknown:
        sys.exit(f"Aineistossa on merkkejä, joita mallin sanastossa ei ole: {' '.join(unknown)}. Korjaa tekstit.")
    train_clips = [c for c in clips if not is_val(c.name)]
    val_clips = [c for c in clips if is_val(c.name)]
    minutes = sum(c.frames for c in train_clips) / FRAMES_PER_S / 60
    print(f"Aineisto: {len(train_clips)} pätkää opetukseen ({minutes:.1f} min), {len(val_clips)} validointiin"
          + (f", {len(skipped)} ohitettu" if skipped else "") + ".")
    if not train_clips:
        sys.exit("Ei opetettavia pätkiä.")

    os.makedirs(run_dir, exist_ok=True)
    settings_path = os.path.join(run_dir, SETTINGS)
    settings = {"name": args.name, "init": os.path.relpath(init, f5fi.ROOT), "sessions": []}
    if os.path.exists(settings_path):
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)
    elif resuming:
        print("asetukset.json puuttuu; jatketaan tilasta.")
    with open(os.path.join(args.dataset, "metadata.csv"), "rb") as f:
        sha = hashlib.sha1(f.read()).hexdigest()[:12]
    settings["sessions"].append({
        "started": time.strftime("%Y-%m-%d %H:%M:%S"), "config": asdict(cfg), "device": str(device),
        "torch": torch.__version__, "train_clips": len(train_clips), "train_min": round(minutes, 1),
        "val_clips": len(val_clips), "skipped": [n for n, _ in skipped], "max_clip_s": args.max_clip_s,
        "metadata_sha1": sha, "sample_ref": os.path.relpath(args.sample_ref, f5fi.ROOT)})
    settings["sample_texts"] = texts
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=1)

    sample_fn = None
    if not args.no_samples:
        with open(os.path.splitext(args.sample_ref)[0] + ".txt", encoding="utf-8") as f:
            ref_text = f.read().strip()

        def sample_fn(step):
            out = samples_dir(run_dir, step)
            os.makedirs(out, exist_ok=True)
            for i, text in enumerate(texts):
                f5fi.synthesize(tts, args.sample_ref, ref_text, text, os.path.join(out, f"lause{i + 1:02d}.wav"))
            write_page(run_dir, texts, args.name)
            if str(device).startswith("mps"):
                torch.mps.empty_cache()

        if not resuming and not os.path.isdir(samples_dir(run_dir, 0)):
            print("Puhutaan testilauseet lähtömallilla vertailua varten.")
            model.eval()
            sample_fn(0)

    awake = None
    if sys.platform == "darwin" and shutil.which("caffeinate"):
        awake = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])  # no idle sleep during the run
    stop = Stop()
    signal.signal(signal.SIGINT, stop)
    try:
        step, why = train(model, train_clips, val_clips, run_dir, cfg, device, sample_fn=sample_fn, stop=stop)
    except RuntimeError as err:
        if "out of memory" in str(err).lower() or "insufficient memory" in str(err).lower():
            sys.exit(f"Muisti loppui: {err}\nSulje muita ohjelmia tai pienennä erää, esimerkiksi "
                     f"--batch-frames {cfg.batch_frames // 2} --accum {cfg.accum * 2}, tai lyhennä pisintä pätkää "
                     "valitsimella --max-clip-s. Sama komento jatkaa viimeisimmästä tallennuksesta.")
        raise
    finally:
        if awake:
            awake.terminate()

    again = f".venv/bin/python scripts/finetune.py --name {args.name}"
    if why == "hidas":
        print(f"Askeleet hidastuivat moninkertaisesti, eli kone siirtää muistia levylle. Ajo pysäytettiin askeleeseen "
              f"{step}. Sulje muistia vievät ohjelmat ja jatka:\n  {again}")
        sys.exit(3)
    if why == "pysäytetty":
        print(f"Pysäytetty askeleeseen {step}. Jatka samalla komennolla:\n  {again}")
        sys.exit(130)
    last = model_path(run_dir, step)
    print(f"Valmis: {step} askelta.\nKuuntele: open {os.path.relpath(os.path.join(run_dir, 'index.html'), f5fi.ROOT)}"
          f"\nKäyttö: .venv/bin/python scripts/speak.py \"Tekstiä.\" --ckpt {os.path.relpath(last, f5fi.ROOT)} --out puhe.wav")


if __name__ == "__main__":
    main()
