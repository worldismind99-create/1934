#!/usr/bin/env bash
# 学習済み(マージ済み)モデルを GGUF に変換して Ollama に登録する
#   前提: llama.cpp を clone 済み(LLAMA_CPP 環境変数でパス指定)、ollama インストール済み
#   使い方: ./export_to_ollama.sh out/merged droneshow-assistant
set -euo pipefail
MERGED=${1:-out/merged}
NAME=${2:-droneshow-assistant}
LLAMA_CPP=${LLAMA_CPP:-$HOME/llama.cpp}

python "$LLAMA_CPP/convert_hf_to_gguf.py" "$MERGED" --outtype q8_0 --outfile "$MERGED/model-q8_0.gguf"
cat > "$MERGED/Modelfile" <<EOF
FROM ./model-q8_0.gguf
PARAMETER temperature 0.4
PARAMETER num_ctx 8192
SYSTEM """あなたはBlenderでドローンライトショーのアニメーションを制作するアシスタントです。安全距離・速度・加速度の設計値を守り、スクリプトで再現可能なデータを作り、必ず検証してから納品します。"""
EOF
ollama create "$NAME" -f "$MERGED/Modelfile"
echo "done: ollama run $NAME"
