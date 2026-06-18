-- 0003_rls.sql
alter table domains    enable row level security;
alter table tasks      enable row level security;
alter table benchmarks enable row level security;
alter table methods    enable row level security;
alter table papers     enable row level security;
alter table code       enable row level security;
alter table results    enable row level security;

-- Reference tables: world-readable (no secrets in taxonomy/paper metadata).
create policy "public read domains"    on domains    for select using (true);
create policy "public read tasks"      on tasks      for select using (true);
create policy "public read benchmarks" on benchmarks for select using (true);
create policy "public read methods"    on methods    for select using (true);
create policy "public read papers"     on papers     for select using (true);
create policy "public read code"       on code       for select using (true);

-- results: only PUBLISHED rows are visible to anon/publishable key.
create policy "public read published results"
  on results for select
  using (verification_status = 'published');

-- No insert/update/delete policies => only the service-role key (which
-- bypasses RLS) can write. The publishable key is read-only by construction.
