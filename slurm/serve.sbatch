#!/bin/bash
#SBATCH --job-name=f5fi-puhe
#SBATCH --partition=interactive
#SBATCH --gres=gpu:a30:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=24G
#SBATCH --time=7-00:00:00
#SBATCH --signal=B:USR1@900
#SBATCH --output=%x-%j.log
#
# Puhepalvelu Slurm-työnä. Käynnistys: sbatch slurm/serve.sbatch   Sammutus: scancel --name=f5fi-puhe
# Tarkista GRES-nimi ja osion nimi ensin: sinfo -o "%P %G %l"  (muokkaa --partition ja --gres tarvittaessa)
#
# Signaalit: Slurm lähettää SIGUSR1:n 15 minuuttia ennen aikarajaa ja SIGTERM:n aikarajalla tai scancelissa.
# Palvelu käsittelee ne itse (scripts/serve.py), joten python käynnistetään exec:llä ja saa signaalit suoraan.
set -euo pipefail

F5_HOME=${F5_HOME:-$HOME/F5-FI-Jooseppi}
F5_ENV=${F5_ENV:-$F5_HOME/.env-lehmus}
VOIKKO_PREFIX=${VOIKKO_PREFIX:-$HOME/voikko}
STATE_DIR=${F5SERVE_STATE_DIR:-$HOME/f5fi-tila}
VOICES=${F5SERVE_VOICES:-$F5_HOME/slurm/voices.json}
KEYS=${F5SERVE_KEYS_FILE:-$STATE_DIR/avaimet.json}
WORKERS=${F5SERVE_WORKERS:-2}
MAX_SESSIONS=${F5SERVE_MAX_SESSIONS:-4}
IDLE_EXIT_S=${F5SERVE_IDLE_EXIT_S:-0}          # >0: sammu, kun ei käyttöä näin monta sekuntia (vapauttaa GPU:n)
RESUBMIT=${F5SERVE_RESUBMIT:-0}                # 1: jokainen työ tilaa seuraajansa, jolloin palvelu jatkuu viikosta toiseen
LIFETIME_S=${F5SERVE_LIFETIME_S:-604800}       # sama kuin --time sekunteina
OVERLAP_S=${F5SERVE_OVERLAP_S:-2700}           # seuraaja alkaa näin monta sekuntia ennen tämän päättymistä

for f in "$F5_ENV/bin/python" "$VOICES" "$KEYS"; do
  [ -e "$f" ] || { echo "puuttuu: $f (aja slurm/install.sh ja tee voices.json)"; exit 1; }
done
mkdir -p "$STATE_DIR"

export VOIKKO_LIB_DIR="$VOIKKO_PREFIX/lib" VOIKKO_DICT_DIR="$VOIKKO_PREFIX/lib/voikko"
export HF_HUB_OFFLINE=1 WANDB_MODE=disabled PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export OMP_NUM_THREADS=$(( ${SLURM_CPUS_PER_TASK:-4} / WORKERS > 0 ? ${SLURM_CPUS_PER_TASK:-4} / WORKERS : 1 ))
GPU_FRACTION=$("$F5_ENV/bin/python" -c "print(round(0.9 / $WORKERS, 3))")

echo "työ $SLURM_JOB_ID solmulla $(hostname): $WORKERS työläistä, $MAX_SESSIONS istuntoa, GPU: $(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader | head -1)"

if [ "$RESUBMIT" = 1 ] && [ ! -e "$STATE_DIR/STOP" ]; then
  # Seuraaja alkaa ennen tämän päättymistä ja ottaa osoitteen (current.json) heti kun on valmis; tämä tyhjenee itsestään.
  SCRIPT=$(scontrol show job "$SLURM_JOB_ID" | awk -F= '/^ *Command=/{print $2; exit}')
  NEXT=$(sbatch --parsable --begin="now+$((LIFETIME_S - OVERLAP_S))" "$SCRIPT")
  echo "seuraaja tilattu: työ $NEXT (pysäytä ketju: touch $STATE_DIR/STOP ja scancel --name=f5fi-puhe)"
fi

exec "$F5_ENV/bin/python" "$F5_HOME/scripts/serve.py" \
  --voices "$VOICES" --state-dir "$STATE_DIR" --keys-file "$KEYS" \
  --workers "$WORKERS" --max-sessions "$MAX_SESSIONS" --gpu-fraction "$GPU_FRACTION" \
  --idle-exit "$IDLE_EXIT_S" ${F5SERVE_PORT:+--port "$F5SERVE_PORT"}
