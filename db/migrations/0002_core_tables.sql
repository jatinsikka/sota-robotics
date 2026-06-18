-- 0002_core_tables.sql
create type verification_status as enum ('pending','published','held','refuted');
create type result_origin       as enum ('public_reproducible','vendor_internal');
create type eval_realm          as enum ('sim','real');

create table domains (
  id          bigint generated always as identity primary key,
  slug        citext unique not null,
  name        text   not null,
  description text,
  created_at  timestamptz not null default now()
);

create table tasks (
  id         bigint generated always as identity primary key,
  domain_id  bigint not null references domains(id) on delete restrict,
  slug       citext unique not null,
  name       text   not null,
  description text,
  created_at timestamptz not null default now()
);

create table benchmarks (
  id           bigint generated always as identity primary key,
  domain_id    bigint references domains(id) on delete set null,
  slug         citext unique not null,
  name         text   not null,
  measures     text,
  metric       text,
  results_url  text,
  is_saturated boolean not null default false,
  notes        text,
  created_at   timestamptz not null default now()
);

create table methods (
  id         bigint generated always as identity primary key,
  slug       citext unique not null,
  name       text   not null,
  org        text,
  params     text,
  created_at timestamptz not null default now()
);

create table papers (
  id             bigint generated always as identity primary key,
  arxiv_id       text unique,
  title          text not null,
  authors        text,
  abstract       text,
  published_date date,
  url            text,
  created_at     timestamptz not null default now()
);

create table code (
  id          bigint generated always as identity primary key,
  repo_url    text unique not null,
  stars       int,
  last_commit date,
  license     text,
  created_at  timestamptz not null default now()
);

create table results (
  id                   bigint generated always as identity primary key,
  method_id            bigint not null references methods(id)    on delete cascade,
  benchmark_id         bigint not null references benchmarks(id) on delete cascade,
  task_id              bigint references tasks(id)  on delete set null,
  paper_id             bigint references papers(id) on delete set null,
  code_id              bigint references code(id)   on delete set null,
  metric               text   not null,
  metric_value         numeric,
  eval_conditions      jsonb  not null default '{}'::jsonb,
  eval_conditions_hash text   not null,
  realm                eval_realm          not null default 'sim',
  origin               result_origin       not null default 'public_reproducible',
  source_url           text,
  result_date          date,
  confidence           numeric check (confidence is null or (confidence >= 0 and confidence <= 1)),
  verification_status  verification_status not null default 'pending',
  skeptic_notes        text,
  ingested_run_id      text,
  created_at           timestamptz not null default now(),
  unique (method_id, benchmark_id, eval_conditions_hash)
);

create index results_published_idx
  on results (benchmark_id, metric_value desc)
  where verification_status = 'published';

create index results_eval_conditions_gin
  on results using gin (eval_conditions);
