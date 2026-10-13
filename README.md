# تواصل — موقع تواصل اجتماعي بـ Python Flet و Supabase

موقع تواصل اجتماعي مبني بالكامل بلغة **Python** باستخدام مكتبة **Flet**، وقاعدة بيانات **Supabase** (PostgreSQL + نظام تسجيل الدخول Supabase Auth)، بواجهة عربية من اليمين إلى اليسار.

![الصفحة الرئيسية](docs/screenshot-feed.png)

## المميزات

- إنشاء حساب وتسجيل دخول بالبريد الإلكتروني عبر **Supabase Auth**
- نشر المنشورات وحذف منشوراتك
- الإعجاب بالمنشورات وإلغاء الإعجاب ❤️
- التعليق على المنشورات 💬
- متابعة المستخدمين وإلغاء المتابعة
- الصفحة الرئيسية تعرض منشوراتك ومنشورات من تتابعهم
- صفحة استكشاف فيها كل المنشورات والبحث عن مستخدمين
- ملف شخصي (عدد المنشورات والمتابِعين ومن يتابعهم) مع تعديل الاسم والنبذة
- حماية البيانات بـ **Row Level Security**: كل مستخدم يعدّل ويحذف بياناته فقط، والزوار غير المسجلين لا يرون شيئاً
- وضع ليلي 🌙 وخط عربي (Cairo) مضمّن

![الملف الشخصي](docs/screenshot-profile.png)

## الإعداد خطوة بخطوة

### 1. أنشئ مشروعاً على Supabase

ادخل إلى [supabase.com](https://supabase.com) وأنشئ مشروعاً جديداً (مجاني).

### 2. أنشئ الجداول

من لوحة التحكم: **SQL Editor → New query**، الصق محتوى الملف [`supabase/schema.sql`](supabase/schema.sql) كاملاً ثم اضغط **Run**.

### 3. (اختياري) إيقاف تفعيل البريد الإلكتروني

افتراضياً يرسل Supabase رسالة تفعيل لكل حساب جديد، ويجب الضغط على الرابط قبل تسجيل الدخول.
لتسهيل التجربة يمكنك إيقافها من: **Authentication → Sign In / Providers → Email → Confirm email**.

### 4. ضع مفاتيح المشروع

انسخ `.env.example` إلى `.env`:

```bash
cp .env.example .env
```

ثم ضع فيه القيم من **Project Settings → API Keys**:

```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=المفتاح العام (anon / publishable)
```

> ⚠️ استخدم المفتاح العام فقط، **ولا تستخدم** مفتاح `service_role` / `secret` لأنه يتجاوز صلاحيات الحماية.

### 5. شغّل الموقع

```bash
pip install -r requirements.txt
python main.py
```

سيفتح الموقع في المتصفح على: http://localhost:8550
(لتغيير المنفذ: `PORT=9000 python main.py`)

## بنية المشروع

| الملف | الوصف |
|------|------|
| `main.py` | واجهة المستخدم (Flet): تسجيل الدخول، الرئيسية، الاستكشاف، الملف الشخصي، التعليقات |
| `database.py` | الاتصال بـ Supabase: الحسابات، المنشورات، الإعجابات، التعليقات، المتابعات |
| `supabase/schema.sql` | الجداول وسياسات الحماية (RLS) والدوال (RPC) |
| `assets/fonts/` | خط Cairo العربي (رخصة OFL) |
| `tests/` | اختبارات تكامل على Supabase |

### جداول قاعدة البيانات

| الجدول | المحتوى |
|---|---|
| `auth.users` | الحسابات (يديرها Supabase Auth، وكلمات المرور مشفّرة) |
| `profiles` | الملف الشخصي: اسم المستخدم، الاسم الكامل، النبذة (يُنشأ تلقائياً عند التسجيل) |
| `posts` | المنشورات |
| `likes` | الإعجابات |
| `comments` | التعليقات |
| `follows` | المتابعات |

الدوال `get_posts` و `get_profile` تجلب المنشورات والملف الشخصي مع الأعداد (الإعجابات، التعليقات، المتابعين) في استعلام واحد.

## الاختبارات

الاختبارات تعمل على مشروع Supabase حقيقي، والأفضل تشغيلها على نسخة محلية عبر [Supabase CLI](https://supabase.com/docs/guides/local-development) (تحتاج Docker):

```bash
supabase start                      # يطبع API_URL و PUBLISHABLE_KEY
psql postgresql://postgres:postgres@127.0.0.1:54322/postgres -f supabase/schema.sql
pip install pytest
SUPABASE_URL=http://127.0.0.1:54321 SUPABASE_KEY=<PUBLISHABLE_KEY> python -m pytest tests
```

بدون هذين المتغيرين تُتخطّى الاختبارات تلقائياً.
