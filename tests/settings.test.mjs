// SEC requests need a contact; a missing or "github" contact must fail loudly, not send a blocked request.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { writeFileSync, mkdtempSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

const dir = mkdtempSync(join(tmpdir(), 'bs-'));
const use = (obj) => { const p = join(dir, `${Math.random()}.json`); writeFileSync(p, JSON.stringify(obj)); process.env.BUYSIDE_SETTINGS = p; };
const S = await import('../lib/settings.mjs');

test('secContact returns the configured contact', () => { use({ sec_contact: 'A B a@b.com' }); assert.equal(S.secContact(), 'A B a@b.com'); });
test('secContact refuses a missing contact', () => { use({}); assert.throws(() => S.secContact(), /sec_contact is not set/); });
test('secContact refuses "github"', () => { use({ sec_contact: 'me github.com/me' }); assert.throws(() => S.secContact(), /github/); });
test('defaults fill what the file leaves out', () => { use({ sec_contact: 'x y@z.com' }); assert.deepEqual(S.loadSettings().alpha_vantage_keys, []); assert.match(S.loadSettings().chrome_path, /Google Chrome/); });
