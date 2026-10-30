# llm-training — このセッションをローカルLLMに学習させる

Claude Code のセッション記録(JSONL)と、本リポジトリのドローンショー資料から学習用データを作り、
ローカルLLM(Qwen2.5 など)を LoRA 学習する一式。

| ファイル | 役割 |
|---|---|
| `make_dataset.py` | セッション記録 → `sft_dialogue.jsonl`(会話)/ `sft_tool_trajectories.jsonl`(ツール呼び出し軌跡)/ `knowledge_docs.jsonl`(資料)。メール・署名付きURL・セッションURLはマスク |
| `train_lora.py` | QLoRA 学習(既定 Qwen/Qwen2.5-7B-Instruct、VRAM 約10〜12GB。`--model Qwen/Qwen2.5-3B-Instruct` で軽量化)。`--merge` でベースに焼き込み |
| `export_to_ollama.sh` | マージ済みモデルを GGUF 化して Ollama に登録 |
| `quick_ollama_context.sh` | 学習せずに、会話と資料をシステムプロンプトに埋めた Ollama モデルを作る最短ルート |
| `dataset/knowledge_docs.jsonl` | 資料部分のみ生成済み(会話部分はお手元で生成) |

## 手順(お手元のPC)

```bash
# 1) 会話記録からデータセットを作る(記録は ~/.claude/projects/<project>/<session>.jsonl にある)
python make_dataset.py --jsonl ~/.claude/projects/<project>/<session>.jsonl --out dataset --docs ../drone-show-halloween-skull

# 2a) LoRA 学習(GPU 推奨)
pip install -r requirements.txt
python train_lora.py --data dataset --out out/lora --model Qwen/Qwen2.5-7B-Instruct --epochs 3
python train_lora.py --merge out/lora --out out/merged
./export_to_ollama.sh out/merged droneshow-assistant     # ollama run droneshow-assistant

# 2b) 学習せずに使う(GPU なしでも可)
./quick_ollama_context.sh dataset qwen2.5:7b droneshow-context
```

クラウド側では会話記録ファイルの読み出しが許可されないため、会話部分のデータセット生成は
お手元のPC(Remote Control 接続後でも可)で実行する。
