"""تواصل - موقع تواصل اجتماعي مبني بـ Python Flet و Supabase.

التشغيل (بعد إعداد ملف .env، انظر README.md):
    python main.py            # يفتح الموقع في المتصفح على http://localhost:8550
"""

import os
from datetime import datetime, timezone

import flet as ft

from database import ConfirmEmail, Database, DatabaseError

APP_NAME = "تواصل"
AVATAR_COLORS = [
    ft.Colors.INDIGO, ft.Colors.TEAL, ft.Colors.DEEP_ORANGE, ft.Colors.PURPLE,
    ft.Colors.GREEN, ft.Colors.PINK, ft.Colors.BLUE, ft.Colors.BROWN,
]


def avatar(user_id, name, radius=20):
    """صورة رمزية بالحرف الأول من الاسم ولون ثابت لكل مستخدم."""
    return ft.CircleAvatar(
        content=ft.Text(name[:1].upper(), weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
        bgcolor=AVATAR_COLORS[int(user_id[:8], 16) % len(AVATAR_COLORS)],
        radius=radius,
    )


def time_ago(iso):
    seconds = int((datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds())
    if seconds < 60:
        return "الآن"
    if seconds < 3600:
        return f"منذ {seconds // 60} دقيقة"
    if seconds < 86400:
        return f"منذ {seconds // 3600} ساعة"
    if seconds < 86400 * 30:
        return f"منذ {seconds // 86400} يوم"
    return iso[:10]


class SocialApp:
    def __init__(self, page: ft.Page):
        self.page = page
        # عميل Supabase مستقل لكل جلسة متصفح
        self.db = Database()
        self.user = None
        self.tab = 0
        self.profile_user_id = None

        page.title = APP_NAME
        page.rtl = True
        page.fonts = {"Cairo": "fonts/Cairo-Regular.ttf"}
        page.theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO, font_family="Cairo")
        page.dark_theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO, font_family="Cairo")
        page.theme_mode = ft.ThemeMode.LIGHT
        page.padding = 0
        page.on_disconnect = lambda e: self.db.close()
        self.show_auth()

    # ---------- أدوات مساعدة ----------

    def toast(self, message, error=False):
        self.page.show_dialog(
            ft.SnackBar(
                ft.Text(message, color=ft.Colors.WHITE),
                bgcolor=ft.Colors.RED_700 if error else ft.Colors.GREEN_700,
            )
        )

    def set_body(self, *controls):
        self.page.controls.clear()
        self.page.add(
            ft.Container(
                content=ft.Column(list(controls), scroll=ft.ScrollMode.AUTO, expand=True),
                padding=ft.Padding.symmetric(horizontal=16, vertical=12),
                expand=True,
                alignment=ft.Alignment.TOP_CENTER,
            )
        )

    def refresh_user(self):
        self.user = self.db.get_user(self.user["id"])

    # ---------- تسجيل الدخول / إنشاء حساب ----------

    def show_auth(self, register=False):
        self.page.appbar = None
        self.page.navigation_bar = None

        email = ft.TextField(
            label="البريد الإلكتروني", prefix_icon=ft.Icons.EMAIL, autofocus=True,
            keyboard_type=ft.KeyboardType.EMAIL, rtl=False,
        )
        username = ft.TextField(label="اسم المستخدم", prefix_icon=ft.Icons.PERSON, visible=register)
        full_name = ft.TextField(label="الاسم الكامل", prefix_icon=ft.Icons.BADGE, visible=register)
        password = ft.TextField(
            label="كلمة المرور", prefix_icon=ft.Icons.LOCK, password=True, can_reveal_password=True
        )

        def submit(e):
            try:
                if register:
                    self.user = self.db.register(
                        email.value or "", username.value or "", full_name.value or "", password.value or ""
                    )
                    self.toast(f"أهلاً بك يا {self.user['full_name']}!")
                else:
                    self.user = self.db.login(email.value or "", password.value or "")
                self.show_main()
            except ConfirmEmail:
                self.toast("تم إنشاء الحساب! افتح بريدك الإلكتروني لتفعيله ثم سجّل الدخول")
                self.show_auth(register=False)
            except DatabaseError as err:
                self.toast(str(err), error=True)

        password.on_submit = submit

        card = ft.Card(
            content=ft.Container(
                padding=30,
                width=420,
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.FORUM, size=64, color=ft.Colors.PRIMARY),
                        ft.Text(APP_NAME, size=32, weight=ft.FontWeight.BOLD),
                        ft.Text(
                            "أنشئ حساباً جديداً" if register else "سجّل دخولك وشارك أفكارك",
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        email,
                        username,
                        full_name,
                        password,
                        ft.FilledButton(
                            "إنشاء حساب" if register else "تسجيل الدخول",
                            on_click=submit,
                            width=float("inf"),
                            height=45,
                        ),
                        ft.TextButton(
                            "لديك حساب؟ سجّل الدخول" if register else "ليس لديك حساب؟ أنشئ حساباً",
                            on_click=lambda e: self.show_auth(not register),
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=15,
                    tight=True,
                ),
            )
        )
        self.page.controls.clear()
        self.page.add(
            ft.Container(content=card, alignment=ft.Alignment.CENTER, expand=True, padding=16)
        )

    def logout(self, e=None):
        self.db.logout()
        self.user = None
        self.tab = 0
        self.show_auth()

    # ---------- الواجهة الرئيسية ----------

    def toggle_theme(self, e):
        dark = self.page.theme_mode == ft.ThemeMode.DARK
        self.page.theme_mode = ft.ThemeMode.LIGHT if dark else ft.ThemeMode.DARK
        e.control.icon = ft.Icons.DARK_MODE if dark else ft.Icons.LIGHT_MODE
        self.page.update()

    def show_main(self):
        self.page.appbar = ft.AppBar(
            leading=ft.Icon(ft.Icons.FORUM),
            title=ft.Text(APP_NAME, weight=ft.FontWeight.BOLD),
            bgcolor=ft.Colors.PRIMARY_CONTAINER,
            actions=[
                ft.IconButton(ft.Icons.DARK_MODE, tooltip="الوضع الليلي", on_click=self.toggle_theme),
                ft.IconButton(ft.Icons.LOGOUT, tooltip="تسجيل الخروج", on_click=self.logout),
            ],
        )
        self.page.navigation_bar = ft.NavigationBar(
            selected_index=self.tab,
            on_change=lambda e: self.go_tab(e.control.selected_index),
            destinations=[
                ft.NavigationBarDestination(icon=ft.Icons.HOME_OUTLINED, selected_icon=ft.Icons.HOME, label="الرئيسية"),
                ft.NavigationBarDestination(icon=ft.Icons.EXPLORE_OUTLINED, selected_icon=ft.Icons.EXPLORE, label="استكشاف"),
                ft.NavigationBarDestination(icon=ft.Icons.PERSON_OUTLINE, selected_icon=ft.Icons.PERSON, label="ملفي"),
            ],
        )
        self.go_tab(self.tab)

    def go_tab(self, index):
        self.tab = index
        self.page.navigation_bar.selected_index = index
        if index == 0:
            self.show_feed()
        elif index == 1:
            self.show_explore()
        else:
            self.show_profile(self.user["id"])

    def refresh(self):
        """إعادة رسم الشاشة الحالية بعد أي تغيير."""
        if self.tab == 2 or self.profile_user_id is not None:
            self.show_profile(self.profile_user_id or self.user["id"])
        else:
            self.go_tab(self.tab)

    # ---------- بطاقة المنشور ----------

    def post_card(self, post):
        is_mine = post["user_id"] == self.user["id"]

        def like(e):
            self.db.toggle_like(post["id"])
            self.refresh()

        def delete(e):
            def confirm(ev):
                self.page.pop_dialog()
                self.db.delete_post(post["id"])
                self.toast("تم حذف المنشور")
                self.refresh()

            self.page.show_dialog(
                ft.AlertDialog(
                    title=ft.Text("حذف المنشور"),
                    content=ft.Text("هل أنت متأكد من حذف هذا المنشور؟"),
                    actions=[
                        ft.TextButton("إلغاء", on_click=lambda ev: self.page.pop_dialog()),
                        ft.FilledButton("حذف", on_click=confirm),
                    ],
                )
            )

        header = ft.Row(
            [
                ft.Container(
                    content=ft.Row(
                        [
                            avatar(post["user_id"], post["full_name"]),
                            ft.Column(
                                [
                                    ft.Text(post["full_name"], weight=ft.FontWeight.BOLD),
                                    ft.Text(
                                        f"\u200e@{post['username']} · {time_ago(post['created_at'])}",
                                        size=12,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                    ),
                                ],
                                spacing=0,
                            ),
                        ]
                    ),
                    on_click=lambda e: self.show_profile(post["user_id"]),
                ),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="حذف", on_click=delete, visible=is_mine),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        actions = ft.Row(
            [
                ft.TextButton(
                    str(post["like_count"]),
                    icon=ft.Icons.FAVORITE if post["liked"] else ft.Icons.FAVORITE_BORDER,
                    icon_color=ft.Colors.RED if post["liked"] else None,
                    on_click=like,
                ),
                ft.TextButton(
                    str(post["comment_count"]),
                    icon=ft.Icons.CHAT_BUBBLE_OUTLINE,
                    on_click=lambda e: self.show_comments(post),
                ),
            ]
        )

        return ft.Card(
            content=ft.Container(
                padding=15,
                content=ft.Column([header, ft.Text(post["content"], size=16, selectable=True), ft.Divider(height=1), actions]),
            )
        )

    def posts_column(self, posts, empty_text):
        if not posts:
            return ft.Container(
                content=ft.Text(empty_text, color=ft.Colors.ON_SURFACE_VARIANT, text_align=ft.TextAlign.CENTER),
                padding=40,
                alignment=ft.Alignment.CENTER,
            )
        return ft.Column([self.post_card(p) for p in posts])

    def composer(self):
        field = ft.TextField(
            hint_text=f"بماذا تفكر يا {self.user['full_name']}؟",
            multiline=True,
            min_lines=2,
            max_lines=6,
            max_length=1000,
            border=ft.NoInputBorder(),
        )

        def publish(e):
            try:
                self.db.create_post(field.value or "")
                self.toast("تم النشر بنجاح")
                self.refresh()
            except DatabaseError as err:
                self.toast(str(err), error=True)

        return ft.Card(
            content=ft.Container(
                padding=15,
                content=ft.Column(
                    [
                        ft.Row([avatar(self.user["id"], self.user["full_name"]), ft.Container(field, expand=True)], vertical_alignment=ft.CrossAxisAlignment.START),
                        ft.Row([ft.FilledButton("نشر", icon=ft.Icons.SEND, on_click=publish)], alignment=ft.MainAxisAlignment.END),
                    ]
                ),
            )
        )

    # ---------- الشاشات ----------

    def show_feed(self):
        self.profile_user_id = None
        self.set_body(
            self.composer(),
            ft.Text("آخر المنشورات", size=20, weight=ft.FontWeight.BOLD),
            self.posts_column(
                self.db.feed(),
                "لا توجد منشورات بعد.\nانشر شيئاً أو تابع أشخاصاً من صفحة الاستكشاف!",
            ),
        )

    def show_explore(self):
        self.profile_user_id = None
        results = ft.Column()

        def search(e=None):
            q = (search_field.value or "").strip()
            results.controls.clear()
            if q:
                users = self.db.search_users(q)
                if not users:
                    results.controls.append(ft.Text("لا يوجد مستخدمون مطابقون", color=ft.Colors.ON_SURFACE_VARIANT))
                for u in users:
                    results.controls.append(
                        ft.ListTile(
                            leading=avatar(u["id"], u["full_name"]),
                            title=ft.Text(u["full_name"]),
                            subtitle=ft.Text(f"\u200e@{u['username']}"),
                            on_click=lambda e, uid=u["id"]: self.show_profile(uid),
                        )
                    )
            self.page.update()

        search_field = ft.TextField(
            hint_text="ابحث عن مستخدمين...",
            prefix_icon=ft.Icons.SEARCH,
            on_change=search,
            border_radius=30,
        )
        self.set_body(
            search_field,
            results,
            ft.Text("كل المنشورات", size=20, weight=ft.FontWeight.BOLD),
            self.posts_column(self.db.all_posts(), "لا توجد منشورات على الموقع بعد."),
        )

    def show_profile(self, user_id):
        self.refresh_user()
        user = self.db.get_user(user_id)
        if user is None:
            return
        is_me = user_id == self.user["id"]
        self.profile_user_id = None if is_me else user_id
        if is_me and self.tab != 2:
            self.tab = 2
            self.page.navigation_bar.selected_index = 2

        def stat(value, label):
            return ft.Column(
                [ft.Text(str(value), size=18, weight=ft.FontWeight.BOLD), ft.Text(label, size=12)],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
            )

        def follow(e):
            self.db.toggle_follow(user_id)
            self.show_profile(user_id)

        if is_me:
            action = ft.OutlinedButton("تعديل الملف الشخصي", icon=ft.Icons.EDIT, on_click=lambda e: self.edit_profile())
        else:
            following = user["is_following"]
            action = (
                ft.OutlinedButton("إلغاء المتابعة", icon=ft.Icons.PERSON_REMOVE, on_click=follow)
                if following
                else ft.FilledButton("متابعة", icon=ft.Icons.PERSON_ADD, on_click=follow)
            )

        header = ft.Card(
            content=ft.Container(
                padding=20,
                content=ft.Column(
                    [
                        avatar(user["id"], user["full_name"], radius=45),
                        ft.Text(user["full_name"], size=24, weight=ft.FontWeight.BOLD),
                        ft.Text(f"\u200e@{user['username']}", color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text(user["bio"] or ("أضف نبذة عنك" if is_me else ""), text_align=ft.TextAlign.CENTER),
                        ft.Row(
                            [stat(user["post_count"], "منشورات"), stat(user["followers"], "متابِعون"), stat(user["following"], "يتابع")],
                            alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                        ),
                        action,
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
            )
        )
        controls = []
        if not is_me:
            controls.append(ft.TextButton("رجوع", icon=ft.Icons.ARROW_BACK, on_click=lambda e: self.go_tab(self.tab)))
        controls += [header]
        if is_me:
            controls.append(self.composer())
        controls.append(
            self.posts_column(self.db.user_posts(user_id), "لا توجد منشورات بعد.")
        )
        self.set_body(*controls)

    # ---------- النوافذ المنبثقة ----------

    def edit_profile(self):
        name = ft.TextField(label="الاسم الكامل", value=self.user["full_name"])
        bio = ft.TextField(label="نبذة عنك", value=self.user["bio"], multiline=True, max_lines=4, max_length=200)

        def save(e):
            try:
                self.db.update_profile(name.value or "", bio.value or "")
                self.page.pop_dialog()
                self.toast("تم حفظ التعديلات")
                self.show_profile(self.user["id"])
            except DatabaseError as err:
                self.toast(str(err), error=True)

        self.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("تعديل الملف الشخصي"),
                content=ft.Column([name, bio], tight=True, width=400),
                actions=[
                    ft.TextButton("إلغاء", on_click=lambda e: self.page.pop_dialog()),
                    ft.FilledButton("حفظ", on_click=save),
                ],
            )
        )

    def show_comments(self, post):
        comments_list = ft.ListView(spacing=8, height=300, width=450)
        field = ft.TextField(hint_text="اكتب تعليقاً...", expand=True, autofocus=True)

        def load():
            comments_list.controls.clear()
            comments = self.db.get_comments(post["id"])
            if not comments:
                comments_list.controls.append(ft.Text("لا توجد تعليقات بعد. كن أول من يعلّق!", color=ft.Colors.ON_SURFACE_VARIANT))
            for c in comments:
                comments_list.controls.append(
                    ft.Row(
                        [
                            avatar(c["user_id"], c["full_name"], radius=16),
                            ft.Container(
                                expand=True,
                                padding=10,
                                border_radius=12,
                                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                                content=ft.Column(
                                    [
                                        ft.Text(f"{c['full_name']} · {time_ago(c['created_at'])}", size=12, weight=ft.FontWeight.BOLD),
                                        ft.Text(c["content"], selectable=True),
                                    ],
                                    spacing=2,
                                ),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    )
                )

        def send(e):
            try:
                self.db.add_comment(post["id"], field.value or "")
                field.value = ""
                load()
                self.page.update()
            except DatabaseError as err:
                self.toast(str(err), error=True)

        def close(e):
            self.page.pop_dialog()
            self.refresh()

        field.on_submit = send
        load()
        self.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("التعليقات"),
                content=ft.Column(
                    [comments_list, ft.Row([field, ft.IconButton(ft.Icons.SEND, on_click=send)])],
                    tight=True,
                ),
                actions=[ft.TextButton("إغلاق", on_click=close)],
            )
        )


def main(page: ft.Page):
    try:
        SocialApp(page)
    except RuntimeError as err:
        page.rtl = True
        page.add(ft.Text(str(err), color=ft.Colors.RED, size=18))


if __name__ == "__main__":
    ft.run(
        main,
        view=ft.AppView.WEB_BROWSER,
        port=int(os.environ.get("PORT", 8550)),
        assets_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets"),
        no_cdn=True,
    )
