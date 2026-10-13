import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database, DatabaseError  # noqa: E402


@pytest.fixture
def db():
    d = Database(":memory:")
    yield d
    d.close()


def test_register_and_login(db):
    user = db.register("ali", "علي أحمد", "secret123")
    assert user["username"] == "ali"
    assert db.login("ALI", "secret123")["id"] == user["id"]
    with pytest.raises(DatabaseError):
        db.login("ali", "wrong-pass")


def test_register_validation(db):
    db.register("ali", "علي", "secret123")
    with pytest.raises(DatabaseError):
        db.register("ali", "آخر", "secret123")
    with pytest.raises(DatabaseError):
        db.register("ab", "قصير", "secret123")
    with pytest.raises(DatabaseError):
        db.register("sara", "سارة", "123")


def test_posts_likes_comments(db):
    a = db.register("ali", "علي", "secret123")
    b = db.register("sara", "سارة", "secret123")
    pid = db.create_post(a["id"], "  مرحباً بالعالم  ")
    assert db.toggle_like(b["id"], pid) is True
    db.add_comment(b["id"], pid, "منشور جميل")
    post = db.all_posts(b["id"])[0]
    assert post["content"] == "مرحباً بالعالم"
    assert (post["like_count"], post["comment_count"], post["liked"]) == (1, 1, 1)
    assert db.toggle_like(b["id"], pid) is False
    assert db.all_posts(b["id"])[0]["like_count"] == 0
    with pytest.raises(DatabaseError):
        db.create_post(a["id"], "   ")


def test_delete_only_own_post(db):
    a = db.register("ali", "علي", "secret123")
    b = db.register("sara", "سارة", "secret123")
    pid = db.create_post(a["id"], "منشور")
    db.add_comment(b["id"], pid, "تعليق")
    assert db.delete_post(b["id"], pid) is False
    assert db.delete_post(a["id"], pid) is True
    assert db.get_comments(pid) == []


def test_follow_and_feed(db):
    a = db.register("ali", "علي", "secret123")
    b = db.register("sara", "سارة", "secret123")
    db.create_post(b["id"], "منشور سارة")
    assert db.feed(a["id"]) == []
    assert db.toggle_follow(a["id"], b["id"]) is True
    assert [p["content"] for p in db.feed(a["id"])] == ["منشور سارة"]
    assert db.get_user(b["id"])["followers"] == 1
    assert db.toggle_follow(a["id"], b["id"]) is False
    with pytest.raises(DatabaseError):
        db.toggle_follow(a["id"], a["id"])


def test_search_and_profile(db):
    a = db.register("ali", "علي أحمد", "secret123")
    db.register("sara", "سارة", "secret123")
    assert [u["username"] for u in db.search_users("أحمد")] == ["ali"]
    db.update_profile(a["id"], "علي", "مطور بايثون")
    assert db.get_user(a["id"])["bio"] == "مطور بايثون"
