#!/usr/bin/env bash
# Asennus ilman root-oikeuksia: Python 3.13 -ympäristö, Voikko (rakennetaan kotihakemistoon) ja avaimet.
#
#   module load conda            # tai PYTHON=/polku/python3.13, jos sellainen on
#   sbatch slurm/install.sbatch  # suositus (srun --pty ei toimi); tai suoraan: bash slurm/install.sh
#
# Asetukset ympäristömuuttujilla (oletus suluissa):
#   F5_ENV (repo/.env-lehmus)  VOIKKO_PREFIX (~/voikko)  F5SERVE_STATE_DIR (~/.f5-palvelu)  PYTHON  CONDA_MODULE (conda)
#   PIP_EXTRA        lisävalitsimet pip/uv:lle. PyPI:n torch on CUDA 13 -käännös; jos ajuri on vanhempi, hae CUDA 12 -pyörä:
#                    PIP_EXTRA="--extra-index-url https://download.pytorch.org/whl/cu126" (katso docs/palvelin-lehmus.md)
#   VOIKKO_SRC_TARBALL, VOIKKO_FI_DEB   paikalliset tiedostot, jos klusteri ei tavoita archive.ubuntu.com-palvelinta
#   RUN_TESTS=0      ohita yksikkötestit lopuksi
set -euo pipefail

