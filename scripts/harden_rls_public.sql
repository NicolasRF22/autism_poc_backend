-- Hardening for Supabase public schema tables.
-- Apply in Supabase SQL editor or psql if needed.

alter table if exists public.case_study_submissions enable row level security;
alter table if exists public.diary_entries enable row level security;
alter table if exists public.object_storage_files enable row level security;
alter table if exists public.pdis enable row level security;
alter table if exists public.school_registration_submissions enable row level security;
alter table if exists public.schools enable row level security;
alter table if exists public.students enable row level security;
alter table if exists public.teachers enable row level security;

revoke all on table public.case_study_submissions from anon, authenticated;
revoke all on table public.diary_entries from anon, authenticated;
revoke all on table public.object_storage_files from anon, authenticated;
revoke all on table public.pdis from anon, authenticated;
revoke all on table public.school_registration_submissions from anon, authenticated;
revoke all on table public.schools from anon, authenticated;
revoke all on table public.students from anon, authenticated;
revoke all on table public.teachers from anon, authenticated;

-- Optional: when exposing selected tables via Supabase client SDK,
-- create explicit policies per table/role after this hardening step.
