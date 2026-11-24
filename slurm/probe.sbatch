#!/bin/bash
#SBATCH --job-name=f5fi-koe
#SBATCH --partition=interactive
#SBATCH --gres=gpu:a30:1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:20:00
#SBATCH --output=%x-%j.log
#
# Koe ennen asennusta: mitä solmu tarjoaa? Aja: sbatch slurm/probe.sbatch ja lue f5fi-koe-<työ>.log.
# Lopussa solmulla käynnistetään 4 minuutiksi pieni HTTP-palvelin, jotta nähdään, tavoittaako Rooliharjoittelun
# kone solmun portin.
echo "== solmu"; hostname; uname -r
head -3 /etc/os-release 2>/dev/null; ldd --version 2>&1 | head -1
echo; echo "== GPU ja ajuri"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
nvidia-smi 2>&1 | grep -m1 "CUDA Version"
echo; echo "== Slurm"
scontrol show job "$SLURM_JOB_ID" | grep -E "Partition=|TimeLimit=|TresPerNode|Gres" | head -5
sinfo -o "%P %G %l %D" 2>&1 | head -12
echo; echo "== Python ja kääntäjät"
python3 --version; command -v module >/dev/null 2>&1 && (module avail conda python gcc 2>&1 | head -15)
g++ --version 2>&1 | head -1; make --version 2>&1 | head -1; command -v conda uv curl tar ar 2>&1
echo; echo "== levy (kotikansio, työkansio, paikallinen TMPDIR) ja kiintiö"
df -h "$HOME" "${TMPDIR:-/tmp}" 2>&1 | head -4; echo "TMPDIR=${TMPDIR:-}"
quota -s 2>&1 | head -4; lfs quota -h "$HOME" 2>&1 | head -4
echo; echo "== lähtevä verkko (HTTP-koodi, 000 = ei yhteyttä)"
for u in https://pypi.org http://archive.ubuntu.com https://conda.anaconda.org https://huggingface.co https://download.pytorch.org https://github.com; do
  printf '%-34s ' "$u"; curl -s -o /dev/null -w '%{http_code}\n' --max-time 10 -I "$u" || echo 000
done
echo; echo "== torch (jos ympäristö on jo asennettu)"
ENV=${F5_ENV:-$HOME/F5-FI-Jooseppi/.env-lehmus}
if [ -x "$ENV/bin/python" ]; then
  "$ENV/bin/python" -c "
import time, torch
print('torch', torch.__version__, 'CUDA', torch.version.cuda, 'käytettävissä', torch.cuda.is_available())
if torch.cuda.is_available():
    print(torch.cuda.get_device_name(0)); x = torch.randn(8192, 8192, device='cuda'); torch.cuda.synchronize(); t = time.time()
    for _ in range(10): x @ x
    torch.cuda.synchronize(); print('10 matriisikertolaskua', round(time.time() - t, 3), 's')"
else
  echo "ei vielä: $ENV"
fi
echo; echo "== portin tavoitettavuus"
PORT=$(python3 -c 'import socket; s=socket.socket(); s.bind(("",0)); print(s.getsockname()[1])')
echo "Kokeile 4 minuutin ajan siltä koneelta, jossa Rooliharjoittelu pyörii:   curl -sS http://$(hostname):$PORT/"
echo "Jos ei vastaa, kokeile myös: curl -sS http://$(hostname -f 2>/dev/null):$PORT/  (ja ssh-tunneli kirjautumissolmun kautta)"
timeout 240 python3 -m http.server "$PORT" --bind 0.0.0.0 >/dev/null 2>&1
echo "koe päättyi"
