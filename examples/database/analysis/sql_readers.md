
### dump postgres acme

| object | live database | tree-sitter | sqlglot | sqlparse + rules |
|---|---|---|---|---|
| tables | 25 | **26** | 25 | 25 |
| columns | 131 | **139** | **121** | **121** |
| primary keys | 19 | 19 | 19 | 19 |
| foreign keys | 14 | 14 | 14 | 14 |
| unique | 8 | 8 | 8 | 8 |
| checks | 7 | **0** | 7 | 7 |
| indexes | 11 | 11 | **12** | **12** |
| views | 4 | 4 | **3** | 4 |
| materialized views | 2 | 2 | **0** | 2 |
| functions | 10 | 10 | **7** | 10 |
| procedures | 1 | 1 | 1 | 1 |
| triggers | 4 | 4 | 4 | 4 |
| sequences | 2 | 2 | 2 | 2 |
| types | 4 | **2** | **2** | 4 |
| table comments | 20 | 20 | 20 | 20 |
| column comments | 8 | 8 | 8 | 8 |
| not understood | – | 850 | 99 | 0 |
| seconds | – | 0.01 | 0.05 | 0.23 |
- tree-sitter did not understand: comment ×686, ERROR nodes ×126, ERROR ×33, create_role ×2, alter_sequence ×2, create_policy ×1
- sqlglot did not understand: COMMENT ['ON'] ×19, ALTER ['TEXT'] ×19, ALTER ['TABLE'] ×16, ALTER ['FOREIGN'] ×7, CREATE ['EXTENSION'] ×5, ALTER ['INDEX'] ×5

### dump mysql acme

| object | live database | tree-sitter | sqlglot | sqlparse + rules |
|---|---|---|---|---|
| tables | 11 | **8** | **8** | 11 |
| columns | 66 | **45** | **49** | **69** |
| primary keys | 10 | **8** | **7** | 10 |
| foreign keys | 7 | **0** | 7 | 7 |
| unique | 4 | 4 | 4 | 4 |
| checks | 5 | **1** | 5 | 5 |
| indexes | 5 | **13** | **8** | **11** |
| views | 3 | **1** | 3 | 3 |
| functions | 1 | 1 | 1 | 1 |
| procedures | 1 | 1 | 1 | 1 |
| triggers | 3 | **0** | **0** | 3 |
| table comments | 11 | **0** | **8** | 11 |
| column comments | 6 | **0** | **5** | **5** |
| not understood | – | 267 | 12 | 0 |
| seconds | – | 0.01 | 0.04 | 0.11 |
- tree-sitter did not understand: ERROR nodes ×181, comment ×66, ERROR ×11, drop_view ×4, from ×3, drop_function ×1
- sqlglot did not understand: CREATE ['DEFINER=`root`@`localhost`'] ×4, EndStatement ×4, CREATE ['TABLE'] ×3, DROP ['EVENT'] ×1

### dump sqlite

| object | live database | tree-sitter | sqlglot | sqlparse + rules |
|---|---|---|---|---|
| tables | 8 | **0** | 8 | **7** |
| columns | 38 | **0** | **37** | 38 |
| primary keys | 6 | **0** | **7** | 6 |
| foreign keys | 6 | **0** | **4** | 6 |
| unique | 4 | **0** | 4 | 4 |
| checks | 6 | **0** | **5** | 6 |
| indexes | 3 | **0** | 3 | 3 |
| views | 2 | **0** | 2 | 2 |
| triggers | 2 | **0** | **0** | 2 |
| not understood | – | 10 | 9 | 0 |
| seconds | – | 0.00 | 0.01 | 0.02 |
- tree-sitter did not understand: ERROR nodes ×10
- sqlglot did not understand: CREATE ['TABLE'] ×3, Pragma ×2, CREATE ['TRIGGER'] ×2, EndStatement ×2

### sql server script

| object | live database | tree-sitter | sqlglot | sqlparse + rules |
|---|---|---|---|---|
| tables | 9 | **8** | **6** | **8** |
| columns | 43 | **42** | **35** | 43 |
| primary keys | 7 | 7 | **5** | 7 |
| foreign keys | 7 | 7 | **6** | 7 |
| unique | 5 | **4** | 5 | 5 |
| checks | 5 | **3** | 5 | 5 |
| indexes | 4 | **2** | **1** | 4 |
| views | 3 | **1** | **1** | 3 |
| functions | 3 | **2** | **2** | 3 |
| procedures | 1 | **0** | 1 | 1 |
| triggers | 1 | **0** | **0** | 1 |
| sequences | 1 | 1 | 1 | 1 |
| types | 2 | 2 | **0** | 2 |
| table comments | 3 | **0** | **0** | 3 |
| column comments | 1 | **0** | **0** | 1 |
| not understood | – | 104 | 1 | 0 |
| seconds | – | 0.01 | 0.02 | 0.06 |
- tree-sitter did not understand: ERROR nodes ×76, ERROR ×20, comment ×7, keyword_truncate ×1
- sqlglot did not understand: CREATE ['SYNONYM'] ×1

### flyway V1..V5 (in order)

| object | live database | tree-sitter | sqlglot | sqlparse + rules |
|---|---|---|---|---|
| tables | 6 | 6 | 6 | 6 |
| columns | 32 | 32 | **33** | **33** |
| primary keys | 6 | 6 | 6 | 6 |
| foreign keys | 6 | 6 | 6 | 6 |
| unique | 4 | **3** | **3** | **3** |
| checks | 5 | 5 | 5 | 5 |
| indexes | 1 | 1 | 1 | 1 |
| table comments | 6 | 6 | 6 | 6 |
| not understood | – | 5 | 0 | 0 |
| seconds | – | 0.00 | 0.01 | 0.02 |
- tree-sitter did not understand: comment ×5, ERROR nodes ×0
