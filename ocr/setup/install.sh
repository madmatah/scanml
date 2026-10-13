#!/usr/bin/env bash
# One-shot installer for the OCR sandbox, run by the `ocr-setup` service.
#
# It runs inside a container that only sees /opt/sandbox (SANDBOX_DIR on the
# host). It has network access because it downloads Python packages and model
# weights; the runtime `ocr` service that later executes this code has none.
#
# Every step is idempotent (marker files), so the script can be re-run after a
# failure or to upgrade a single component (delete its marker / directory).
set -euo pipefail

SANDBOX=/opt/sandbox
LOG="$SANDBOX/setup.log"

PADDLE_WHEEL_URL="https://paddle-whl.cdn.bcebos.com/stable/cu126/paddlepaddle-gpu/paddlepaddle_gpu-3.2.1-cp312-cp312-linux_x86_64.whl"
PADDLEOCR_SPEC="paddleocr[doc-parser]==3.7.0"
VLLM_SPEC="vllm==0.31.0"
MODEL_REPO="PaddlePaddle/PaddleOCR-VL-1.6"
MODEL_REVISION="c5630abae1d940eafe0697512a0325494b02ab42"

export UV_CACHE_DIR="$SANDBOX/cache/uv"
export UV_LINK_MODE=copy
export HF_HOME="$SANDBOX/cache/huggingface"
export HF_HUB_DISABLE_TELEMETRY=1
export DO_NOT_TRACK=1
export PADDLE_PDX_CACHE_HOME="$SANDBOX/paddlex"
export PADDLE_PDX_MODEL_SOURCE=huggingface

mkdir -p "$SANDBOX/cache" "$SANDBOX/models"
exec > >(tee -a "$LOG") 2>&1
echo "=== ScanMyLib OCR sandbox setup — $(date -Is) ==="

step_done() { [[ -f "$SANDBOX/.done-$1" ]]; }
mark_done() { date -Is > "$SANDBOX/.done-$1"; }

# 1. PaddlePaddle + PaddleOCR (layout detection and the document-parsing pipeline).
#    Only the paddlepaddle-gpu wheel comes from the official Paddle CDN (it is not
#    published on PyPI); all its dependencies are resolved from PyPI.
if ! step_done venv-paddle; then
  echo "--- [1/4] venv-paddle"
  rm -rf "$SANDBOX/venv-paddle"
  uv venv --python /usr/local/bin/python3.12 "$SANDBOX/venv-paddle"
  uv pip install --python "$SANDBOX/venv-paddle/bin/python" \
    "paddlepaddle-gpu @ $PADDLE_WHEEL_URL" "$PADDLEOCR_SPEC" safetensors
  mark_done venv-paddle
fi

# 2. vLLM (fast inference server for the PaddleOCR-VL vision-language model).
if ! step_done venv-vllm; then
  echo "--- [2/4] venv-vllm"
  rm -rf "$SANDBOX/venv-vllm"
  uv venv --python /usr/local/bin/python3.12 "$SANDBOX/venv-vllm"
  uv pip install --python "$SANDBOX/venv-vllm/bin/python" "$VLLM_SPEC"
  mark_done venv-vllm
fi

# 3. PaddleOCR-VL-1.6 weights, pinned to a known Hugging Face commit.
if ! step_done model-vl; then
  echo "--- [3/4] $MODEL_REPO@$MODEL_REVISION"
  "$SANDBOX/venv-vllm/bin/python" - <<EOF
from huggingface_hub import snapshot_download
snapshot_download("$MODEL_REPO", revision="$MODEL_REVISION",
                  local_dir="$SANDBOX/models/PaddleOCR-VL-1.6")
EOF
  mark_done model-vl
fi

# 4. Auxiliary PaddleX models used by the pipeline (layout detection, page
#    orientation, page unwarping), pinned to known Hugging Face commits. They are
#    fetched with huggingface_hub only: no Paddle code ever runs with network.
if ! step_done models-paddlex; then
  echo "--- [4/4] PaddleX auxiliary models"
  "$SANDBOX/venv-vllm/bin/python" - <<EOF
from huggingface_hub import snapshot_download
for name, revision in {
    "PP-DocLayoutV3": "241f8bdfc77a7c7bee915a5057aaee58c235a8d3",
    "PP-LCNet_x1_0_doc_ori": "d3b95a6dff5fe8a94f2748e12b61cb26818a0df8",
    "UVDoc": "16c3f0ea9c2f0c6a57e24160f7eeaa7574613fa3",
}.items():
    snapshot_download(f"PaddlePaddle/{name}", revision=revision,
                      local_dir=f"$PADDLE_PDX_CACHE_HOME/official_models/{name}")
    print("downloaded", name, revision)
EOF
  mark_done models-paddlex
fi

# Manifest: what exactly is installed in the sandbox.
"$SANDBOX/venv-paddle/bin/python" - <<EOF
import json, importlib.metadata as md, subprocess, datetime, pathlib
def versions(py, pkgs):
    out = subprocess.run([py, "-c",
        "import importlib.metadata as m, json, sys; print(json.dumps({p: m.version(p) for p in sys.argv[1:]}))", *pkgs],
        capture_output=True, text=True, check=True).stdout
    return json.loads(out)
manifest = {
    "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
    "venv-paddle": versions("$SANDBOX/venv-paddle/bin/python", ["paddlepaddle-gpu", "paddleocr", "paddlex"]),
    "venv-vllm": versions("$SANDBOX/venv-vllm/bin/python", ["vllm", "torch", "transformers"]),
    "model": {"repo": "$MODEL_REPO", "revision": "$MODEL_REVISION"},
    "paddlex_models": sorted(p.name for p in pathlib.Path("$PADDLE_PDX_CACHE_HOME/official_models").iterdir()),
}
pathlib.Path("$SANDBOX/MANIFEST.json").write_text(json.dumps(manifest, indent=2))
print(json.dumps(manifest, indent=2))
EOF

# The venvs are full copies (UV_LINK_MODE=copy): download caches are not needed anymore.
rm -rf "$SANDBOX/cache"

echo "=== setup complete — $(date -Is) ==="
du -sh "$SANDBOX"/venv-paddle "$SANDBOX"/venv-vllm "$SANDBOX"/models "$SANDBOX"/paddlex 2>/dev/null || true
