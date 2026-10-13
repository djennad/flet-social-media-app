"""طبقة قاعدة البيانات (Supabase) لتطبيق التواصل الاجتماعي.

كل جلسة متصفح تنشئ كائن Database خاصاً بها، فيبقى تسجيل الدخول منفصلاً لكل مستخدم.
الصلاحيات تُفرض في قاعدة البيانات نفسها عبر Row Level Security (انظر supabase/schema.sql).
"""

import os
import re

from postgrest.exceptions import APIError
from supabase import create_client
from supabase_auth.errors import AuthError

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")

AUTH_ERRORS = {
    "invalid_credentials": "البريد الإلكتروني أو كلمة المرور غير صحيحة",
    "user_already_exists": "هذا البريد الإلكتروني مسجّل مسبقاً",
    "email_exists": "هذا البريد الإلكتروني مسجّل مسبقاً",
    "email_not_confirmed": "لم يتم تفعيل البريد الإلكتروني بعد، تحقق من بريدك",
    "weak_password": "كلمة المرور ضعيفة، اختر كلمة أقوى",
    "validation_failed": "البريد الإلكتروني غير صالح",
    "email_address_invalid": "البريد الإلكتروني غير صالح",
    "over_request_rate_limit": "محاولات كثيرة، حاول مرة أخرى بعد قليل",
    "over_email_send_rate_limit": "محاولات كثيرة، حاول مرة أخرى بعد قليل",
}


class DatabaseError(Exception):
    """خطأ برسالة مفهومة للمستخدم."""


class ConfirmEmail(Exception):
    """تم إنشاء الحساب لكن يجب تفعيل البريد الإلكتروني قبل تسجيل الدخول."""


def _auth_error(err):
    return DatabaseError(AUTH_ERRORS.get(getattr(err, "code", None), f"خطأ في المصادقة: {err}"))


def _api_error(err):
    return DatabaseError(f"خطأ في قاعدة البيانات: {err.message or err}")


