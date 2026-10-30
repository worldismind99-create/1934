# -*- coding: utf-8 -*-
"""
ローカルLLMのLoRA(QLoRA)学習スクリプト — このセッションのデータセット用。

対象: Hugging Face の instruct モデル(既定: Qwen/Qwen2.5-7B-Instruct。日本語・コード両対応)
      VRAM 目安: 7B を 4bit QLoRA で約 10〜12GB / 3B なら約 6GB / 1.5B なら約 4GB
使い方:
  pip install -r requirements.txt
  python train_lora.py --data dataset --out out/lora --model Qwen/Qwen2.5-7B-Instruct --epochs 3
  # 小さいGPUなら: --model Qwen/Qwen2.5-3B-Instruct  /  CPUのみなら --model Qwen/Qwen2.5-0.5B-Instruct --no-4bit
学習後:
  python train_lora.py --merge out/lora --out out/merged      # LoRAをベースに焼き込み(GGUF化・Ollama登録用)
"""
import argparse
import json
import os
import glob

import torch
from datasets import Dataset
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import LoraConfig, PeftModel, prepare_model_for_kbit_training
from trl import SFTTrainer, SFTConfig


def load_rows(data_dir, use_trajectories=True, use_docs=True):
    rows = []
    for name in ["sft_dialogue.jsonl"] + (["sft_tool_trajectories.jsonl"] if use_trajectories else []):
        p = os.path.join(data_dir, name)
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                r = json.loads(line)
                # tool_calls / tool ロールは chat template が対応していないモデルもあるのでテキスト化して保持
                msgs = []
                for m in r["messages"]:
                    c = m.get("content") or ""
                    if m.get("tool_calls"):
                        c += "\n\n<tool_calls>\n" + "\n".join(
                            f"{t['function']['name']}({t['function']['arguments']})" for t in m["tool_calls"]) + "\n</tool_calls>"
                    role = "user" if m["role"] == "tool" else m["role"]
                    if m["role"] == "tool":
                        c = "<tool_result>\n" + c + "\n</tool_result>"
                    msgs.append({"role": role, "content": c})
                rows.append({"messages": msgs})
    if use_docs:
        p = os.path.join(data_dir, "knowledge_docs.jsonl")
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                d = json.loads(line)
                # 文書は「この文書の内容を説明して」→本文 という形で学習させる(簡易な継続事前学習)
                rows.append({"messages": [
                    {"role": "user", "content": f"ファイル {d['source']} の内容をそのまま示してください。"},
                    {"role": "assistant", "content": d["text"][:12000]}]})
    return rows


def train(a):
    tok = AutoTokenizer.from_pretrained(a.model, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    quant = None
    if not a.no_4bit and torch.cuda.is_available():
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                   bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    model = AutoModelForCausalLM.from_pretrained(
        a.model, quantization_config=quant, device_map="auto" if torch.cuda.is_available() else None,
        torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32, trust_remote_code=True)
    if quant is not None:
        model = prepare_model_for_kbit_training(model)
    lora = LoraConfig(r=a.rank, lora_alpha=a.rank * 2, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])
    rows = load_rows(a.data, use_trajectories=not a.no_trajectories, use_docs=not a.no_docs)
    print(f"samples: {len(rows)}")
    ds = Dataset.from_list(rows)
    cfg = SFTConfig(output_dir=a.out, num_train_epochs=a.epochs, per_device_train_batch_size=a.batch,
                    gradient_accumulation_steps=a.grad_accum, learning_rate=a.lr, lr_scheduler_type="cosine",
                    warmup_ratio=0.05, logging_steps=5, save_strategy="epoch", bf16=torch.cuda.is_available(),
                    max_length=a.max_len, packing=False, gradient_checkpointing=True, report_to="none")
    trainer = SFTTrainer(model=model, args=cfg, train_dataset=ds, processing_class=tok, peft_config=lora)
    trainer.train()
    trainer.save_model(a.out)
    tok.save_pretrained(a.out)
    print("saved LoRA adapter to", a.out)


def merge(a):
    tok = AutoTokenizer.from_pretrained(a.merge)
    base_name = json.load(open(os.path.join(a.merge, "adapter_config.json")))["base_model_name_or_path"]
    base = AutoModelForCausalLM.from_pretrained(base_name, torch_dtype=torch.bfloat16, trust_remote_code=True)
    model = PeftModel.from_pretrained(base, a.merge).merge_and_unload()
    model.save_pretrained(a.out, safe_serialization=True)
    tok.save_pretrained(a.out)
    print("merged model saved to", a.out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="dataset")
    ap.add_argument("--out", default="out/lora")
    ap.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--epochs", type=float, default=3)
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--max-len", type=int, default=4096)
    ap.add_argument("--no-4bit", action="store_true")
    ap.add_argument("--no-trajectories", action="store_true", help="ツール軌跡を使わない(会話のみ)")
    ap.add_argument("--no-docs", action="store_true", help="知識ドキュメントを使わない")
    ap.add_argument("--merge", help="LoRAフォルダを指定するとベースに焼き込んで --out に保存")
    a = ap.parse_args()
    if a.merge:
        merge(a)
    else:
        train(a)
