/** Pure data helpers. The desk never fetches publishers or rewrites their headlines. */
export const DEFAULTS = Object.freeze({ q: '', scope: 'all', source: '', day: '', sort: 'newest', view: 'headlines' });
export const normalize = value => String(value ?? '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[‘’]/g, "'").toLowerCase();
export function matches(text, query) {
  const words = normalize(query).match(/"[^"]+"|\S+/g) || [];
  return words.every(word => normalize(text).includes(word.replace(/^"|"$/g, '')));
}
export function safeURL(raw) {
  try {
    const url = new URL(raw);
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : '';
  } catch { return ''; }
}
export const host = url => { try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return ''; } };
export function readState(search) {
  const params = new URLSearchParams(search);
  const state = { ...DEFAULTS };
  for (const key of ['q', 'source', 'day']) state[key] = (params.get(key) || '').slice(0, 240);
  for (const [key, choices] of Object.entries({ scope: ['all', 'partners', 'saved'], sort: ['newest', 'oldest', 'source'], view: ['headlines', 'newsrooms', 'about'] })) {
    if (choices.includes(params.get(key))) state[key] = params.get(key);
  }
  return state;
}
export function stateURL(state, base, share = false) {
  const url = new URL(base);
  for (const key of Object.keys(DEFAULTS)) {
    const value = share && key === 'scope' && state.scope === 'saved' ? 'all' : state[key];
    if (!value || value === DEFAULTS[key]) url.searchParams.delete(key);
    else url.searchParams.set(key, value);
  }
  return url.href;
}
const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const eastern = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
function wallTime(year, month, day, hour, minute) {
  const target = Date.UTC(year, month, day, hour, minute);
  let result = target;
  for (let i = 0; i < 3; i++) {
    const parts = Object.fromEntries(eastern.formatToParts(result).map(p => [p.type, p.value]));
    const observed = Date.UTC(+parts.year, +parts.month - 1, +parts.day, +parts.hour, +parts.minute);
    result += target - observed;
  }
  return result;
}
export function referenceDate(text) {
  const match = text.match(/(January|February|March|April|May|June|July|August|September|October|November|December) (\d{1,2}), (\d{4}), (\d{1,2}):(\d{2}) (AM|PM) (EDT|EST)/);
  if (!match) return null;
  const [, month, day, year, hour, minute, period] = match;
  const date = new Date(Date.UTC(+year, months.indexOf(month), +day));
  if (date.getUTCDate() !== +day || +hour < 1 || +hour > 12 || +minute > 59) return null;
  return { year: +year, month: months.indexOf(month), day: +day, weekday: date.getUTCDay(), timestamp: wallTime(+year, months.indexOf(month), +day, +hour % 12 + (period === 'PM' ? 12 : 0), +minute) };
}
export function publication(label, reference) {
  const unknown = { timestamp: null, day: '', when: label || 'Time not supplied' };
  const match = label.match(/^(Sun|Mon|Tue|Wed|Thu|Fri|Sat) (\d{1,2}):(\d{2}) (AM|PM)$/);
  if (!match || !reference || +match[2] < 1 || +match[2] > 12 || +match[3] > 59) return unknown;
  const delta = (reference.weekday - days.indexOf(match[1]) + 7) % 7;
  const date = new Date(Date.UTC(reference.year, reference.month, reference.day - delta));
  const timestamp = wallTime(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate(), +match[2] % 12 + (match[4] === 'PM' ? 12 : 0), +match[3]);
  if (timestamp > reference.timestamp) return unknown;
  return { timestamp, day: date.toISOString().slice(0, 10), when: new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', weekday: 'short', month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' }).format(timestamp) };
}
export function filterStories(stories, state, saved) {
  return stories.filter(story => (state.scope !== 'partners' || story.partner) && (state.scope !== 'saved' || saved.has(story.url)) && (!state.source || story.host === state.source) && (!state.day || story.day === state.day) && matches(`${story.title} ${story.source} ${story.host}`, state.q)).sort((a, b) => {
    if (state.sort === 'source') return a.source.localeCompare(b.source) || a.title.localeCompare(b.title);
    // Unknown dates remain at the end, even when sorting oldest first.
    if (a.timestamp === null) return b.timestamp === null ? a.title.localeCompare(b.title) : 1;
    if (b.timestamp === null) return -1;
    return (state.sort === 'oldest' ? a.timestamp - b.timestamp : b.timestamp - a.timestamp) || a.title.localeCompare(b.title);
  });
}
export function toCSV(stories) {
  const cell = value => {
    let text = String(value ?? '');
    if (/^[\s\uFEFF]*[=+\-@]/.test(text) || /^[\t\r\n]/.test(text)) text = `'${text}`;
    return `"${text.replace(/"/g, '""')}"`;
  };
  return '\uFEFF' + [['Headline', 'Newsroom', 'Published (Eastern time)', 'Partner in snapshot', 'URL'], ...stories.map(s => [s.title, s.source, s.when, s.partner ? 'Yes' : 'No', s.url])].map(row => row.map(cell).join(',')).join('\r\n');
}
export function parseSnapshot(html) {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const meta = doc.querySelector('.meta')?.textContent.trim() || 'Snapshot date not supplied';
  const reference = referenceDate(meta);
  const unique = new Map();
  let skipped = 0;
  for (const row of doc.querySelectorAll('ul.stories > li')) {
    const anchor = row.querySelector('a[href]');
    const url = safeURL(anchor?.getAttribute('href'));
    const title = anchor?.textContent.trim();
    const source = row.querySelector('.src')?.textContent.trim();
    if (!url || !title || !source) { skipped++; continue; }
    const story = { url, title, source, host: host(url), partner: row.classList.contains('is-partner'), ...publication(row.querySelector('.when')?.textContent.trim() || '', reference) };
    if (unique.has(url)) unique.get(url).partner ||= story.partner;
    else unique.set(url, story);
  }
  const directory = [...doc.querySelectorAll('table tbody tr')].map(row => {
    const cells = [...row.querySelectorAll('td')];
    const url = safeURL(cells[3]?.querySelector('a')?.getAttribute('href'));
    return { name: cells[0]?.textContent.trim() || '', type: cells[1]?.textContent.trim() || '', feed: cells[2]?.textContent.trim().toLowerCase() === 'yes', url, host: host(url) };
  }).filter(row => row.name);
  const stats = [...doc.querySelectorAll('.stat')].map(row => ({ value: row.querySelector('b')?.textContent.trim() || '', label: row.querySelector('span')?.textContent.trim() || '' }));
  const reported = stats.filter(s => /headlines/i.test(s.label)).reduce((sum, s) => sum + (Number(s.value.replace(/,/g, '')) || 0), 0);
  return { stories: [...unique.values()], meta, reference, directory, stats, reported, skipped };
}
