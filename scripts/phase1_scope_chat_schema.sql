-- Phase 1 foundation for hierarchical RBAC + chat history in Supabase.
-- Apply in Supabase SQL editor.

begin;

create table if not exists public.user_profiles (
  id uuid primary key default gen_random_uuid(),
  username text unique,
  password_hash text,
  full_name text,
  role text not null check (role in (
    'admin',
    'secretaria',
    'coordenacao',
    'professor',
    'viewer'
  )),
  municipio_id text,
  school_id text,
  teacher_id text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.teacher_student_links (
  id uuid primary key default gen_random_uuid(),
  teacher_id text not null,
  student_id text not null,
  created_at timestamptz not null default now(),
  unique (teacher_id, student_id)
);

create table if not exists public.chat_sessions (
  id text primary key,
  session_date date not null,
  created_by_user_id text not null,
  created_by_username text,
  created_by_role text not null,
  municipio_id text,
  school_id text,
  teacher_id text,
  student_id text,
  student_name text,
  school_name text,
  extra jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.chat_messages (
  id uuid primary key default gen_random_uuid(),
  session_id text not null references public.chat_sessions(id) on delete cascade,
  message_index integer not null,
  role text not null check (role in ('user', 'assistant', 'system')),
  content text not null,
  user_id text,
  username text,
  sources jsonb not null default '{}'::jsonb,
  extra jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (session_id, message_index)
);

create index if not exists idx_user_profiles_role on public.user_profiles(role);
create index if not exists idx_user_profiles_municipio on public.user_profiles(municipio_id);
create index if not exists idx_user_profiles_school on public.user_profiles(school_id);
create index if not exists idx_chat_sessions_day on public.chat_sessions(session_date);
create index if not exists idx_chat_sessions_student on public.chat_sessions(student_id);
create index if not exists idx_chat_sessions_school on public.chat_sessions(school_id);
create index if not exists idx_chat_sessions_municipio on public.chat_sessions(municipio_id);
create index if not exists idx_chat_messages_session on public.chat_messages(session_id);

alter table public.user_profiles enable row level security;
alter table public.teacher_student_links enable row level security;
alter table public.chat_sessions enable row level security;
alter table public.chat_messages enable row level security;

revoke all on table public.user_profiles from anon;
revoke all on table public.teacher_student_links from anon;
revoke all on table public.chat_sessions from anon;
revoke all on table public.chat_messages from anon;

revoke all on table public.user_profiles from authenticated;
revoke all on table public.teacher_student_links from authenticated;
revoke all on table public.chat_sessions from authenticated;
revoke all on table public.chat_messages from authenticated;

create or replace function public.current_user_role()
returns text
language sql
stable
as $$
  select role
  from public.user_profiles
  where id::text = auth.uid()::text
    and is_active = true
  limit 1;
$$;

create or replace function public.current_user_municipio_id()
returns text
language sql
stable
as $$
  select municipio_id
  from public.user_profiles
  where id::text = auth.uid()::text
    and is_active = true
  limit 1;
$$;

create or replace function public.current_user_school_id()
returns text
language sql
stable
as $$
  select school_id
  from public.user_profiles
  where id::text = auth.uid()::text
    and is_active = true
  limit 1;
$$;

create policy chat_sessions_select_policy
on public.chat_sessions
for select
to authenticated
using (
  public.current_user_role() = 'admin'
  or (
    public.current_user_role() = 'secretaria'
    and coalesce(municipio_id, '') = coalesce(public.current_user_municipio_id(), '')
  )
  or (
    public.current_user_role() = 'coordenacao'
    and coalesce(school_id, '') = coalesce(public.current_user_school_id(), '')
  )
  or (
    public.current_user_role() = 'professor'
    and created_by_user_id = auth.uid()::text
  )
  or (
    public.current_user_role() = 'viewer'
    and (
      (
        coalesce(public.current_user_school_id(), '') <> ''
        and coalesce(school_id, '') = coalesce(public.current_user_school_id(), '')
      )
      or (
        coalesce(public.current_user_school_id(), '') = ''
        and coalesce(public.current_user_municipio_id(), '') <> ''
        and coalesce(municipio_id, '') = coalesce(public.current_user_municipio_id(), '')
      )
    )
  )
);

create policy chat_messages_select_policy
on public.chat_messages
for select
to authenticated
using (
  exists (
    select 1
    from public.chat_sessions s
    where s.id = chat_messages.session_id
      and (
        public.current_user_role() = 'admin'
        or (
          public.current_user_role() = 'secretaria'
          and coalesce(s.municipio_id, '') = coalesce(public.current_user_municipio_id(), '')
        )
        or (
          public.current_user_role() = 'coordenacao'
          and coalesce(s.school_id, '') = coalesce(public.current_user_school_id(), '')
        )
        or (
          public.current_user_role() = 'professor'
          and s.created_by_user_id = auth.uid()::text
        )
        or (
          public.current_user_role() = 'viewer'
          and (
            (
              coalesce(public.current_user_school_id(), '') <> ''
              and coalesce(s.school_id, '') = coalesce(public.current_user_school_id(), '')
            )
            or (
              coalesce(public.current_user_school_id(), '') = ''
              and coalesce(public.current_user_municipio_id(), '') <> ''
              and coalesce(s.municipio_id, '') = coalesce(public.current_user_municipio_id(), '')
            )
          )
        )
      )
  )
);

-- Backend writes with service-role key, so insert/update/delete policies are optional for now.

commit;
