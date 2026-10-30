
### postgres

| object | ours (c) | SQLAlchemy (a) | tbls | Atlas |
|---|---|---|---|---|
| aggregates | 1 | – | – | – |
| casts | 1 | – | – | – |
| check constraints | 7 | 7 | 7 | – |
| collations | 1 | – | – | – |
| column comments | 8 | 8 | 8 | – |
| columns | 131 | 131 | 131 | 108 |
| composite types | 1 | – | – | – |
| databases | 3 | – | – | – |
| domains | 2 | 2 | – | – |
| enums | 1 | 1 | 1 | – |
| event triggers | 1 | – | – | – |
| exclusion constraints | 1 | – | 1 | – |
| extended statistics | 1 | – | – | – |
| extensions | 6 | – | – | – |
| foreign keys | 14 | 20 | 20 | 14 |
| foreign servers | 1 | – | – | – |
| foreign tables | 2 | 2 | 2 | – |
| functions | 10 | – | 318 | – |
| generated columns | 1 | 1 | – | – |
| grants | 11 | – | – | – |
| identity columns | 13 | 14 | – | – |
| indexes | 33 | 19 | 39 | 18 |
| inheritance | 2 | – | – | – |
| materialized views | 2 | 2 | 2 | – |
| operators | 1 | – | – | – |
| other comments | 35 | – | – | – |
| partitions | 5 | – | – | – |
| primary keys | 14 | 19 | 19 | 14 |
| procedures | 1 | – | 1 | – |
| publications | 1 | – | – | – |
| roles | 3 | – | – | – |
| row security policies | 1 | – | – | – |
| rules | 1 | – | – | – |
| schemas | 9 | 9 | 7 | 9 |
| sequences | 12 | 12 | – | – |
| shared comments | 4 | – | – | – |
| subscriptions | 1 | – | – | – |
| table comments | 20 | 20 | 20 | – |
| tables | 25 | 25 | 25 | 20 |
| tablespaces | 1 | – | – | – |
| text search configs | 1 | – | – | – |
| triggers | 4 | – | 4 | – |
| unique constraints | 8 | 8 | 8 | – |
| unlogged tables | 1 | – | – | – |
| user mappings | 2 | – | – | – |
| view dependencies | 11 | – | 11 | – |
| views | 4 | 4 | 4 | – |
| seconds | 0.1 | 0.4 | 0.1 | 0.1 |

- SQLAlchemy (a) misses entirely: aggregates, casts, collations, composite types, databases, event triggers, exclusion constraints, extended statistics, extensions, foreign servers, functions, grants, inheritance, operators, other comments, partitions, procedures, publications, roles, row security policies, rules, shared comments, subscriptions, tablespaces, text search configs, triggers, unlogged tables, user mappings, view dependencies

- tbls misses entirely: aggregates, casts, collations, composite types, databases, domains, event triggers, extended statistics, extensions, foreign servers, generated columns, grants, identity columns, inheritance, operators, other comments, partitions, publications, roles, row security policies, rules, sequences, shared comments, subscriptions, tablespaces, text search configs, unlogged tables, user mappings

- Atlas misses entirely: aggregates, casts, check constraints, collations, column comments, composite types, databases, domains, enums, event triggers, exclusion constraints, extended statistics, extensions, foreign servers, foreign tables, functions, generated columns, grants, identity columns, inheritance, materialized views, operators, other comments, partitions, procedures, publications, roles, row security policies, rules, sequences, shared comments, subscriptions, table comments, tablespaces, text search configs, triggers, unique constraints, unlogged tables, user mappings, view dependencies, views

### mysql

| object | ours (c) | SQLAlchemy (a) | tbls | Atlas |
|---|---|---|---|---|
| check constraints | 5 | 5 | 5 | – |
| column comments | 6 | 5 | 6 | – |
| columns | 66 | 66 | 66 | 66 |
| domains | – | 0 | – | – |
| enums | – | 0 | – | – |
| events | 0 | – | – | – |
| foreign keys | 7 | 7 | 7 | 7 |
| foreign tables | – | 0 | – | – |
| functions | 1 | – | 1 | – |
| generated columns | 2 | 2 | – | – |
| grants | 164 | – | – | – |
| identity columns | 1 | 8 | – | – |
| indexes | 25 | 15 | 24 | 15 |
| materialized views | – | 0 | – | – |
| other comments | 2 | – | – | – |
| partitions | 5 | – | – | – |
| primary keys | 10 | 10 | 10 | 10 |
| procedures | 1 | – | 1 | – |
| roles | 0 | – | – | – |
| schemas | 1 | 1 | 1 | 1 |
| sequences | – | 0 | – | – |
| table comments | 11 | 11 | 11 | – |
| tables | 11 | 11 | 11 | 11 |
| triggers | 0 | – | – | – |
| unique constraints | 4 | 4 | 4 | – |
| view dependencies | 5 | – | 5 | – |
| views | 3 | 3 | 3 | – |
| seconds | 0.0 | 0.0 | 0.3 | 0.0 |