class Database:
    def __init__(self, url=None, key=None):
        url = url or os.environ.get("SUPABASE_URL")
        key = key or os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError(
                "يجب تعيين SUPABASE_URL و SUPABASE_KEY (في ملف .env أو متغيرات البيئة)"
            )
        self.client = create_client(url, key)
        self.user_id = None

    def close(self):
        try:
            self.client.auth.sign_out()
        except AuthError:
            pass

    def _rpc(self, name, params):
        try:
            return self.client.rpc(name, params).execute().data
        except APIError as err:
            raise _api_error(err) from None

    def _run(self, query):
        try:
            return query.execute().data
        except APIError as err:
            raise _api_error(err) from None

    # ---------- الحسابات ----------

    def register(self, email, username, full_name, password):
        """ينشئ حساباً ويسجّل الدخول. يرفع ConfirmEmail إذا كان تفعيل البريد مطلوباً."""
        email, username, full_name = email.strip(), username.strip(), full_name.strip()
        if not email:
            raise DatabaseError("الرجاء إدخال البريد الإلكتروني")
        if not USERNAME_RE.match(username):
            raise DatabaseError("اسم المستخدم يجب أن يكون 3 إلى 30 حرفاً (حروف إنجليزية وأرقام و _ فقط)")
        if not full_name:
            raise DatabaseError("الرجاء إدخال الاسم الكامل")
        if len(password) < 6:
            raise DatabaseError("كلمة المرور يجب أن تكون 6 أحرف على الأقل")
        if not self._rpc("username_available", {"p_username": username}):
            raise DatabaseError("اسم المستخدم مستخدم مسبقاً")
        try:
            res = self.client.auth.sign_up(
                {
                    "email": email,
                    "password": password,
                    "options": {"data": {"username": username, "full_name": full_name}},
                }
            )
        except AuthError as err:
            raise _auth_error(err) from None
        if res.session is None:
            raise ConfirmEmail()
        self.user_id = res.user.id
        return self.get_user(self.user_id)

    def login(self, email, password):
        try:
            res = self.client.auth.sign_in_with_password(
                {"email": email.strip(), "password": password}
            )
        except AuthError as err:
            raise _auth_error(err) from None
        self.user_id = res.user.id
        return self.get_user(self.user_id)

    def logout(self):
        self.close()
        self.user_id = None

    # ---------- الملفات الشخصية ----------

    def get_user(self, user_id):
        rows = self._rpc("get_profile", {"p_user_id": user_id})
        return rows[0] if rows else None

    def update_profile(self, full_name, bio):
        full_name = full_name.strip()
        if not full_name:
            raise DatabaseError("الاسم الكامل لا يمكن أن يكون فارغاً")
        self._run(
            self.client.table("profiles")
            .update({"full_name": full_name, "bio": bio.strip()})
            .eq("id", self.user_id)
        )

    def search_users(self, query, limit=30):
        # إزالة المحارف الخاصة بصيغة فلاتر PostgREST
        q = re.sub(r"[,()*%\\]", " ", query).strip()
        if not q:
            return []
        return self._run(
            self.client.table("profiles")
            .select("id, username, full_name, bio")
            .or_(f"username.ilike.*{q}*,full_name.ilike.*{q}*")
            .order("username")
            .limit(limit)
        )

    # ---------- المتابعة ----------

    def toggle_follow(self, followed_id):
        """يتابع أو يلغي المتابعة. يعيد True إذا أصبح متابعاً."""
        if followed_id == self.user_id:
            raise DatabaseError("لا يمكنك متابعة نفسك")
        removed = self._run(
            self.client.table("follows")
            .delete()
            .eq("follower_id", self.user_id)
            .eq("followed_id", followed_id)
        )
        if removed:
            return False
        self._run(self.client.table("follows").insert({"followed_id": followed_id}))
        return True

    # ---------- المنشورات ----------

    def create_post(self, content):
        content = content.strip()
        if not content:
            raise DatabaseError("لا يمكن نشر منشور فارغ")
        if len(content) > 1000:
            raise DatabaseError("المنشور طويل جداً (الحد الأقصى 1000 حرف)")
        return self._run(self.client.table("posts").insert({"content": content}))[0]["id"]

    def delete_post(self, post_id):
        """RLS يضمن أن المستخدم لا يحذف إلا منشوراته."""
        return bool(self._run(self.client.table("posts").delete().eq("id", post_id)))

    def feed(self, limit=100):
        """منشوراتي ومنشورات من أتابعهم."""
        return self._rpc("get_posts", {"p_mode": "feed", "p_limit": limit})

    def all_posts(self, limit=100):
        return self._rpc("get_posts", {"p_mode": "all", "p_limit": limit})

    def user_posts(self, user_id, limit=100):
        return self._rpc("get_posts", {"p_mode": "user", "p_user_id": user_id, "p_limit": limit})

    # ---------- الإعجابات والتعليقات ----------

    def toggle_like(self, post_id):
        """يعيد True إذا أصبح المنشور معجباً به."""
        removed = self._run(
            self.client.table("likes").delete().eq("user_id", self.user_id).eq("post_id", post_id)
        )
        if removed:
            return False
        self._run(self.client.table("likes").insert({"post_id": post_id}))
        return True

    def add_comment(self, post_id, content):
        content = content.strip()
        if not content:
            raise DatabaseError("لا يمكن إضافة تعليق فارغ")
        if len(content) > 500:
            raise DatabaseError("التعليق طويل جداً (الحد الأقصى 500 حرف)")
        return self._run(
            self.client.table("comments").insert({"post_id": post_id, "content": content})
        )[0]["id"]

    def get_comments(self, post_id):
        rows = self._run(
            self.client.table("comments")
            .select("id, content, created_at, user_id, profiles(username, full_name)")
            .eq("post_id", post_id)
            .order("id")
        )
        return [
            {**{k: v for k, v in r.items() if k != "profiles"}, **r["profiles"]} for r in rows
        ]
