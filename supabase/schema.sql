-- Run this in Supabase Dashboard -> SQL Editor.
create table if not exists public.checked_usernames (
  username text primary key check (username ~ '^[a-z]{5}$'),
  status text not null,
  checked_at timestamptz not null default now()
);

-- Update the status constraint for both existing and fresh installations.
alter table public.checked_usernames
  drop constraint if exists checked_usernames_status_check;

alter table public.checked_usernames
  add constraint checked_usernames_status_check
  check (status in ('public_chat_found', 'not_found_unverified', 'error'));

alter table public.checked_usernames enable row level security;

-- Keep the Supabase secret key only in private server-side environment variables.
