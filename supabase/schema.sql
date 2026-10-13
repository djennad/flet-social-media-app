-- مخطط قاعدة بيانات "تواصل" على Supabase
-- شغّل هذا الملف مرة واحدة من: Supabase Dashboard → SQL Editor → New query → Run

-- ============ الجداول ============

create table if not exists public.profiles (
    id         uuid primary key references auth.users (id) on delete cascade,
    username   text not null check (username ~ '^[A-Za-z0-9_]{3,30}$'),
    full_name  text not null check (length(trim(full_name)) between 1 and 100),
    bio        text not null default '' check (length(bio) <= 200),
    created_at timestamptz not null default now()
);
create unique index if not exists profiles_username_key on public.profiles (lower(username));

create table if not exists public.posts (
    id         bigint generated always as identity primary key,
    user_id    uuid not null default auth.uid() references public.profiles (id) on delete cascade,
    content    text not null check (length(trim(content)) between 1 and 1000),
    created_at timestamptz not null default now()
);
create index if not exists posts_user_id_idx on public.posts (user_id);

create table if not exists public.likes (
    user_id uuid   not null default auth.uid() references public.profiles (id) on delete cascade,
    post_id bigint not null references public.posts (id) on delete cascade,
    primary key (user_id, post_id)
);
create index if not exists likes_post_id_idx on public.likes (post_id);

create table if not exists public.comments (
    id         bigint generated always as identity primary key,
    post_id    bigint not null references public.posts (id) on delete cascade,
    user_id    uuid   not null default auth.uid() references public.profiles (id) on delete cascade,
    content    text   not null check (length(trim(content)) between 1 and 500),
    created_at timestamptz not null default now()
);
create index if not exists comments_post_id_idx on public.comments (post_id);

create table if not exists public.follows (
    follower_id uuid not null default auth.uid() references public.profiles (id) on delete cascade,
    followed_id uuid not null references public.profiles (id) on delete cascade,
    primary key (follower_id, followed_id),
    check (follower_id <> followed_id)
);
create index if not exists follows_followed_id_idx on public.follows (followed_id);

-- ============ إنشاء الملف الشخصي تلقائياً عند التسجيل ============

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = ''
as $$
begin
    insert into public.profiles (id, username, full_name)
    values (
        new.id,
        new.raw_user_meta_data ->> 'username',
        new.raw_user_meta_data ->> 'full_name'
    );
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- ============ صلاحيات الوصول (Row Level Security) ============

alter table public.profiles enable row level security;
alter table public.posts    enable row level security;
alter table public.likes    enable row level security;
alter table public.comments enable row level security;
alter table public.follows  enable row level security;

drop policy if exists "profiles are visible to signed-in users" on public.profiles;
create policy "profiles are visible to signed-in users" on public.profiles
    for select to authenticated using (true);
drop policy if exists "users update their own profile" on public.profiles;
create policy "users update their own profile" on public.profiles
    for update to authenticated using (id = auth.uid()) with check (id = auth.uid());

drop policy if exists "posts are visible to signed-in users" on public.posts;
create policy "posts are visible to signed-in users" on public.posts
    for select to authenticated using (true);
drop policy if exists "users create their own posts" on public.posts;
create policy "users create their own posts" on public.posts
    for insert to authenticated with check (user_id = auth.uid());
drop policy if exists "users delete their own posts" on public.posts;
create policy "users delete their own posts" on public.posts
    for delete to authenticated using (user_id = auth.uid());

drop policy if exists "likes are visible to signed-in users" on public.likes;
create policy "likes are visible to signed-in users" on public.likes
    for select to authenticated using (true);
drop policy if exists "users like as themselves" on public.likes;
create policy "users like as themselves" on public.likes
    for insert to authenticated with check (user_id = auth.uid());
drop policy if exists "users remove their own likes" on public.likes;
create policy "users remove their own likes" on public.likes
    for delete to authenticated using (user_id = auth.uid());

