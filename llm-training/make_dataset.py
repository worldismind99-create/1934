# -*- coding: utf-8 -*-
"""
Claude Code セッション記録(JSONL)から、ローカルLLMの学習用データセットを作る。

入力: ~/.claude/projects/<project>/<session>.jsonl(Claude Code が保存する会話ログ)
出力(--out で指定したフォルダ):
  sft_dialogue.jsonl          ユーザー発話 → アシスタントの最終回答(直前の会話を文脈として付ける)
  sft_tool_trajectories.jsonl ツール呼び出し込みの行動軌跡(エージェント学習用。tool_calls / tool ロール形式)
  knowledge_docs.jsonl        README・スクリプトなどの「知識」ドキュメント(継続事前学習 / RAG 用)
  stats.json                  件数などの統計
個人情報(メールアドレス・署名付きURL・セッションURL)は正規表現でマスクする。

使い方:
  python make_dataset.py --jsonl <session.jsonl> --out dataset --docs <dir1> <dir2> ...
"""
import argparse
import json
import os
import re
import glob

SYSTEM_PROMPT = ("あなたはBlenderでドローンライトショーのアニメーションを制作するアシスタントです。"
                 "安全距離・速度・加速度の設計値を守り、スクリプトで再現可能なデータを作り、必ず検証してから納品します。")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SIGNED_URL_RE = re.compile(r"https?://\S*X-Amz-Signature=\S+")
SESSION_URL_RE = re.compile(r"https://claude\.ai/code/session_\S+")
TOKEN_RE = re.compile(r"(X-Amz-Credential|X-Amz-Signature)=[^&\s\"]+")
MAX_TOOL_INPUT = 6000      # ツール入力(コード等)の保持上限[文字]
MAX_TOOL_RESULT = 3000     # ツール結果の保持上限[文字]


def scrub(text):
    if not isinstance(text, str):
        return text
    text = EMAIL_RE.sub("<email>", text)
    text = SIGNED_URL_RE.sub("<signed-url>", text)
    text = SESSION_URL_RE.sub("<session-url>", text)
    text = TOKEN_RE.sub(r"\1=<redacted>", text)
    return text


def clip(text, n):
    if text is None:
        return ""
    text = str(text)
    return text if len(text) <= n else text[:n] + f"\n...[truncated {len(text) - n} chars]"


def text_of_blocks(content):
    """content(str or list of blocks) → 表示テキスト(thinking/画像は除外)"""
    if isinstance(content, str):
        return content
    out = []
    for b in content or []:
        if b.get("type") == "text":
            out.append(b.get("text", ""))
    return "\n".join(out).strip()


def load_turns(path):
    turns = []  # dict(role, text, tool_calls, tool_results)
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("type") not in ("user", "assistant"):
                continue
            m = d.get("message") or {}
            role = m.get("role")
            content = m.get("content")
            if role == "user":
                if isinstance(content, list):
                    results = [b for b in content if b.get("type") == "tool_result"]
                    txt = text_of_blocks(content)
                    if results:
                        turns.append({"role": "tool", "results": results})
                    if txt:
                        turns.append({"role": "user", "text": txt})
                else:
                    if content:
                        turns.append({"role": "user", "text": content})
            elif role == "assistant":
                txt = text_of_blocks(content)
                calls = [b for b in (content if isinstance(content, list) else []) if b.get("type") == "tool_use"]
                turns.append({"role": "assistant", "text": txt, "tool_calls": calls})
    return turns


def is_system_notice(text):
    t = text.strip()
    return (t.startswith("<system-reminder>") or t.startswith("[Request interrupted") or
            "SYSTEM NOTIFICATION" in t[:200] or t.startswith("Stop hook feedback") or
            t.startswith("This session's worker") or t.startswith("<task-notification>"))


def strip_reminders(text):
    text = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.S)
    text = re.sub(r"\[SYSTEM NOTIFICATION.*?(?=\n\n|\Z)", "", text, flags=re.S)
    return text.strip()


