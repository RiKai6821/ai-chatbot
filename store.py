"""会话持久化（SQLite，零额外依赖）。

服务端的会话记忆默认放在内存 dict 里，进程一重启就全丢。这个模块把每个会话的
消息历史以 JSON 存进一个本地 sqlite 文件，重启后还能接着聊。

表结构：sessions(ns, session_id, messages_json)，主键 (ns, session_id)。
  ns         区分用途，如 "chat" / "agent"，避免不同人设互相覆盖。
  messages   就是发给模型的那个 messages 列表（含 system / user / assistant / tool）。

用法：
    import store
    store.init()
    msgs = store.load("chat", "default")          # 没有则返回 None
    store.save("chat", "default", msgs)
"""
import os
import json
import sqlite3
import threading

# 可写数据目录：默认当前目录；容器里设 XZ_DATA_DIR 指向挂载卷以持久化。
DATA_DIR = os.getenv("XZ_DATA_DIR", ".")
DB_PATH = os.path.join(DATA_DIR, "sessions.db")
_lock = threading.Lock()      # sqlite 连接非线程安全，FastAPI 多线程下加锁最稳妥
_conn: sqlite3.Connection | None = None


def init(db_path: str = DB_PATH) -> None:
    """建表并打开连接。进程启动时调用一次。"""
    global _conn
    # 确保父目录存在（XZ_DATA_DIR 指向新目录时；":memory:" 等无目录则跳过）
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    _conn = sqlite3.connect(db_path, check_same_thread=False)
    _conn.execute(
        "CREATE TABLE IF NOT EXISTS sessions ("
        "  ns TEXT NOT NULL,"
        "  session_id TEXT NOT NULL,"
        "  messages_json TEXT NOT NULL,"
        "  PRIMARY KEY (ns, session_id)"
        ")"
    )
    _conn.commit()


def load(ns: str, session_id: str) -> list | None:
    """读取某会话的消息历史；不存在返回 None。"""
    if _conn is None:
        return None
    with _lock:
        row = _conn.execute(
            "SELECT messages_json FROM sessions WHERE ns=? AND session_id=?",
            (ns, session_id),
        ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return None


def save(ns: str, session_id: str, messages: list) -> None:
    """写入/覆盖某会话的消息历史。"""
    if _conn is None:
        return
    data = json.dumps(messages, ensure_ascii=False)
    with _lock:
        _conn.execute(
            "INSERT INTO sessions (ns, session_id, messages_json) VALUES (?,?,?) "
            "ON CONFLICT(ns, session_id) DO UPDATE SET messages_json=excluded.messages_json",
            (ns, session_id, data),
        )
        _conn.commit()
