#!/usr/bin/env bash
# doctracker_reader: reads the data, the views and the routines' definitions, changes nothing.
set -euo pipefail
mysql -uroot -p"$MYSQL_ROOT_PASSWORD" <<SQL
CREATE USER 'doctracker_reader'@'%' IDENTIFIED BY '${READER_PASSWORD}' COMMENT 'Read-only user doctracker documents the databases with.';
GRANT SELECT, SHOW VIEW, SHOW_ROUTINE ON *.* TO 'doctracker_reader'@'%';
SQL
