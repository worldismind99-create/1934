#!/usr/bin/env bash
# 学習せずに「このセッションの知識」をローカルLLMで使う最短ルート(RAG / システムプロンプト注入)
#   dataset/knowledge_docs.jsonl と sft_dialogue.jsonl を1本のコンテキスト文書にまとめ、
#   Ollama の Modelfile に埋め込む(ベースは qwen2.5:7b など日本語が使えるモデル)。
#   使い方: ./quick_ollama_context.sh dataset qwen2.5:7b droneshow-context
set -euo pipefail
DATA=${1:-dataset}
BASE=${2:-qwen2.5:7b}
NAME=${3:-droneshow-context}
python3 - "$DATA" <<'EOF'
import json, sys, os
d = sys.argv[1]
parts = []
for line in open(os.path.join(d, "sft_dialogue.jsonl"), encoding="utf-8"):
    r = json.loads(line)
    u = r["messages"][-2]["content"]; a = r["messages"][-1]["content"]
    parts.append(f"### 過去のやり取り\nユーザー: {u[:1500]}\nアシスタント: {a[:3000]}\n")
if os.path.exists(os.path.join(d, "knowledge_docs.jsonl")):
    for line in open(os.path.join(d, "knowledge_docs.jsonl"), encoding="utf-8"):
        doc = json.loads(line)
        if doc["source"].endswith(".md"):
            parts.append(f"### 文書 {doc['source']}\n{doc['text'][:8000]}\n")
ctx = "\n".join(parts)[:60000]
open(os.path.join(d, "context.txt"), "w", encoding="utf-8").write(ctx)
print("context chars:", len(ctx))
EOF
python3 - "$DATA" "$BASE" <<'EOF'
import sys, os
d, base = sys.argv[1], sys.argv[2]
ctx = open(os.path.join(d, "context.txt"), encoding="utf-8").read().replace('"""', "'''")
open(os.path.join(d, "Modelfile"), "w", encoding="utf-8").write(
    f'FROM {base}\nPARAMETER num_ctx 32768\nPARAMETER temperature 0.4\nSYSTEM """あなたはBlenderでドローンライトショーのアニメーションを制作するアシスタントです。以下はこれまでの制作セッションの記録と資料です。これを前提知識として回答してください。\n\n{ctx}\n"""\n')
EOF
ollama create "$NAME" -f "$DATA/Modelfile"
echo "done: ollama run $NAME"
