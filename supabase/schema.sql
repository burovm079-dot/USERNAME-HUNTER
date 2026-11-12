-- Run this in Supabase Dashboard -> SQL Editor.
create table if not exists public.checked_usernames (
  username text primary key check (username ~ '^[a-z]{5}$'),
  status text not null check (status in ('free', 'taken', 'error')),
  checked_at timestamptz not null default now()
);

alter table public.checked_usernames enable row level security;

-- The bot uses the service-role key only on the private worker.
-- Never expose the service-role key in a browser or commit it to GitHub.
