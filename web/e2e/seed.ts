/**
 * Seeds the e2e market into the local database for manual QA:
 *   npm run e2e:seed
 * Then create a search for Ford Fiesta (Titanium, 2016–2018, USD 11.500, AMBA)
 * and run `python -m tools.rematch` from worker/ to get its backfill.
 */
import { closeDb, resetE2E, seedMarket } from "./support/db";

async function main() {
  await resetE2E();
  const ids = await seedMarket();
  console.log("listings:", ids);
  await closeDb();
}

void main();
