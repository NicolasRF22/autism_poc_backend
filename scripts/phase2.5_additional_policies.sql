-- Phase 2.5 additional policies for user_profiles, municipalities, and object_storage_files.
-- Apply after phase2_scope_core_policies.sql.

begin;

-- user_profiles: Each user can only see their own profile, except admin sees all.
drop policy if exists user_profiles_select_policy on public.user_profiles;

create policy user_profiles_select_policy
on public.user_profiles
for select
to authenticated
using (
  public.current_user_role() = 'admin'
  or id::text = auth.uid()::text
);

-- municipalities: Visible to secretaria (own municipio), coordenacao/professor (schools' municipios), admin (all).
drop policy if exists municipalities_select_policy on public.municipalities;

create policy municipalities_select_policy
on public.municipalities
for select
to authenticated
using (
  public.current_user_role() = 'admin'
  or (
    public.current_user_role() = 'secretaria'
    and coalesce(id, '') = coalesce(public.current_user_municipio_id(), '')
  )
  or (
    public.current_user_role() in ('coordenacao', 'professor', 'viewer')
    and (
      coalesce(id, '') in (
        select distinct coalesce(payload ->> 'municipio_id', '')
        from public.schools s
        where s.id = coalesce(public.current_user_school_id(), '')
          and coalesce(public.current_user_school_id(), '') <> ''
      )
      or (
        public.current_user_role() = 'viewer'
        and coalesce(public.current_user_municipio_id(), '') <> ''
        and coalesce(id, '') = coalesce(public.current_user_municipio_id(), '')
      )
    )
  )
);

-- object_storage_files: Visible to admin, or if user can access the student (reference_id is student_id).
drop policy if exists object_storage_files_select_policy on public.object_storage_files;

create policy object_storage_files_select_policy
on public.object_storage_files
for select
to authenticated
using (
  public.current_user_role() = 'admin'
  or public.can_access_student_record(reference_id)
);

commit;
