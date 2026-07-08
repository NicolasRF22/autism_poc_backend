-- Phase 4: Fix all Security Advisor warnings.
-- Fixes:
--   1. Function Search Path Mutable → add SET search_path = public to all 8 helper functions
--   2. RLS Disabled in Public → enable RLS on peis and prompt_templates with scoped policies
-- Apply in Supabase SQL editor after all previous phases.

begin;

-- ============================================================
-- 1. FUNÇÕES COM search_path FIXO
--    Recria as 8 funções com SET search_path = public para
--    evitar ataques de search_path injection.
-- ============================================================

create or replace function public.current_user_role()
returns text
language sql
stable
security invoker
set search_path = public
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
security invoker
set search_path = public
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
security invoker
set search_path = public
as $$
  select school_id
  from public.user_profiles
  where id::text = auth.uid()::text
    and is_active = true
  limit 1;
$$;

create or replace function public.current_user_teacher_id()
returns text
language sql
stable
security invoker
set search_path = public
as $$
  select teacher_id
  from public.user_profiles
  where id::text = auth.uid()::text
    and is_active = true
  limit 1;
$$;

create or replace function public.can_access_school_scope(target_school_id text, target_municipio_id text)
returns boolean
language sql
stable
security invoker
set search_path = public
as $$
  select (
    public.current_user_role() = 'admin'
    or (
      public.current_user_role() = 'secretaria'
      and coalesce(public.current_user_municipio_id(), '') <> ''
      and coalesce(target_municipio_id, '') = coalesce(public.current_user_municipio_id(), '')
    )
    or (
      public.current_user_role() = 'coordenacao'
      and coalesce(public.current_user_school_id(), '') <> ''
      and coalesce(target_school_id, '') = coalesce(public.current_user_school_id(), '')
    )
    or (
      public.current_user_role() = 'professor'
      and coalesce(public.current_user_school_id(), '') <> ''
      and coalesce(target_school_id, '') = coalesce(public.current_user_school_id(), '')
    )
    or (
      public.current_user_role() = 'viewer'
      and (
        (
          coalesce(public.current_user_school_id(), '') <> ''
          and coalesce(target_school_id, '') = coalesce(public.current_user_school_id(), '')
        )
        or (
          coalesce(public.current_user_school_id(), '') = ''
          and coalesce(public.current_user_municipio_id(), '') <> ''
          and coalesce(target_municipio_id, '') = coalesce(public.current_user_municipio_id(), '')
        )
      )
    )
  );
$$;

create or replace function public.can_access_school_record(target_school_id text)
returns boolean
language sql
stable
security invoker
set search_path = public
as $$
  select exists (
    select 1
    from public.schools s
    where s.id = target_school_id
      and public.can_access_school_scope(
        s.id,
        coalesce(s.municipio_id, '')
      )
  );
$$;

create or replace function public.can_access_teacher_record(target_teacher_id text)
returns boolean
language sql
stable
security invoker
set search_path = public
as $$
  select exists (
    select 1
    from public.teachers t
    where t.id = target_teacher_id
      and (
        public.current_user_role() = 'admin'
        or (
          public.current_user_role() = 'professor'
          and coalesce(public.current_user_teacher_id(), '') <> ''
          and t.id = public.current_user_teacher_id()
        )
        or (
          public.current_user_role() in ('secretaria', 'coordenacao', 'viewer')
          and public.can_access_school_record(coalesce(t.school_id, ''))
        )
      )
  );
$$;

create or replace function public.can_access_student_record(target_student_id text)
returns boolean
language sql
stable
security invoker
set search_path = public
as $$
  select exists (
    select 1
    from public.students st
    where st.id = target_student_id
      and (
        public.current_user_role() = 'admin'
        or (
          public.current_user_role() in ('secretaria', 'coordenacao', 'viewer')
          and public.can_access_school_record(coalesce(st.school_id, ''))
        )
        or (
          public.current_user_role() = 'professor'
          and coalesce(public.current_user_teacher_id(), '') <> ''
          and exists (
            select 1 from public.teacher_student_links tsl
            where tsl.student_id = st.id
              and tsl.teacher_id = public.current_user_teacher_id()
          )
        )
      )
  );
$$;

-- ============================================================
-- 2. RLS PARA peis
--    Mesma lógica de pdis: acesso via can_access_student_record.
--    student_id pode ser NULL (SET NULL on delete), então:
--      - admin vê todos
--      - outros só veem se student_id não é null e têm acesso
--      - gerador do PEI vê o próprio mesmo sem student_id
-- ============================================================

alter table public.peis enable row level security;

revoke all on table public.peis from anon, authenticated;
grant select on table public.peis to authenticated;

drop policy if exists peis_select_policy on public.peis;

create policy peis_select_policy
on public.peis
for select
to authenticated
using (
  public.current_user_role() = 'admin'
  or (
    student_id is not null
    and public.can_access_student_record(student_id)
  )
  or (
    generated_by_user_id is not null
    and generated_by_user_id = auth.uid()::text
  )
);

-- ============================================================
-- 3. RLS PARA prompt_templates
--    Tabela de configuração gerenciada via service role pelo backend.
--    Via API direta: somente admin pode ler; ninguém escreve.
-- ============================================================

alter table public.prompt_templates enable row level security;

revoke all on table public.prompt_templates from anon, authenticated;
grant select on table public.prompt_templates to authenticated;

drop policy if exists prompt_templates_select_policy on public.prompt_templates;

create policy prompt_templates_select_policy
on public.prompt_templates
for select
to authenticated
using (
  public.current_user_role() = 'admin'
);

commit;
