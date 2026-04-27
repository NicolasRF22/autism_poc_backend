-- Phase 2 hardening for core entities with scoped RBAC policies.
-- Apply after phase1_scope_chat_schema.sql.

begin;

-- Keep RLS active on all protected tables.
alter table if exists public.schools enable row level security;
alter table if exists public.students enable row level security;
alter table if exists public.teachers enable row level security;
alter table if exists public.teacher_student_links enable row level security;
alter table if exists public.diary_entries enable row level security;
alter table if exists public.pdis enable row level security;
alter table if exists public.case_study_submissions enable row level security;
alter table if exists public.school_registration_submissions enable row level security;

-- Grants for authenticated users. RLS policies below enforce scope.
grant select on table public.schools to authenticated;
grant select on table public.students to authenticated;
grant select on table public.teachers to authenticated;
grant select on table public.teacher_student_links to authenticated;
grant select on table public.diary_entries to authenticated;
grant select on table public.pdis to authenticated;
grant select on table public.case_study_submissions to authenticated;
grant select on table public.school_registration_submissions to authenticated;

grant insert, update, delete on table public.teacher_student_links to authenticated;

create or replace function public.current_user_teacher_id()
returns text
language sql
stable
as $$
  select teacher_id
  from public.user_profiles
  where id = auth.uid()
    and is_active = true
  limit 1;
$$;

create or replace function public.school_municipio_id_from_payload(school_payload jsonb)
returns text
language sql
immutable
as $$
  select coalesce(
    nullif(trim(coalesce(school_payload ->> 'municipio_id', '')), ''),
    nullif(trim(coalesce(school_payload #>> '{address,city}', '')), '')
  );
$$;

create or replace function public.can_access_school_scope(target_school_id text, target_municipio_id text)
returns boolean
language sql
stable
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
as $$
  select exists (
    select 1
    from public.schools s
    where s.id = target_school_id
      and public.can_access_school_scope(
        s.id,
        public.school_municipio_id_from_payload(s.payload::jsonb)
      )
  );
$$;

create or replace function public.can_access_teacher_record(target_teacher_id text)
returns boolean
language sql
stable
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
          and public.can_access_school_record(coalesce(t.payload ->> 'school_id', ''))
        )
      )
  );
$$;

create or replace function public.can_access_student_record(target_student_id text)
returns boolean
language sql
stable
as $$
  select exists (
    select 1
    from public.students st
    where st.id = target_student_id
      and (
        public.current_user_role() = 'admin'
        or (
          public.current_user_role() in ('secretaria', 'coordenacao', 'viewer')
          and public.can_access_school_record(coalesce(st.payload ->> 'school_id', ''))
        )
        or (
          public.current_user_role() = 'professor'
          and coalesce(public.current_user_teacher_id(), '') <> ''
          and (
            coalesce(st.payload ->> 'teacher_id', '') = public.current_user_teacher_id()
            or coalesce(st.payload -> 'teacher_ids', '[]'::jsonb) ? public.current_user_teacher_id()
          )
        )
      )
  );
$$;

-- Recreate policies idempotently.
drop policy if exists schools_select_policy on public.schools;
drop policy if exists students_select_policy on public.students;
drop policy if exists teachers_select_policy on public.teachers;
drop policy if exists diary_entries_select_policy on public.diary_entries;
drop policy if exists pdis_select_policy on public.pdis;
drop policy if exists case_study_submissions_select_policy on public.case_study_submissions;
drop policy if exists school_registration_submissions_select_policy on public.school_registration_submissions;
drop policy if exists teacher_student_links_select_policy on public.teacher_student_links;
drop policy if exists teacher_student_links_insert_policy on public.teacher_student_links;
drop policy if exists teacher_student_links_update_policy on public.teacher_student_links;
drop policy if exists teacher_student_links_delete_policy on public.teacher_student_links;

create policy schools_select_policy
on public.schools
for select
to authenticated
using (
  public.can_access_school_scope(
    id,
    public.school_municipio_id_from_payload(payload::jsonb)
  )
);

create policy students_select_policy
on public.students
for select
to authenticated
using (
  public.can_access_student_record(id)
);

create policy teachers_select_policy
on public.teachers
for select
to authenticated
using (
  public.can_access_teacher_record(id)
);

create policy diary_entries_select_policy
on public.diary_entries
for select
to authenticated
using (
  public.can_access_student_record(coalesce(payload ->> 'student_id', ''))
);

create policy pdis_select_policy
on public.pdis
for select
to authenticated
using (
  public.can_access_student_record(coalesce(payload ->> 'student_id', ''))
);

create policy case_study_submissions_select_policy
on public.case_study_submissions
for select
to authenticated
using (
  public.can_access_student_record(coalesce(metadata ->> 'pre_registration_id', ''))
);

create policy school_registration_submissions_select_policy
on public.school_registration_submissions
for select
to authenticated
using (
  public.can_access_school_record(coalesce(metadata ->> 'pre_registration_id', ''))
);

create policy teacher_student_links_select_policy
on public.teacher_student_links
for select
to authenticated
using (
  public.current_user_role() = 'admin'
  or (
    public.current_user_role() = 'professor'
    and coalesce(public.current_user_teacher_id(), '') <> ''
    and teacher_id = public.current_user_teacher_id()
  )
  or (
    public.current_user_role() in ('secretaria', 'coordenacao', 'viewer')
    and public.can_access_student_record(student_id)
  )
);

create policy teacher_student_links_insert_policy
on public.teacher_student_links
for insert
to authenticated
with check (
  public.current_user_role() in ('admin', 'coordenacao')
  and public.can_access_student_record(student_id)
  and public.can_access_teacher_record(teacher_id)
);

create policy teacher_student_links_update_policy
on public.teacher_student_links
for update
to authenticated
using (
  public.current_user_role() in ('admin', 'coordenacao')
  and public.can_access_student_record(student_id)
  and public.can_access_teacher_record(teacher_id)
)
with check (
  public.current_user_role() in ('admin', 'coordenacao')
  and public.can_access_student_record(student_id)
  and public.can_access_teacher_record(teacher_id)
);

create policy teacher_student_links_delete_policy
on public.teacher_student_links
for delete
to authenticated
using (
  public.current_user_role() in ('admin', 'coordenacao')
  and public.can_access_student_record(student_id)
  and public.can_access_teacher_record(teacher_id)
);

commit;