drop policy if exists "comments are visible to signed-in users" on public.comments;
create policy "comments are visible to signed-in users" on public.comments
    for select to authenticated using (true);
drop policy if exists "users comment as themselves" on public.comments;
create policy "users comment as themselves" on public.comments
    for insert to authenticated with check (user_id = auth.uid());
drop policy if exists "users delete their own comments" on public.comments;
create policy "users delete their own comments" on public.comments
    for delete to authenticated using (user_id = auth.uid());

drop policy if exists "follows are visible to signed-in users" on public.follows;
create policy "follows are visible to signed-in users" on public.follows
    for select to authenticated using (true);
drop policy if exists "users follow as themselves" on public.follows;
create policy "users follow as themselves" on public.follows
    for insert to authenticated with check (follower_id = auth.uid());
drop policy if exists "users unfollow as themselves" on public.follows;
create policy "users unfollow as themselves" on public.follows
    for delete to authenticated using (follower_id = auth.uid());

-- ============ دوال يستدعيها التطبيق (RPC) ============

-- هل اسم المستخدم متاح؟ (تُستدعى قبل التسجيل)
create or replace function public.username_available(p_username text)
returns boolean
language sql
stable
security definer set search_path = ''
as $$
    select not exists (
        select 1 from public.profiles where lower(username) = lower(trim(p_username))
    );
$$;

-- المنشورات مع اسم الكاتب وعدد الإعجابات والتعليقات وهل أعجب بها المستخدم الحالي
-- p_mode: 'feed' (منشوراتي ومن أتابعهم) أو 'all' (كل المنشورات) أو 'user' (منشورات p_user_id)
create or replace function public.get_posts(
    p_mode    text,
    p_user_id uuid default null,
    p_limit   int  default 100
)
returns table (
    id            bigint,
    user_id       uuid,
    content       text,
    created_at    timestamptz,
    username      text,
    full_name     text,
    like_count    bigint,
    comment_count bigint,
    liked         boolean
)
language sql
stable
set search_path = ''
as $$
    select p.id, p.user_id, p.content, p.created_at,
           u.username, u.full_name,
           (select count(*) from public.likes l where l.post_id = p.id),
           (select count(*) from public.comments c where c.post_id = p.id),
           exists (select 1 from public.likes l where l.post_id = p.id and l.user_id = auth.uid())
    from public.posts p
    join public.profiles u on u.id = p.user_id
    where case p_mode
        when 'feed' then p.user_id = auth.uid()
                      or p.user_id in (select f.followed_id from public.follows f
                                       where f.follower_id = auth.uid())
        when 'user' then p.user_id = p_user_id
        else true
    end
    order by p.id desc
    limit p_limit;
$$;

-- الملف الشخصي مع الإحصائيات وهل يتابعه المستخدم الحالي
create or replace function public.get_profile(p_user_id uuid)
returns table (
    id           uuid,
    username     text,
    full_name    text,
    bio          text,
    created_at   timestamptz,
    post_count   bigint,
    followers    bigint,
    following    bigint,
    is_following boolean
)
language sql
stable
set search_path = ''
as $$
    select u.id, u.username, u.full_name, u.bio, u.created_at,
           (select count(*) from public.posts p   where p.user_id = u.id),
           (select count(*) from public.follows f where f.followed_id = u.id),
           (select count(*) from public.follows f where f.follower_id = u.id),
           exists (select 1 from public.follows f
                   where f.follower_id = auth.uid() and f.followed_id = u.id)
    from public.profiles u
    where u.id = p_user_id;
$$;

revoke execute on function public.get_posts(text, uuid, int) from public, anon;
revoke execute on function public.get_profile(uuid)          from public, anon;
grant  execute on function public.get_posts(text, uuid, int) to authenticated;
grant  execute on function public.get_profile(uuid)          to authenticated;
grant  execute on function public.username_available(text)  to anon, authenticated;
