"""اختبارات تكامل تعمل على مشروع Supabase حقيقي (يُفضّل محلياً عبر `supabase start`).

تتطلب SUPABASE_URL و SUPABASE_KEY، وتُتخطّى إن لم تكن معرّفة.
يجب أن يكون تفعيل البريد الإلكتروني معطّلاً في المشروع المستخدم للاختبار.
"""

import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database, DatabaseError  # noqa: E402

pytestmark = pytest.mark.skipif(
    not (os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY")),
    reason="SUPABASE_URL / SUPABASE_KEY غير معرّفين",
)


def new_user(name="مستخدم"):
    """ينشئ حساباً جديداً باسم فريد ويعيد (db, user)."""
    tag = uuid.uuid4().hex[:10]
    db = Database()
    user = db.register(f"u{tag}@example.com", f"u_{tag}", name, "secret123")
    user["email"] = f"u{tag}@example.com"
    return db, user


def test_register_and_login():
    db, user = new_user("علي أحمد")
    assert user["full_name"] == "علي أحمد"
    assert user["post_count"] == 0
    email = user["email"]
    db.logout()

    other = Database()
    assert other.login(email, "secret123")["id"] == user["id"]
    with pytest.raises(DatabaseError, match="غير صحيحة"):
        Database().login(email, "wrong-pass")


def test_register_validation():
    db, user = new_user()
    with pytest.raises(DatabaseError, match="مستخدم مسبقاً"):
        Database().register(f"x{uuid.uuid4().hex[:8]}@example.com", user["username"].upper(), "آخر", "secret123")
    with pytest.raises(DatabaseError):
        Database().register("a@example.com", "ab", "قصير", "secret123")
    with pytest.raises(DatabaseError):
        Database().register("a@example.com", "valid_name", "اسم", "123")


def test_posts_likes_comments():
    a, ua = new_user("علي")
    b, ub = new_user("سارة")
    pid = a.create_post("  مرحباً بالعالم  ")

    assert b.toggle_like(pid) is True
    b.add_comment(pid, "منشور جميل")
    post = next(p for p in b.all_posts() if p["id"] == pid)
    assert post["content"] == "مرحباً بالعالم"
    assert (post["like_count"], post["comment_count"], post["liked"]) == (1, 1, True)
    assert next(p for p in a.all_posts() if p["id"] == pid)["liked"] is False

    comments = a.get_comments(pid)
    assert [(c["full_name"], c["content"]) for c in comments] == [("سارة", "منشور جميل")]

    assert b.toggle_like(pid) is False
    assert next(p for p in b.all_posts() if p["id"] == pid)["like_count"] == 0
    with pytest.raises(DatabaseError):
        a.create_post("   ")


def test_rls_only_owner_can_delete_post():
    a, _ = new_user()
    b, _ = new_user()
    pid = a.create_post("منشور")
    b.add_comment(pid, "تعليق")
    assert b.delete_post(pid) is False  # RLS يمنع حذف منشور غيره
    assert a.delete_post(pid) is True
    assert a.get_comments(pid) == []


def test_follow_and_feed():
    a, ua = new_user()
    b, ub = new_user()
    b.create_post("منشور سارة")
    assert [p for p in a.feed() if p["user_id"] == ub["id"]] == []

    assert a.toggle_follow(ub["id"]) is True
    assert [p["content"] for p in a.feed() if p["user_id"] == ub["id"]] == ["منشور سارة"]
    profile = a.get_user(ub["id"])
    assert (profile["followers"], profile["is_following"]) == (1, True)

    assert a.toggle_follow(ub["id"]) is False
    assert a.get_user(ub["id"])["followers"] == 0
    with pytest.raises(DatabaseError):
        a.toggle_follow(ua["id"])


def test_search_and_profile():
    a, ua = new_user("علي أحمد")
    assert ua["id"] in [u["id"] for u in a.search_users(ua["username"])]
    assert a.search_users("(),*") == []
    a.update_profile("علي", "مطور بايثون")
    assert a.get_user(ua["id"])["bio"] == "مطور بايثون"
