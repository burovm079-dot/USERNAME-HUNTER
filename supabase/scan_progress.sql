-- Persistent cursor for the sequential 5-letter username scanner.
-- Run this once in Supabase Dashboard -> SQL Editor -> New query.

create table if not exists public.scan_progress (
  id smallint primary key check (id = 1),
  next_index bigint not null default 0,
  updated_at timestamptz not null default now()
);

insert into public.scan_progress (id, next_index)
values (1, 0)
on conflict (id) do nothing;

-- The scanner uses the Supabase service-role/secret key from GitHub Actions.
