#!/bin/bash
#SBATCH --job-name=f5fi-asennus
#SBATCH --partition=interactive
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=%x-%j.log
#
# Asennus laskentasolmulla (srun --pty ei toimi). Aja repositorion juuresta:
#   module load conda        # sbatch vie ympäristön mukanaan
#   sbatch slurm/install.sbatch
# Asetukset ympäristömuuttujilla kuten install.sh:ssa (F5_ENV, VOIKKO_PREFIX, PIP_EXTRA, ...). Osio ei tarvitse GPU:ta.
set -euo pipefail
export F5_HOME=${F5_HOME:-${SLURM_SUBMIT_DIR:?aja sbatch repositorion juuresta}}
[ -f "$F5_HOME/slurm/install.sh" ] || { echo "ei löydy: $F5_HOME/slurm/install.sh (aja sbatch repositorion juuresta tai aseta F5_HOME)"; exit 1; }
exec bash "$F5_HOME/slurm/install.sh"