def build_dialogue(turns, context_turns=6):
    """ユーザー発話ごとに、その後に来るアシスタントの最終テキスト回答をペアにする"""
    samples = []
    history = []
    i = 0
    while i < len(turns):
        t = turns[i]
        if t["role"] == "user":
            utext = strip_reminders(t["text"])
            if not utext or is_system_notice(t["text"]):
                i += 1
                continue
            j = i + 1
            final = ""
            while j < len(turns) and not (turns[j]["role"] == "user" and strip_reminders(turns[j]["text"]) and not is_system_notice(turns[j]["text"])):
                if turns[j]["role"] == "assistant" and turns[j]["text"]:
                    final = turns[j]["text"]
                j += 1
            if final:
                msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
                for h in history[-context_turns:]:
                    msgs.append(h)
                msgs.append({"role": "user", "content": scrub(utext)})
                msgs.append({"role": "assistant", "content": scrub(final)})
                samples.append({"messages": msgs})
                history.append({"role": "user", "content": scrub(utext)})
                history.append({"role": "assistant", "content": scrub(final)})
            i = j
        else:
            i += 1
    return samples


def build_trajectories(turns, max_msgs=60):
    """ツール呼び出し込みの軌跡。ユーザー発話単位でエピソードに分け、長いものは max_msgs で分割"""
    episodes = []
    cur = None
    for t in turns:
        if t["role"] == "user":
            utext = strip_reminders(t["text"])
            if not utext or is_system_notice(t["text"]):
                continue
            if cur:
                episodes.append(cur)
            cur = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": scrub(utext)}]
        elif cur is not None and t["role"] == "assistant":
            msg = {"role": "assistant", "content": scrub(t["text"])}
            if t["tool_calls"]:
                msg["tool_calls"] = [{"id": c.get("id"), "type": "function",
                                      "function": {"name": c.get("name"),
                                                   "arguments": scrub(clip(json.dumps(c.get("input"), ensure_ascii=False), MAX_TOOL_INPUT))}}
                                     for c in t["tool_calls"]]
            cur.append(msg)
        elif cur is not None and t["role"] == "tool":
            for r in t["results"]:
                c = r.get("content")
                if isinstance(c, list):
                    c = "\n".join(b.get("text", "") for b in c if b.get("type") == "text")
                cur.append({"role": "tool", "tool_call_id": r.get("tool_use_id"), "content": scrub(clip(c, MAX_TOOL_RESULT))})
    if cur:
        episodes.append(cur)
    samples = []
    for ep in episodes:
        head = ep[:2]
        body = ep[2:]
        for k in range(0, max(1, len(body)), max_msgs):
            chunk = body[k:k + max_msgs]
            if chunk:
                samples.append({"messages": head + chunk})
    return samples


def build_docs(doc_dirs, exts=(".md", ".py", ".json", ".txt")):
    docs = []
    for d in doc_dirs:
        for p in sorted(glob.glob(os.path.join(d, "**", "*"), recursive=True)):
            if os.path.isfile(p) and p.endswith(exts) and os.path.getsize(p) < 400_000 and "video_frames" not in p:
                try:
                    txt = open(p, encoding="utf-8").read()
                except Exception:
                    continue
                docs.append({"source": os.path.relpath(p, d), "text": scrub(txt)})
    return docs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--out", default="dataset")
    ap.add_argument("--docs", nargs="*", default=[])
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    turns = load_turns(a.jsonl)
    dialogue = build_dialogue(turns)
    traj = build_trajectories(turns)
    docs = build_docs(a.docs)
    for name, rows in (("sft_dialogue.jsonl", dialogue), ("sft_tool_trajectories.jsonl", traj), ("knowledge_docs.jsonl", docs)):
        with open(os.path.join(a.out, name), "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    stats = {"turns": len(turns), "dialogue_samples": len(dialogue), "trajectory_samples": len(traj),
             "knowledge_docs": len(docs),
             "dialogue_chars": sum(len(m["content"]) for s in dialogue for m in s["messages"]),
             "trajectory_chars": sum(len(json.dumps(s, ensure_ascii=False)) for s in traj),
             "docs_chars": sum(len(d["text"]) for d in docs)}
    with open(os.path.join(a.out, "stats.json"), "w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=2)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
