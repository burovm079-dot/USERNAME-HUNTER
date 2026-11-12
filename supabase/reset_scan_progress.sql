-- Run once after deploying the curated candidate scanner.
-- Resets only the scanner cursor; previously saved check results are preserved.
update public.scan_progress
set next_index = 0,
    updated_at = now()
where id = 1;
