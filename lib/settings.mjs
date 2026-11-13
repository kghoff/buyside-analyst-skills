// User settings for the buyside skills: ~/.config/buyside-analyst/settings.json (BUYSIDE_SETTINGS overrides the path).
import { readFileSync, existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

export const DEFAULTS = {
  sec_contact: '', research_dir: '~/Desktop/Research', alpha_vantage_keys: [],
  chrome_path: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  xbrl_cli: '~/Desktop/edgar-xbrl-financials/bin/cli.js',
};
const expand = (p) => (p.startsWith('~/') ? join(homedir(), p.slice(2)) : p);

export function settingsPath() { return expand(process.env.BUYSIDE_SETTINGS || '~/.config/buyside-analyst/settings.json'); }

export function loadSettings() {
  const p = settingsPath();
  return { ...DEFAULTS, ...(existsSync(p) ? JSON.parse(readFileSync(p, 'utf8')) : {}) };
}

export function xbrlCli() { return expand(loadSettings().xbrl_cli); }

export function researchDir() { return expand(loadSettings().research_dir); }

// SEC silently 403s requests without a contact, or whose User-Agent contains "github".
export function secContact() {
  const c = String(loadSettings().sec_contact ?? '').trim();
  if (!c) throw new Error(`sec_contact is not set in ${settingsPath()}. The SEC requires a contact on every request: add "sec_contact": "Your Name you@example.com".`);
  if (/github/i.test(c)) throw new Error('sec_contact must not contain "github": the SEC silently blocks such requests.');
  return c;
}
