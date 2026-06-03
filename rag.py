"""RAG（检索增强生成）：给小智接一个私有知识库。

流程：知识文档 → 切块 → 向量化(embedding) → 存索引 → 查询时向量检索最相关的块。
让模型"先查资料再回答"，而不是凭记忆瞎编。配合 tools.py 暴露成一个工具，
模型在 /agent 里会按需调用。

设计取舍（刻意轻量、无重型依赖）：
- 向量化：复用项目已有的 DashScope（OpenAI 兼容）text-embedding-v3。
- 向量库：纯 Python 余弦相似度 + 一个 JSON 索引缓存文件，不引入 faiss/chroma/numpy。
  知识库只有几十个块，纯 Python 足够快；要扩到上万条再换专用向量库。

命令行：
    python rag.py build          # 重建索引（知识库变了就跑一次）
    python rag.py "保修多久"      # 试检索
"""
import os
import sys
import json
import math
import glob
import hashlib

import config  # 自动加载 .env
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

KNOWLEDGE_DIR = "knowledge"
INDEX_PATH = "rag_index.json"
EMBED_MODEL = "text-embedding-v3"
EMBED_BATCH = 10                 # DashScope 单次 embedding 输入条数上限，保守取 10
CHUNK_MAX = 400                  # 每块最大字符数


# ── 切块 ──────────────────────────────────────────────────
def _split_doc(text: str) -> list[str]:
    """按空行分段；过长的段再按句号切，控制每块大小。"""
    chunks = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if len(para) <= CHUNK_MAX:
            chunks.append(para)
        else:
            buf = ""
            for sent in para.replace("。", "。\n").split("\n"):
                if len(buf) + len(sent) > CHUNK_MAX and buf:
                    chunks.append(buf.strip())
                    buf = ""
                buf += sent
            if buf.strip():
                chunks.append(buf.strip())
    return chunks


def _load_chunks() -> list[dict]:
    """读 knowledge/ 下所有 .md/.txt，切块，带上来源文件名。"""
    items = []
    for path in sorted(glob.glob(os.path.join(KNOWLEDGE_DIR, "*.md")) +
                       glob.glob(os.path.join(KNOWLEDGE_DIR, "*.txt"))):
        source = os.path.basename(path)
        with open(path, encoding="utf-8") as f:
            for ch in _split_doc(f.read()):
                items.append({"text": ch, "source": source})
    return items


def _knowledge_hash() -> str:
    """知识库内容指纹，用于判断是否需要重建索引。"""
    h = hashlib.sha256()
    for path in sorted(glob.glob(os.path.join(KNOWLEDGE_DIR, "*.md")) +
                       glob.glob(os.path.join(KNOWLEDGE_DIR, "*.txt"))):
        with open(path, "rb") as f:
            h.update(os.path.basename(path).encode())
            h.update(f.read())
    return h.hexdigest()


# ── 向量化 ────────────────────────────────────────────────
def _embed(texts: list[str]) -> list[list[float]]:
    """批量向量化，返回每段的 embedding。"""
    out = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i:i + EMBED_BATCH]
        resp = client.embeddings.create(model=EMBED_MODEL, input=batch)
        out.extend(d.embedding for d in resp.data)
    return out


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb + 1e-9)


# ── 索引 ──────────────────────────────────────────────────
def build_index() -> dict:
    """重建索引并写入 INDEX_PATH。"""
    chunks = _load_chunks()
    if not chunks:
        raise SystemExit(f"{KNOWLEDGE_DIR}/ 下没有找到知识文档（.md/.txt）")
    print(f"切出 {len(chunks)} 个知识块，正在向量化…")
    embs = _embed([c["text"] for c in chunks])
    for c, e in zip(chunks, embs):
        c["embedding"] = e
    index = {"model": EMBED_MODEL, "hash": _knowledge_hash(), "chunks": chunks}
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
    print(f"索引已建好 → {INDEX_PATH}")
    return index


_cache = None


def _get_index() -> dict:
    """加载索引；若不存在或知识库变了，自动重建。"""
    global _cache
    if _cache is not None:
        return _cache
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, encoding="utf-8") as f:
            idx = json.load(f)
        if idx.get("hash") == _knowledge_hash() and idx.get("model") == EMBED_MODEL:
            _cache = idx
            return idx
    _cache = build_index()
    return _cache


# ── 检索 ──────────────────────────────────────────────────
def search(query: str, k: int = 3) -> list[dict]:
    """返回与 query 最相关的 k 个知识块：[{text, source, score}]。"""
    idx = _get_index()
    qv = _embed([query])[0]
    scored = [
        {"text": c["text"], "source": c["source"], "score": _cosine(qv, c["embedding"])}
        for c in idx["chunks"]
    ]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:k]


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "build":
        build_index()
    elif len(sys.argv) >= 2:
        q = " ".join(sys.argv[1:])
        for i, r in enumerate(search(q), 1):
            print(f"\n[{i}] 相关度={r['score']:.3f}  来源={r['source']}")
            print(r["text"])
    else:
        print(__doc__)
