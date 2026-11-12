-- Run once in Supabase Dashboard -> SQL Editor.
-- Stores whether a confirmed available username has already been sent to Telegram.
alter table public.checked_usernames
  add column if not exists notified_at timestamptz;
