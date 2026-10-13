"""طبقة قاعدة البيانات (SQLite) لتطبيق التواصل الاجتماعي."""

import hashlib
import hmac
import os
import sqlite3
from datetime import datetime

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "social.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    full_name     TEXT    NOT NULL,
    bio           TEXT    NOT NULL DEFAULT '',
    password_hash TEXT    NOT NULL,
    salt          TEXT    NOT NULL,
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content    TEXT    NOT NULL,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS likes (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, post_id)
);

CREATE TABLE IF NOT EXISTS comments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id    INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content    TEXT    NOT NULL,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS follows (
    follower_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    followed_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (follower_id, followed_id),
    CHECK (follower_id <> followed_id)
);

CREATE INDEX IF NOT EXISTS idx_posts_user ON posts(user_id);
CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id);
"""

POST_SELECT = """
SELECT p.id, p.user_id, p.content, p.created_at,
       u.username, u.full_name,
       (SELECT COUNT(*) FROM likes l WHERE l.post_id = p.id)    AS like_count,
       (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id) AS comment_count,
       EXISTS(SELECT 1 FROM likes l WHERE l.post_id = p.id AND l.user_id = ?) AS liked
FROM posts p
JOIN users u ON u.id = p.user_id
"""


class DatabaseError(Exception):
    """خطأ برسالة مفهومة للمستخدم."""


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()


class Database:
    def __init__(self, path=DEFAULT_DB_PATH):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    # ---------- المستخدمون ----------

    def register(self, username, full_name, password):
        username = username.strip()
        full_name = full_name.strip()
        if len(username) < 3 or not username.replace("_", "").isalnum():
            raise DatabaseError("اسم المستخدم يجب أن يكون 3 أحرف على الأقل (حروف وأرقام و _ فقط)")
        if not full_name:
            raise DatabaseError("الرجاء إدخال الاسم الكامل")
        if len(password) < 6:
            raise DatabaseError("كلمة المرور يجب أن تكون 6 أحرف على الأقل")
        salt = os.urandom(16).hex()
        try:
            cur = self.conn.execute(
                "INSERT INTO users (username, full_name, password_hash, salt, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (username, full_name, _hash_password(password, salt), salt, _now()),
            )
        except sqlite3.IntegrityError:
            raise DatabaseError("اسم المستخدم مستخدم مسبقاً") from None
        self.conn.commit()
        return self.get_user(cur.lastrowid)

    def login(self, username, password):
        row = self.conn.execute(
            "SELECT * FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
        if row is None or not hmac.compare_digest(
            row["password_hash"], _hash_password(password, row["salt"])
        ):
            raise DatabaseError("اسم المستخدم أو كلمة المرور غير صحيحة")
        return self.get_user(row["id"])

    def get_user(self, user_id):
        row = self.conn.execute(
            """
            SELECT id, username, full_name, bio, created_at,
                   (SELECT COUNT(*) FROM posts   WHERE user_id = u.id)     AS post_count,
                   (SELECT COUNT(*) FROM follows WHERE followed_id = u.id) AS followers,
                   (SELECT COUNT(*) FROM follows WHERE follower_id = u.id) AS following
            FROM users u WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
        return dict(row) if row else None

    def update_profile(self, user_id, full_name, bio):
        full_name = full_name.strip()
        if not full_name:
            raise DatabaseError("الاسم الكامل لا يمكن أن يكون فارغاً")
        self.conn.execute(
            "UPDATE users SET full_name = ?, bio = ? WHERE id = ?",
            (full_name, bio.strip(), user_id),
        )
        self.conn.commit()

    def search_users(self, query, limit=30):
        like = f"%{query.strip()}%"
        rows = self.conn.execute(
            "SELECT id, username, full_name, bio FROM users "
            "WHERE username LIKE ? OR full_name LIKE ? ORDER BY username LIMIT ?",
            (like, like, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ---------- المتابعة ----------

    def is_following(self, follower_id, followed_id):
        return (
            self.conn.execute(
                "SELECT 1 FROM follows WHERE follower_id = ? AND followed_id = ?",
                (follower_id, followed_id),
            ).fetchone()
            is not None
        )

    def toggle_follow(self, follower_id, followed_id):
        """يتابع أو يلغي المتابعة. يعيد True إذا أصبح متابعاً."""
        if follower_id == followed_id:
            raise DatabaseError("لا يمكنك متابعة نفسك")
        if self.is_following(follower_id, followed_id):
            self.conn.execute(
                "DELETE FROM follows WHERE follower_id = ? AND followed_id = ?",
                (follower_id, followed_id),
            )
            result = False
        else:
            self.conn.execute(
                "INSERT INTO follows (follower_id, followed_id) VALUES (?, ?)",
                (follower_id, followed_id),
            )
            result = True
        self.conn.commit()
        return result

    # ---------- المنشورات ----------

    def create_post(self, user_id, content):
        content = content.strip()
        if not content:
            raise DatabaseError("لا يمكن نشر منشور فارغ")
        if len(content) > 1000:
            raise DatabaseError("المنشور طويل جداً (الحد الأقصى 1000 حرف)")
        cur = self.conn.execute(
            "INSERT INTO posts (user_id, content, created_at) VALUES (?, ?, ?)",
            (user_id, content, _now()),
        )
        self.conn.commit()
        return cur.lastrowid

    def delete_post(self, user_id, post_id):
        cur = self.conn.execute(
            "DELETE FROM posts WHERE id = ? AND user_id = ?", (post_id, user_id)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def feed(self, user_id, limit=100):
        """منشورات المستخدم ومن يتابعهم."""
        rows = self.conn.execute(
            POST_SELECT
            + """
            WHERE p.user_id = ?
               OR p.user_id IN (SELECT followed_id FROM follows WHERE follower_id = ?)
            ORDER BY p.id DESC LIMIT ?
            """,
            (user_id, user_id, user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def all_posts(self, viewer_id, limit=100):
        rows = self.conn.execute(
            POST_SELECT + " ORDER BY p.id DESC LIMIT ?", (viewer_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def user_posts(self, viewer_id, user_id, limit=100):
        rows = self.conn.execute(
            POST_SELECT + " WHERE p.user_id = ? ORDER BY p.id DESC LIMIT ?",
            (viewer_id, user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ---------- الإعجابات والتعليقات ----------

    def toggle_like(self, user_id, post_id):
        """يعيد True إذا أصبح المنشور معجباً به."""
        cur = self.conn.execute(
            "DELETE FROM likes WHERE user_id = ? AND post_id = ?", (user_id, post_id)
        )
        liked = cur.rowcount == 0
        if liked:
            self.conn.execute(
                "INSERT INTO likes (user_id, post_id) VALUES (?, ?)", (user_id, post_id)
            )
        self.conn.commit()
        return liked

    def add_comment(self, user_id, post_id, content):
        content = content.strip()
        if not content:
            raise DatabaseError("لا يمكن إضافة تعليق فارغ")
        cur = self.conn.execute(
            "INSERT INTO comments (post_id, user_id, content, created_at) VALUES (?, ?, ?, ?)",
            (post_id, user_id, content, _now()),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_comments(self, post_id):
        rows = self.conn.execute(
            """
            SELECT c.id, c.content, c.created_at, c.user_id, u.username, u.full_name
            FROM comments c JOIN users u ON u.id = c.user_id
            WHERE c.post_id = ? ORDER BY c.id
            """,
            (post_id,),
        ).fetchall()
        return [dict(r) for r in rows]
