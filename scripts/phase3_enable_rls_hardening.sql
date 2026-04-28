-- Phase 3 hardening: turn on RLS for all sensitive tables used by the app.
-- This is safe with the current architecture because the backend uses the
-- Supabase service role key, which bypasses RLS.

begin;

alter table if exists public.user_profiles enable row level security;
alter table if exists public.chat_sessions enable row level security;
alter table if exists public.chat_messages enable row level security;
alter table if exists public.municipalities enable row level security;
alter table if exists public.schools enable row level security;
alter table if exists public.students enable row level security;
alter table if exists public.teachers enable row level security;
alter table if exists public.teacher_student_links enable row level security;
alter table if exists public.diary_entries enable row level security;
alter table if exists public.pdis enable row level security;
alter table if exists public.case_study_submissions enable row level security;
alter table if exists public.school_registration_submissions enable row level security;
alter table if exists public.object_storage_files enable row level security;

revoke all on table public.user_profiles from anon, authenticated;
revoke all on table public.chat_sessions from anon, authenticated;
revoke all on table public.chat_messages from anon, authenticated;
revoke all on table public.municipalities from anon, authenticated;
revoke all on table public.schools from anon, authenticated;
revoke all on table public.students from anon, authenticated;
revoke all on table public.teachers from anon, authenticated;
revoke all on table public.teacher_student_links from anon, authenticated;
revoke all on table public.diary_entries from anon, authenticated;
revoke all on table public.pdis from anon, authenticated;
revoke all on table public.case_study_submissions from anon, authenticated;
revoke all on table public.school_registration_submissions from anon, authenticated;
revoke all on table public.object_storage_files from anon, authenticated;

commit;