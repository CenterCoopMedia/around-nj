import test from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULTS, matches, safeURL, host, readState, stateURL, referenceDate, publication, filterStories, toCSV } from '../assets/desk-core.mjs';

test('search folds accents and smart quotes, supports all words and quoted phrases', () => {
  assert.ok(matches('Café in South Orange: New Jersey’s schools', 'cafe schools'));
  assert.ok(matches('South Orange schools', '"south orange" schools'));
  assert.ok(!matches('South schools in Orange', '"south orange"'));
  assert.ok(matches('School [board] opens', '[board]'));
  assert.ok(matches('Anything', '   '));
  assert.ok(!matches('New Jersey', 'New York'));
});
test('only credential-free absolute HTTP links are accepted', () => {
  for (const value of ['javascript:alert(1)', 'data:text/html,x', '/relative', 'https://user:pass@example.com', null, 'not a url']) assert.equal(safeURL(value), '');
  assert.equal(safeURL('https://example.com/story?a=1#story'), 'https://example.com/story?a=1#story');
  assert.equal(host('https://www.example.com/a'), 'example.com');
});
test('URL state validates enums and bounds text', () => {
  assert.deepEqual(readState('?scope=nope&sort=bad&view=wrong'), { ...DEFAULTS });
  assert.equal(readState('?q=' + 'x'.repeat(999)).q.length, 240);
  assert.equal(readState('?scope=partners&day=2026-09-18').scope, 'partners');
});
test('view links round-trip Unicode and omit the private saved scope', () => {
  const state = { ...DEFAULTS, q: 'école & town', scope: 'saved', source: 'example.com' };
  const url = stateURL(state, 'https://example.org/around-nj/?utm_source=test');
  assert.deepEqual(readState(new URL(url).search), state);
  assert.equal(new URL(url).searchParams.get('utm_source'), 'test');
  assert.equal(readState(new URL(stateURL(state, url, true)).search).scope, 'all');
});
const reference = referenceDate('Demo snapshot · Friday, September 18, 2026, 12:01 PM EDT · last 72 hours · not a live product');
test('legacy source times resolve from capture date, not the computer clock', () => {
  assert.equal(reference.timestamp, Date.parse('2026-09-18T16:01:00Z'));
  const value = publication('Wed 11:30 AM', reference);
  assert.equal(value.timestamp, Date.parse('2026-09-16T15:30:00Z'));
  assert.equal(value.day, '2026-09-16');
  assert.match(value.when, /2026/);
  assert.match(value.when, /EDT/);
});
test('date resolution crosses month/year and daylight-saving boundaries', () => {
  const january = referenceDate('Friday, January 2, 2026, 12:01 PM EST');
  assert.equal(publication('Wed 11:00 AM', january).day, '2025-12-31');
  const november = referenceDate('Sunday, November 1, 2026, 12:01 PM EST');
  assert.equal(publication('Sat 10:00 AM', november).timestamp, Date.parse('2026-10-31T14:00:00Z'));
});
test('missing, invalid, and future dates remain unknown rather than fabricated', () => {
  assert.equal(referenceDate('April 31, 2026, 12:01 PM EDT'), null);
  assert.equal(referenceDate('no date supplied'), null);
  for (const label of ['Fri 1:00 PM', 'Fri 13:00 AM', 'Fri 10:99 AM', 'yesterday', '']) assert.equal(publication(label, reference).timestamp, null);
  assert.equal(publication('Wed 11:30 AM', null).timestamp, null);
});
const stories = [
  { title: 'New school opens', source: 'A newsroom', host: 'a.test', partner: true, url: 'https://a.test/1', timestamp: 20, day: '2026-09-18', when: 'Friday' },
  { title: 'Town approves school funding', source: 'B newsroom', host: 'b.test', partner: false, url: 'https://b.test/1', timestamp: 10, day: '2026-09-17', when: 'Thursday' },
  { title: 'Time unavailable', source: 'C newsroom', host: 'c.test', partner: true, url: 'https://c.test/1', timestamp: null, day: '', when: 'Unknown' }
];
test('search, source, day, partner, and saved filters compose without mutating data', () => {
  const saved = new Map([[stories[1].url, stories[1]]]);
  assert.equal(filterStories(stories, { ...DEFAULTS, q: 'school', scope: 'partners' }, saved).length, 1);
  assert.equal(filterStories(stories, { ...DEFAULTS, source: 'b.test', day: '2026-09-17' }, saved).length, 1);
  assert.equal(filterStories(stories, { ...DEFAULTS, scope: 'saved' }, saved)[0].url, stories[1].url);
  assert.equal(filterStories(stories, { ...DEFAULTS, source: 'missing.test' }, saved).length, 0);
  assert.equal(stories[0].timestamp, 20);
});
test('chronological sorting puts unknown times last in both directions', () => {
  assert.deepEqual(filterStories(stories, DEFAULTS, new Map()).map(s => s.timestamp), [20, 10, null]);
  assert.deepEqual(filterStories(stories, { ...DEFAULTS, sort: 'oldest' }, new Map()).map(s => s.timestamp), [10, 20, null]);
});
test('CSV preserves Unicode, quotes, newlines and neutralizes formula injection', () => {
  const csv = toCSV([{ ...stories[0], title: '=HYPERLINK("bad")\nCafé' }, { ...stories[1], title: '  @SUM(1,2)' }]);
  assert.ok(csv.startsWith('\uFEFF'));
  assert.ok(csv.includes('"\'=HYPERLINK(""bad"")\nCafé"'));
  assert.ok(csv.includes('"\'  @SUM(1,2)"'));
  assert.ok(csv.includes(stories[0].url));
});
