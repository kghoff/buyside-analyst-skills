import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { mkdtempSync, rmSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

// The skill is installed as a symlink (skills folder/<name> -> repo/skills/<name>), and SKILL.md runs every script by that
// symlinked path. A script that only runs its CLI when argv[1] equals its own real path silently does nothing there
// (exit 0, no output): manifest entries never get written, sell-side reports never get filed, decks never convert.
const SCRIPTS = new URL('../scripts/', import.meta.url).pathname;
const CLIS = ['manifest', 'inbox', 'slides', 'convert', 'render', 'relabel'];
let tmp;
beforeAll(() => { tmp = mkdtempSync(join(tmpdir(), 'symlink-test-')); symlinkSync(SCRIPTS, join(tmp, 'scripts')); });
afterAll(() => { rmSync(tmp, { recursive: true, force: true }); });

describe('CLIs run when called through a symlinked skill folder', () => {
  it.each(CLIS)('%s.mjs prints its usage instead of exiting silently', (name) => {
    const r = spawnSync('node', [join(tmp, 'scripts', `${name}.mjs`)], { encoding: 'utf8' });
    expect(r.stdout + r.stderr).toMatch(/usage/);
    expect(r.status).toBe(1);
  });
});
