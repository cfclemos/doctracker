# Test databases

The acme shop on four databases, to develop and check doctracker's DATABASE section. Each one holds
every kind of object its catalog can describe, a read-only user, and seed data that is the same at
every start.

| Database | Where | What it holds |
| --- | --- | --- |
| Postgres 17 | `localhost:55432`, databases `acme` and `acme_warehouse` | schemas, enums, domains, composite types, identity and generated columns, arrays, JSON, composite / self / cross-schema foreign keys, unique, check, exclusion, partial / expression / GIN indexes, views, views of views, materialized views, SQL and PL/pgSQL functions, a procedure, triggers, sequences, range and list partitions, inheritance, an unlogged table, extensions, roles, a foreign server (postgres_fdw) to the second database, comments on everything |
| MySQL 8.4 | `localhost:53306`, database `acme` | keys, checks, generated columns, enums, JSON, full-text and functional indexes, range partitions, views, a function, a procedure, triggers, an event, comments |
| SQL Server 2022 | `localhost:51433`, database `acme` | schemas, keys, checks, computed columns, a sequence, a filtered index, a view, scalar and table functions, a procedure, a trigger, a synonym, descriptions (MS_Description) |
| SQLite | `sqlite/acme.sqlite` | keys, checks, generated columns, partial and expression indexes, a WITHOUT ROWID table, views, triggers |

Each one also has what the analysis must find: relations only by name (`imported_orders.customer_id`,
no foreign key, some ids missing), a table without a primary key, a foreign key without an index
(`order_items.product_id`), and sensitive columns (email, CPF, phone, password hash, salary).

## Start, stop, reset

```bash
cp .env.example .env          # then change the passwords
docker compose up -d          # Postgres, MySQL, SQL Server; SQL Server loads its schema once healthy
python sqlite/build.py        # the SQLite file
docker compose down           # stop, keeping the data
docker compose down -v        # stop and drop the data: the next start loads everything again
```

Two OpenSSH servers test doctracker's SSH tunnels: `ssh-bastion`, on `127.0.0.1:${SSH_PORT:-52222}`, and
`ssh-inner`, reachable only through the bastion (a jump). Both let the user `tunnel` in with a key made
once, before the first start (the key stays out of git):

```bash
ssh-keygen -t ed25519 -N "" -f ssh/keys/id_test
```

From the bastion the databases are `postgres:5432`, `mysql:3306` and `mssql:1433`.

doctracker connects as `doctracker_reader`, with `READER_PASSWORD`. It reads and changes nothing:
Postgres gives it `pg_read_all_data` and makes its sessions read only; MySQL gives it `SELECT`,
`SHOW VIEW` and `SHOW_ROUTINE` (MySQL shows triggers only to users who may create them, so the
reader does not see them); SQL Server gives it `db_datareader` and `VIEW DEFINITION`.

## The same schema from every origin

`origins/` holds the acme core (categories, products, customers, orders, order items, payments) as
each kind of project keeps it, reaching the same state in five steps (the last one drops a column,
renames another and adds an index: what a migration lint must flag):

| Origin | Where |
| --- | --- |
| Flyway | `origins/flyway/V1__catalog.sql` … `V5__cleanup.sql`, and `flyway.conf` naming its database; loaded by Flyway's own image (`flyway_schema_history`) |
| golang-migrate | `origins/golang-migrate/000001_catalog.up.sql` … with their `.down.sql`; loaded by golang-migrate's own image (`schema_migrations`) |
| Alembic | `origins/alembic/` — step 3 split into two branches joined by a merge revision |
| Django | `origins/django/shop/` — models and five migrations |
| SQLAlchemy models | `origins/sqlalchemy/models.py` |
| Prisma | `origins/prisma/schema.prisma` |
| Dumps | `origins/dumps/` — Postgres (both databases), MySQL, SQLite with their data (Postgres `acme` as `COPY`, `acme_warehouse` as `INSERT`), and the whole Postgres server without data (`postgres-cluster.sql`), made by `make_dumps.sh` (passwords replaced) |
| Large variant | `origins/large/generate.py` — 600 tables in 12 schemas, a fifth of the relations only by name |

`python origins/compare_origins.py` loads each origin into a database of its own (`origin_<name>`) and
compares them by name. They agree on tables, columns, nullability, primary and foreign keys; Prisma
has no check constraints, and Django indexes every foreign key by itself.

## Analyses run on these databases

`analysis/` keeps the scripts behind the DATABASE section's design decisions and their results. Each
takes the project root as its first argument and reads the passwords from `.env`; all read only.

| Script | What it compares | Result |
| --- | --- | --- |
| `compare_all.py` | what each collector reads from the four databases: SQLAlchemy, SQLAlchemy plus catalog queries, tbls, Atlas (their binaries in `analysis/bin/`, not kept here) | `compare_all.md` |
| `compare.py` | the same on a single Postgres given by `DATABASE_URL` in the project's `.env` | printed |
| `data_probe.py` | what the four offer in common for samples, column profiles, statistics and relations found through the data (values masked) | printed |
| `sql_readers.py` | tree-sitter, sqlglot and sqlparse reading the dumps and migrations, against the live databases | `sql_readers.md` |

## Universe prototype

`universe/` is the prototype of the universe graph (sigma.js + graphology, loaded from esm.sh), as
approved on 2026-10-30: the SQL tree server → database → schema → table or view → column, opened one
level per click; relation kinds chosen on the bar; Depth and "other …" filters; every node a badge in
its kind's colour, a column's badge with its symbols after the name; one box of characteristics on
hover; details on double click.

```bash
python universe/make_universe.py ../.. universe/universe-acme.json          # the four servers
python universe/make_universe.py ../.. universe/universe-large.json large    # the 600 tables (acme_large)
python universe/serve.py 8799 universe                                     # http://127.0.0.1:8799/
```

`universe/checks/` holds the headless Chromium scripts (Node, Chrome DevTools Protocol) used to check
it: walking the tree, hovering, double clicks, themes, depth, and badges overlapping, e.g.
`node universe/checks/probe_overlap.js http://127.0.0.1:8799/sigma.html /tmp/run 9341 '["postgres/acme"]'`.
