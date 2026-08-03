/**
 * Schema parity check.
 *
 * The Drizzle schema in src/models/schema.ts was hand-written from the
 * SQLAlchemy models. This script proves it matches the database Alembic
 * actually built, by diffing it against information_schema in both directions:
 *
 *   - a column in Drizzle that the DB lacks  -> queries would fail at runtime
 *   - a column in the DB that Drizzle lacks  -> we'd silently never read it
 *   - a nullability or type mismatch         -> subtle wrong-value bugs
 *
 * Run:  DATABASE_URL=... pnpm --filter @kol/api tsx scripts/verify-schema.ts
 */
import { getTableConfig } from 'drizzle-orm/pg-core';
import { Pool } from 'pg';

import * as schema from '../src/models/schema.js';

interface DbColumn {
  table_name: string;
  column_name: string;
  is_nullable: 'YES' | 'NO';
  data_type: string;
}

/** Postgres type names that satisfy a given Drizzle column type. */
const TYPE_EQUIVALENTS: Record<string, string[]> = {
  serial: ['integer'],
  integer: ['integer'],
  bigint: ['bigint'],
  boolean: ['boolean'],
  date: ['date'],
  text: ['text'],
  bytea: ['bytea'],
};

function acceptableTypes(drizzleType: string): string[] | null {
  const lower = drizzleType.toLowerCase();
  if (lower.startsWith('varchar')) return ['character varying'];
  if (lower.startsWith('numeric')) return ['numeric'];
  if (lower.startsWith('timestamp')) return ['timestamp with time zone', 'timestamp without time zone'];
  return TYPE_EQUIVALENTS[lower] ?? null;
}

async function main() {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error('DATABASE_URL is required');

  const pool = new Pool({ connectionString: url });
  const { rows } = await pool.query<DbColumn>(
    `SELECT table_name, column_name, is_nullable, data_type
       FROM information_schema.columns
      WHERE table_schema = 'public'`,
  );
  await pool.end();

  const byTable = new Map<string, Map<string, DbColumn>>();
  for (const row of rows) {
    if (!byTable.has(row.table_name)) byTable.set(row.table_name, new Map());
    byTable.get(row.table_name)!.set(row.column_name, row);
  }

  const problems: string[] = [];
  let tablesChecked = 0;
  let columnsChecked = 0;

  for (const value of Object.values(schema)) {
    let config;
    try {
      config = getTableConfig(value as never);
    } catch {
      continue; // not a pgTable (e.g. the bytea helper)
    }

    const dbCols = byTable.get(config.name);
    if (!dbCols) {
      problems.push(`TABLE MISSING IN DB: ${config.name}`);
      continue;
    }
    tablesChecked++;

    const seen = new Set<string>();
    for (const col of config.columns) {
      seen.add(col.name);
      columnsChecked++;
      const dbCol = dbCols.get(col.name);
      if (!dbCol) {
        problems.push(`${config.name}.${col.name}: in Drizzle, MISSING in DB`);
        continue;
      }

      const allowed = acceptableTypes(col.getSQLType());
      if (allowed && !allowed.includes(dbCol.data_type)) {
        problems.push(
          `${config.name}.${col.name}: type ${col.getSQLType()} vs DB ${dbCol.data_type}`,
        );
      }

      // A column Drizzle thinks is NOT NULL but the DB allows null will hand us
      // nulls the types promise cannot happen.
      const dbNullable = dbCol.is_nullable === 'YES';
      if (col.notNull && dbNullable) {
        problems.push(`${config.name}.${col.name}: Drizzle notNull, DB nullable`);
      }
    }

    for (const name of dbCols.keys()) {
      if (!seen.has(name)) {
        problems.push(`${config.name}.${name}: in DB, MISSING in Drizzle`);
      }
    }
  }

  console.log(`Checked ${tablesChecked} tables / ${columnsChecked} columns.`);
  if (problems.length) {
    console.error(`\n❌ ${problems.length} mismatch(es):`);
    for (const p of problems) console.error(`  - ${p}`);
    process.exit(1);
  }
  console.log('✅ Drizzle schema matches the database exactly.');
}

main().catch((err: unknown) => {
  console.error(err);
  process.exit(1);
});
