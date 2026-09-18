import { DEFAULTS, safeURL, host, matches, readState, stateURL, filterStories, toCSV, parseSnapshot } from './desk-core.mjs';

const $ = id => document.getElementById(id);
const make = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
};
const plural = (n, word) => `${n.toLocaleString()} ${word}${n === 1 ? '' : 's'}`;
const KEYS = { saved: 'around-nj.saved.v1', theme: 'around-nj.theme.v1', density: 'around-nj.density.v1' };
let memoryOnly = false;
function storageGet(key) { try { return localStorage.getItem(key); } catch { memoryOnly = true; return null; } }
function storageSet(key, value) {
  try { localStorage.setItem(key, value); }
  catch { memoryOnly = true; }
  $('storage-note').hidden = !memoryOnly;
}
function loadSaved() {
  const result = new Map();
  try {
    const data = JSON.parse(storageGet(KEYS.saved) || '[]');
    if (!Array.isArray(data)) return result;
    for (const value of data.slice(0, 2000)) {
      if (!value || typeof value !== 'object') continue;
      const url = safeURL(value.url);
      if (!url || typeof value.title !== 'string' || typeof value.source !== 'string') continue;
      result.set(url, { url, host: host(url), title: value.title.slice(0, 2000), source: value.source.slice(0, 200), partner: value.partner === true, day: /^\d{4}-\d{2}-\d{2}$/.test(value.day) ? value.day : '', timestamp: Number.isFinite(value.timestamp) && value.timestamp >= 0 && value.timestamp < 4102444800000 ? value.timestamp : null, when: typeof value.when === 'string' ? value.when.slice(0, 200) : 'Time not supplied' });
    }
  } catch { /* A damaged saved list must not prevent reading the snapshot. */ }
  return result;
}
let saved = loadSaved();
let state = readState(location.search);
if (!new URLSearchParams(location.search).has('view') && ['headlines', 'newsrooms', 'about'].includes(location.hash.slice(1))) state.view = location.hash.slice(1);
let model = null;
let limit = 30;
let filtered = [];
let compact = storageGet(KEYS.density) === 'compact';
const narrow = matchMedia('(max-width: 720px)');
$('filter-panel').open = !narrow.matches;
narrow.addEventListener('change', event => { $('filter-panel').open = !event.matches; });
let searchTimer;
let toastTimer;
function announce(message) {
  clearTimeout(toastTimer);
  $('announcement').textContent = message;
  toastTimer = setTimeout(() => { $('announcement').textContent = ''; }, 6000);
}
const systemTheme = matchMedia('(prefers-color-scheme: dark)');
let themePreference = storageGet(KEYS.theme);
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $('theme').textContent = theme === 'dark' ? 'Light appearance' : 'Dark appearance';
  $('theme').setAttribute('aria-label', `Switch to ${theme === 'dark' ? 'light' : 'dark'} appearance`);
}
applyTheme(['light', 'dark'].includes(themePreference) ? themePreference : (systemTheme.matches ? 'dark' : 'light'));
systemTheme.addEventListener('change', event => { if (!themePreference) applyTheme(event.matches ? 'dark' : 'light'); });
$('theme').addEventListener('click', () => {
  themePreference = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  applyTheme(themePreference);
  storageSet(KEYS.theme, themePreference);
});
function writeURL(push = false) {
  const url = new URL(stateURL(state, location.href));
  url.hash = '';
  if (url.href !== location.href) history[push ? 'pushState' : 'replaceState'](null, '', url);
}
function change(patch, { push = false, focus = false } = {}) {
  clearTimeout(searchTimer);
  state = { ...state, q: $('search').value, ...patch };
  limit = 30;
  writeURL(push);
  render();
  if (focus) $('results-title').focus();
}
function reset() { change({ ...DEFAULTS, view: 'headlines' }); $('search').focus(); }
function fillSelect(element, entries, value, placeholder) {
  element.replaceChildren(new Option(placeholder, ''), ...entries.map(([key, label]) => new Option(label, key)));
  if (value && !entries.some(([key]) => key === value)) element.add(new Option(`Not in this collection: ${value}`, value));
  element.value = value;
}
function controls() {
  if ($('search').value !== state.q) $('search').value = state.q;
  $('clear-search').hidden = !state.q;
  $('sort').value = state.sort;
  $('saved-count').textContent = saved.size;
  const activeFilters = Number(Boolean(state.source)) + Number(Boolean(state.day));
  $('filter-summary').textContent = activeFilters ? `Filter headlines · ${activeFilters} active` : 'Filter headlines';
  const collection = state.scope === 'saved' ? [...saved.values()] : model.stories;
  const sources = new Map(collection.map(story => [story.host, story.source]));
  fillSelect($('source'), [...sources.entries()].sort((a, b) => a[1].localeCompare(b[1])), state.source, 'All newsrooms');
  const days = [...new Set(collection.map(story => story.day).filter(Boolean))].sort().reverse();
  fillSelect($('day'), days.map(day => [day, new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(`${day}T12:00:00Z`))]), state.day, 'All dates in snapshot');
  document.querySelectorAll('[data-scope]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.scope === state.scope)));
  $('density').setAttribute('aria-pressed', String(compact));
  $('story-list').classList.toggle('compact', compact);
  $('storage-note').hidden = !memoryOnly;
}
function storyNode(story) {
  const row = make('li', undefined, 'story');
  const content = make('div');
  const meta = make('div', undefined, 'story-meta');
  const source = make('button', story.source, 'source-link');
  source.type = 'button';
  source.title = `Filter headlines from ${story.source}`;
  source.addEventListener('click', () => change({ source: story.host }, { focus: true }));
  meta.append(source);
  if (story.partner) meta.append(make('span', 'Partner', 'partner-key'));
  const time = make('time', story.when);
  if (story.timestamp !== null) time.dateTime = new Date(story.timestamp).toISOString();
  meta.append(time);
  const heading = make('h3');
  const link = make('a', story.title);
  link.href = story.url;
  heading.append(link);
  content.append(meta, heading);
  const actions = make('div', undefined, 'story-actions');
  const save = make('button', undefined, 'save-button');
  save.type = 'button';
  save.dataset.save = story.url;
  const isSaved = saved.has(story.url);
  save.setAttribute('aria-pressed', String(isSaved));
  save.setAttribute('aria-label', `${isSaved ? 'Remove saved story' : 'Save story'}: ${story.title}`);
  const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  icon.setAttribute('viewBox', '0 0 16 20');
  icon.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', 'M3 2h10v15l-5-3-5 3Z');
  icon.append(path);
  save.append(icon, make('span', isSaved ? 'Saved' : 'Save'));
  save.addEventListener('click', () => {
    const oldIndex = [...$('story-list').children].indexOf(row);
    if (saved.has(story.url)) saved.delete(story.url);
    else saved.set(story.url, story);
    storageSet(KEYS.saved, JSON.stringify([...saved.values()]));
    render();
    const same = [...document.querySelectorAll('[data-save]')].find(button => button.dataset.save === story.url);
    (same || $('story-list').children[Math.min(oldIndex, $('story-list').children.length - 1)]?.querySelector('.save-button') || $('results-title')).focus();
    announce(saved.has(story.url) ? (memoryOnly ? 'Story saved for this visit.' : 'Story saved in this browser.') : 'Story removed from your saved list.');
  });
  actions.append(save);
  row.append(content, actions);
  return row;
}
function renderHeadlines() {
  const collection = state.scope === 'saved' ? [...saved.values()] : model.stories;
  filtered = filterStories(collection, state, saved);
  const labels = { all: 'All headlines', partners: 'Partner headlines', saved: 'Saved stories' };
  $('results-title').textContent = labels[state.scope];
  const shown = filtered.slice(0, limit);
  $('result-count').textContent = `Showing ${shown.length.toLocaleString()} of ${plural(filtered.length, 'headline')}${state.q || state.source || state.day ? ' matching your filters' : ''}`;
  $('story-list').replaceChildren(...shown.map(storyNode));
  $('empty').hidden = filtered.length > 0;
  const noSaves = state.scope === 'saved' && saved.size === 0;
  $('empty-title').textContent = noSaves ? 'Your reading list starts here' : 'No matching headlines';
  $('empty-copy').textContent = noSaves ? 'Use Save beside any headline to keep it in this browser.' : 'Try fewer words, a different newsroom, or reset your filters.';
  $('empty-reset').textContent = noSaves ? 'Browse headlines' : 'Reset filters';
  $('saved-note').hidden = state.scope !== 'saved';
  $('load-more').hidden = filtered.length <= limit;
  $('load-more').textContent = `Show ${Math.min(30, Math.max(0, filtered.length - limit))} more headlines`;
  $('export').disabled = filtered.length === 0;
  $('export').title = `Download all ${filtered.length} matching headlines as CSV`;
}
function newsroomRows() {
  const directory = model.directory.map(row => ({ ...row, partner: true }));
  const known = new Set(directory.map(row => row.host).filter(Boolean));
  for (const story of model.stories) {
    if (known.has(story.host)) continue;
    known.add(story.host);
    directory.push({ name: story.source, type: 'Publisher', feed: null, url: new URL(story.url).origin, host: story.host, partner: story.partner });
  }
  return directory.map(room => ({ ...room, count: room.host ? model.stories.filter(story => story.host === room.host).length : 0 })).sort((a, b) => a.name.localeCompare(b.name));
}
function renderDirectory() {
  const query = $('room-search').value;
  const filter = $('room-filter').value;
  const rows = newsroomRows().filter(room => matches(`${room.name} ${room.host} ${room.type}`, query) && (filter !== 'partners' || room.partner) && (filter !== 'stories' || room.count > 0) && (filter !== 'missing' || (room.partner && room.feed === false)));
  $('directory-count').textContent = plural(rows.length, 'organization');
  $('directory-list').replaceChildren(...rows.map(room => {
    const row = make('article', undefined, 'room');
    const info = make('div');
    info.append(make('h3', room.name), make('p', `${room.type}${room.partner ? ' · Partner invitation list' : ' · Other feed list'}`));
    const status = make('p', room.feed === true ? 'Feed listed in snapshot' : room.feed === false ? 'No feed listed' : 'Headline source', 'room-status');
    const actions = make('div');
    if (room.count) {
      const browse = make('button', `${plural(room.count, 'headline')} →`);
      browse.type = 'button';
      browse.addEventListener('click', () => change({ ...DEFAULTS, source: room.host }, { push: true, focus: true }));
      actions.append(browse);
    } else actions.append(make('span', 'No embedded headlines', 'small'));
    if (room.url) { const link = make('a', 'Visit website ↗'); link.href = room.url; link.setAttribute('aria-label', `Visit ${room.name}`); actions.append(link); }
    row.append(info, status, actions);
    return row;
  }));
  if (!rows.length) $('directory-list').append(make('p', 'No newsrooms match. Try another name or change the filter.', 'empty'));
}
function render() {
  if (!model) return;
  for (const view of ['headlines', 'newsrooms', 'about']) $(view).hidden = view !== state.view;
  document.querySelectorAll('.page-tabs [data-view-link]').forEach(link => {
    if (link.dataset.viewLink === state.view) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  controls();
  renderHeadlines();
  renderDirectory();
}
function details() {
  const partnerCount = model.stories.filter(story => story.partner).length;
  const sourceCount = new Set(model.stories.map(story => story.host)).size;
  $('all-count').textContent = model.stories.length;
  $('partner-count').textContent = partnerCount;
  $('snapshot-date').textContent = model.reference ? new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' }).format(model.reference.timestamp) : model.meta;
  $('summary').replaceChildren(...[[model.stories.length, 'browsable headlines'], [sourceCount, 'headline sources'], [partnerCount, 'partner headlines']].map(([number, label]) => { const span = make('span'); span.append(make('b', number.toLocaleString()), document.createTextNode(label)); return span; }));
  $('about-meta').textContent = model.meta;
  $('coverage-note').textContent = `${plural(model.stories.length, 'headline')} from ${plural(sourceCount, 'source')} are available here.${model.reported && model.reported !== model.stories.length ? ` The original collection summary lists ${model.reported.toLocaleString()} headlines, but the remaining records are not embedded in the source page.` : ''}${model.skipped ? ` ${plural(model.skipped, 'incomplete or unsafe record')} could not be included.` : ''}`;
  $('feed-note').textContent = `${model.directory.filter(room => room.feed).length} of ${model.directory.length} organizations in the partner directory have a feed listed. This does not confirm that every feed is working or has headlines in the snapshot.`;
  $('original-stats').replaceChildren(...model.stats.map(stat => { const group = make('div'); group.append(make('dt', stat.label), make('dd', stat.value)); return group; }));
}
async function load() {
  $('load-state').hidden = false;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(new URL('../snapshot.html', import.meta.url), { signal: controller.signal, cache: 'no-cache' });
    if (!response.ok) throw new Error(`Snapshot returned HTTP ${response.status}`);
    model = parseSnapshot(await response.text());
    if (!model.stories.length) throw new Error('No usable headlines in the snapshot');
    for (const story of model.stories) if (saved.has(story.url)) saved.set(story.url, story);
    details();
    render();
    $('load-state').hidden = true;
  } catch {
    model = null;
    $('load-state').replaceChildren(make('h2', 'The headline index could not load.'), make('p', 'You can still open the original reading page, or try the index again.'));
    const link = make('a', 'Read the original snapshot'); link.href = 'snapshot.html';
    const retry = make('button', 'Try again'); retry.type = 'button'; retry.style.marginLeft = '16px';
    retry.addEventListener('click', () => { retry.disabled = true; retry.textContent = 'Loading…'; load(); });
    $('load-state').append(link, retry);
    $('snapshot-date').textContent = 'Snapshot details are unavailable.';
    $('summary').textContent = 'The original snapshot remains available below.';
  } finally { clearTimeout(timeout); }
}
document.querySelectorAll('[data-view-link]').forEach(link => link.addEventListener('click', event => {
  if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  change({ view: link.dataset.viewLink }, { push: true });
}));
document.querySelectorAll('[data-scope]').forEach(button => button.addEventListener('click', () => change({ scope: button.dataset.scope }, { push: true })));
$('source').addEventListener('change', event => change({ source: event.target.value }));
$('day').addEventListener('change', event => change({ day: event.target.value }));
$('sort').addEventListener('change', event => change({ sort: event.target.value }));
$('search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => change({ q: $('search').value }), 120); });
$('search-form').addEventListener('submit', event => { event.preventDefault(); change({ q: $('search').value.trim() }); });
$('clear-search').addEventListener('click', () => { change({ q: '' }); $('search').focus(); });
$('reset').addEventListener('click', reset);
$('empty-reset').addEventListener('click', reset);
$('density').addEventListener('click', () => { compact = !compact; storageSet(KEYS.density, compact ? 'compact' : 'comfortable'); render(); });
$('load-more').addEventListener('click', () => { const previous = limit; limit += 30; render(); $('story-list').children[previous]?.querySelector('h3 a')?.focus(); });
$('room-search').addEventListener('input', renderDirectory);
$('room-filter').addEventListener('change', renderDirectory);
$('export').addEventListener('click', () => {
  const url = URL.createObjectURL(new Blob([toCSV(filtered)], { type: 'text/csv;charset=utf-8' }));
  const link = make('a'); link.href = url; link.download = 'around-new-jersey-headlines.csv';
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  announce(`Exported all ${plural(filtered.length, 'matching headline')}.`);
});
$('share').addEventListener('click', async () => {
  const url = stateURL(state, location.href, true);
  try { await navigator.clipboard.writeText(url); announce(state.scope === 'saved' ? 'View link copied. It shares filters, not your private saved list.' : 'View link copied. Search and filters are included.'); }
  catch { $('copy-value').value = url; $('copy-dialog').showModal(); $('copy-value').focus(); $('copy-value').select(); }
});
window.addEventListener('popstate', () => { clearTimeout(searchTimer); state = readState(location.search); limit = 30; render(); });
window.addEventListener('storage', event => { if (event.key === KEYS.saved || event.key === null) { saved = loadSaved(); render(); } });
document.addEventListener('keydown', event => {
  const target = event.target;
  if (event.key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey && !event.repeat && !target.closest('input, textarea, select, button, [contenteditable="true"], dialog') && model) {
    event.preventDefault(); change({ view: 'headlines' }); $('search').focus();
  }
});
let printLimit;
window.addEventListener('beforeprint', () => { if (model) { printLimit = limit; limit = Infinity; renderHeadlines(); } });
window.addEventListener('afterprint', () => { if (model && printLimit !== undefined) { limit = printLimit; renderHeadlines(); } });
load();
