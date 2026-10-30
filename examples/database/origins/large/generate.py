"""Write a large variant of the shop for Postgres: hundreds of tables in many schemas, linked by keys.

`python origins/large/generate.py 600` writes `origins/large/large.sql` (kept out of git) with 600
tables; load it into its own database with
`docker compose exec -T postgres psql -U acme_admin -d postgres -c 'CREATE DATABASE acme_large'` and
`docker compose exec -T postgres psql -U acme_admin -d acme_large < origins/large/large.sql`.
The same arguments always give the same file.
"""

import random
import sys
from pathlib import Path

OUTPUT = Path(__file__).with_name("large.sql")
"""The file written."""

TYPES = ["integer", "bigint", "text", "numeric(12, 2)", "boolean", "date", "timestamptz", "jsonb", "uuid"]
"""Column types the generated tables pick from."""


def generate(tables: int = 600, schemas: int = 12, seed: int = 7) -> str:
    """Build the SQL of the large variant.

    Args:
        tables: How many tables.
        schemas: How many schemas they are spread over.
        seed: The random seed, so the output is the same every time.

    Returns:
        The SQL: schemas, tables with a primary key, columns, foreign keys to earlier tables (some
        missing on purpose, kept as `<name>_id` columns only), comments, and a view every 25 tables.
    """
    rng = random.Random(seed)
    lines = [f"CREATE SCHEMA area_{s:02};" for s in range(schemas)]
    names = []
    for t in range(tables):
        name = f"area_{t % schemas:02}.entity_{t:04}"
        columns = ["id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY"]
        columns += [f"field_{c} {rng.choice(TYPES)}" for c in range(rng.randint(3, 10))]
        for target in rng.sample(names, k=min(len(names), rng.randint(0, 3))):
            column = f"{target.split('.')[1]}_id"
            enforced = rng.random() > 0.2  # one in five only by name: what implied relations must find
            columns.append(f"{column} bigint" + (f" REFERENCES {target} (id)" if enforced else ""))
        lines.append(f"CREATE TABLE {name} (\n    " + ",\n    ".join(columns) + "\n);")
        lines.append(f"COMMENT ON TABLE {name} IS 'Generated table {t}.';")
        if t and t % 25 == 0:
            lines.append(f"CREATE VIEW {name}_summary AS SELECT id FROM {name};")
        names.append(name)
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    OUTPUT.write_text(generate(int(sys.argv[1]) if len(sys.argv) > 1 else 600), encoding="utf-8")
    print(f"Written {OUTPUT}")