- SQLAlchemy (a) misses entirely: functions, grants, other comments, partitions, procedures, view dependencies

- tbls misses entirely: generated columns, grants, identity columns, other comments, partitions

- Atlas misses entirely: check constraints, column comments, functions, generated columns, grants, identity columns, other comments, partitions, procedures, table comments, unique constraints, view dependencies, views

### sqlserver

| object | ours (c) | SQLAlchemy (a) | tbls | Atlas |
|---|---|---|---|---|
| check constraints | 5 | – | 5 | – |
| column comments | 1 | 1 | 1 | – |
| columns | 47 | 47 | 47 | – |
| default constraints | 4 | – | – | – |
| domains | – | 0 | – | – |
| enums | – | 0 | – | – |
| error | – | – | – | 1 |
| foreign keys | 7 | 7 | 7 | – |
| foreign tables | – | 0 | – | – |
| functions | 3 | – | 4 | – |
| generated columns | 1 | 1 | – | – |
| grants | 226 | – | – | – |
| identity columns | 1 | 5 | – | – |
| indexes | 16 | 8 | 15 | – |
| materialized views | – | 0 | – | – |
| partition functions | 1 | – | – | – |
| partitions | 2 | – | – | – |
| primary keys | 7 | 7 | 7 | – |
| procedures | 1 | – | – | – |
| roles | 0 | – | – | – |
| row security policies | 1 | – | – | – |
| schemas | 5 | 5 | 3 | – |
| sequences | 1 | 1 | – | – |
| synonyms | 1 | – | – | – |
| table comments | 3 | 3 | 3 | – |
| tables | 9 | 9 | 9 | – |
| temporal tables | 1 | – | – | – |
| triggers | 1 | – | 1 | – |
| unique constraints | 5 | – | 4 | – |
| user types | 2 | – | – | – |
| view dependencies | 5 | – | 5 | – |
| views | 3 | 3 | 3 | – |
| seconds | 0.1 | 0.2 | 0.1 | 0.0 |

- SQLAlchemy (a) misses entirely: check constraints, default constraints, functions, grants, partition functions, partitions, procedures, row security policies, synonyms, temporal tables, triggers, unique constraints, user types, view dependencies

- tbls misses entirely: default constraints, generated columns, grants, identity columns, partition functions, partitions, procedures, row security policies, sequences, synonyms, temporal tables, user types

- Atlas misses entirely: check constraints, column comments, columns, default constraints, foreign keys, functions, generated columns, grants, identity columns, indexes, partition functions, partitions, primary keys, procedures, row security policies, schemas, sequences, synonyms, table comments, tables, temporal tables, triggers, unique constraints, user types, view dependencies, views
- Atlas: SQL Server needs Atlas Pro

### sqlite

| object | ours (c) | SQLAlchemy (a) | tbls | Atlas |
|---|---|---|---|---|
| check constraints | 4 | 4 | 4 | – |
| columns | 38 | 48 | 37 | 47 |
| domains | – | 0 | – | – |
| enums | – | 0 | – | – |
| foreign keys | 6 | 6 | 6 | 6 |
| foreign tables | – | 0 | – | – |
| generated columns | 2 | 2 | – | – |
| indexes | 3 | 2 | 8 | 7 |
| materialized views | – | 0 | – | – |
| primary keys | 6 | 10 | 8 | 10 |
| schemas | 1 | 1 | 1 | 1 |
| sequences | – | 0 | – | – |
| strict tables | 1 | – | – | – |
| tables | 7 | 12 | 8 | 12 |
| triggers | 2 | – | 2 | – |
| unique constraints | 4 | 4 | 4 | – |
| view dependencies | no access | – | 4 | – |
| views | 2 | 2 | 2 | – |
| virtual tables | 1 | – | – | – |
| without rowid tables | 1 | – | – | – |
| seconds | 0.0 | 0.0 | 0.0 | 0.0 |

- SQLAlchemy (a) misses entirely: strict tables, triggers, virtual tables, without rowid tables

- tbls misses entirely: generated columns, strict tables, virtual tables, without rowid tables

- Atlas misses entirely: check constraints, generated columns, strict tables, triggers, unique constraints, views, virtual tables, without rowid tables