F5_HOME=${F5_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
F5_ENV=${F5_ENV:-$F5_HOME/.env-lehmus}
VOIKKO_PREFIX=${VOIKKO_PREFIX:-$HOME/voikko}
STATE_DIR=${F5SERVE_STATE_DIR:-$HOME/.f5-palvelu}
CONDA_MODULE=${CONDA_MODULE:-conda}
PIP_EXTRA=${PIP_EXTRA:-}
RUN_TESTS=${RUN_TESTS:-1}
LIBVOIKKO_URL=${LIBVOIKKO_URL:-http://archive.ubuntu.com/ubuntu/pool/main/libv/libvoikko/libvoikko_4.3.2.orig.tar.gz}
VOIKKO_FI_URL=${VOIKKO_FI_URL:-http://archive.ubuntu.com/ubuntu/pool/main/v/voikko-fi/voikko-fi_2.5-1build1_amd64.deb}
WORK=$(mktemp -d "${TMPDIR:-/tmp}/f5fi-install.XXXXXX")
trap 'rm -rf "$WORK"' EXIT
say() { printf '\n== %s\n' "$*"; }

say "1/4 Python 3.13 -ympäristö: $F5_ENV"
if [ ! -x "$F5_ENV/bin/python" ]; then
  if [ -n "${PYTHON:-}" ]; then
    "$PYTHON" -m venv "$F5_ENV"
  else
    if ! command -v conda >/dev/null 2>&1 && type module >/dev/null 2>&1; then
      set +u; module load "$CONDA_MODULE"; set -u
    fi
    command -v conda >/dev/null 2>&1 || { echo "conda ei löydy. Aja ensin: module load $CONDA_MODULE (tai anna PYTHON=/polku/python3.13)"; exit 1; }
    conda create -y -p "$F5_ENV" -c conda-forge --override-channels python=3.13 pip
  fi
fi
"$F5_ENV/bin/python" -c 'import sys; assert sys.version_info[:2] == (3, 13), sys.version; print("Python", sys.version.split()[0])'

say "2/4 Python-paketit (ilman mlx-paketteja, ne ovat vain Macille)"
grep -viE '^(mlx|mlx-metal|mlx-whisper|libvoikko)==' "$F5_HOME/requirements-lock.txt" > "$WORK/lock.txt"
LIBVOIKKO_PIN=$(grep -iE '^libvoikko==' "$F5_HOME/requirements-lock.txt")
# shellcheck disable=SC2086  # PIP_EXTRA is meant to split into words
if command -v uv >/dev/null 2>&1; then
  UV_EXTRA=""; [ -n "$PIP_EXTRA" ] && UV_EXTRA="--index-strategy unsafe-best-match"  # uv prefers PyPI unless told otherwise
  uv pip install --python "$F5_ENV/bin/python" $UV_EXTRA $PIP_EXTRA -r "$WORK/lock.txt" "$LIBVOIKKO_PIN" zstandard
else
  "$F5_ENV/bin/python" -m pip install $PIP_EXTRA -r "$WORK/lock.txt" "$LIBVOIKKO_PIN" zstandard
fi

say "3/4 Voikko: kirjasto lähdekoodista ja sanakirja Ubuntun paketista, kumpikin hakemistoon $VOIKKO_PREFIX"
if [ ! -e "$VOIKKO_PREFIX/lib/libvoikko.so.1" ] || [ ! -d "$VOIKKO_PREFIX/lib/voikko/5/mor-standard" ]; then
  command -v g++ >/dev/null 2>&1 && command -v make >/dev/null 2>&1 || { echo "g++ ja make tarvitaan (esim. module load gcc)"; exit 1; }
  fetch() { if [ -n "${3:-}" ] && [ -f "$3" ]; then cp "$3" "$2"; else curl -fsSL --retry 3 -o "$2" "$1"; fi; }
  fetch "$LIBVOIKKO_URL" "$WORK/libvoikko.tar.gz" "${VOIKKO_SRC_TARBALL:-}"
  fetch "$VOIKKO_FI_URL" "$WORK/voikko-fi.deb" "${VOIKKO_FI_DEB:-}"
  mkdir -p "$WORK/src" "$VOIKKO_PREFIX"
  tar xzf "$WORK/libvoikko.tar.gz" -C "$WORK/src"
  (
    cd "$WORK"/src/libvoikko-*/
    ./configure --prefix="$VOIKKO_PREFIX" --disable-hfst --disable-static --disable-testtools \
                --with-dictionary-path="$VOIKKO_PREFIX/lib/voikko" > "$WORK/configure.log" 2>&1 || { tail -20 "$WORK/configure.log"; exit 1; }
    make -j"${JOBS:-4}" > "$WORK/make.log" 2>&1 || { tail -20 "$WORK/make.log"; exit 1; }
    make install > "$WORK/install.log" 2>&1 || { tail -20 "$WORK/install.log"; exit 1; }
  )
  "$F5_ENV/bin/python" "$F5_HOME/slurm/extract_deb_dir.py" "$WORK/voikko-fi.deb" usr/lib/voikko "$VOIKKO_PREFIX/lib"
fi
export VOIKKO_LIB_DIR="$VOIKKO_PREFIX/lib" VOIKKO_DICT_DIR="$VOIKKO_PREFIX/lib/voikko"
"$F5_ENV/bin/python" -I - "$F5_HOME" <<'PY'
import sys
sys.path.insert(0, sys.argv[1] + "/scripts")
import rajageminaatio
out = rajageminaatio.mark_compounds(rajageminaatio.mark("Tervetuloa meille, voisitko selittää sen?"))
print(out)
assert rajageminaatio._analyzer() is not None, "Voikko ei lataudu"
assert "tervettuloa" in out.lower() and "selittääs" in out, "Voikko toimii, mutta kahdennussäännöt eivät: " + out
PY

say "4/4 Tilakansio ja erä-avain omille ajoille: $STATE_DIR"
mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"
if [ ! -e "$STATE_DIR/avaimet.json" ]; then
  "$F5_ENV/bin/python" -I - "$STATE_DIR/avaimet.json" <<'PY'
import json, os, secrets, sys
fd = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as f:
    json.dump({"batch": secrets.token_urlsafe(32)}, f)  # Rooliharjoittelun avaimen (avain) palvelu luo itse joka käynnistyksessä
print("erä-avain luotu:", sys.argv[1])
PY
fi
"$F5_ENV/bin/python" -I -c 'import torch, f5_tts, fastapi, uvicorn; print("torch", torch.__version__, "CUDA-käännös", torch.version.cuda)'
if [ "$RUN_TESTS" = 1 ]; then
  (cd "$F5_HOME" && "$F5_ENV/bin/python" -m unittest discover tests 2>&1 | tail -4)
fi
say "Valmis. Seuraavaksi: kopioi painot ja viiteäänitteet, tee slurm/voices.json ja aja: sbatch slurm/serve.sbatch"
echo "Ympäristö: $F5_ENV   Voikko: $VOIKKO_PREFIX   Tila: $STATE_DIR"
