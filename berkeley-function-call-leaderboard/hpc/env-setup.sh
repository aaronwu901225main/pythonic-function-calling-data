#!/usr/bin/env bash
# 通用環境安裝腳本：在 headnode 執行一次即可。
# - 建立 conda env (gorilla-hpc)
# - 安裝 PyTorch (CUDA 11.8) 與關鍵依賴
# - 安裝本專案所需的 Python 套件（BFCL/transformers 等）

set -euo pipefail

# 1) 建議把暫存改到 $HOME/tmp，避免 /tmp 爆滿
export TMPDIR="$HOME/tmp"
mkdir -p "$TMPDIR"

# 2) 載入 Anaconda（若集群環境支援 module）
if command -v module &>/dev/null; then
  module purge || true
  module load anaconda || true
fi

# 3) 建立/啟用 conda env
ENV_NAME="BFCL"
PY_VER="3.11"

if ! conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  conda create -y -n "$ENV_NAME" python="$PY_VER"
fi

# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"

# 4) 安裝 PyTorch + CUDA 11.8（與 vLLM/sglang/transformers 相容性佳）
conda install -y -c pytorch -c nvidia pytorch pytorch-cuda=11.8 torchvision torchaudio

# 5) 安裝通用 Python 依賴
pip install --upgrade pip

# BFCL 主套件（CLI: bfcl）
pushd "$(dirname "$0")/.." >/dev/null
pip install -e "./berkeley-function-call-leaderboard"
popd >/dev/null

# Transformers + 其他工具（供 gorilla_eval / raft 等使用）
pip install transformers==4.42.4 accelerate datasets sentencepiece sacremoses sacrebleu
pip install python-dotenv typer tabulate pandas numpy coloredlogs pyyaml tqdm rich

# RAFT 常見依賴補強
pip install openai==1.56.1 httpx==0.27.2

# 若需要 OSS 本地推論（vLLM 或 sglang），可解除以下安裝：
# pip install 'bfcl_eval[oss_eval_vllm]'
# 或
# pip install 'bfcl_eval[oss_eval_sglang]'

cat <<EOF
[OK] Conda env '$ENV_NAME' 準備完成。
- 啟用：  conda activate $ENV_NAME
- Python： $(python --version)
- PyTorch：$(python - <<PY
import torch, sys
print(f"torch={torch.__version__}, cuda={torch.version.cuda}, is_available={torch.cuda.is_available()}")
PY
)
EOF
