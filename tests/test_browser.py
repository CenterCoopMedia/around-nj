"""Browser checks against snapshot.html. Run from this branch, not master."""
import csv
import io
import json
import os
import shutil
import threading
import unittest
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

class DeskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/'
        cls.pw = sync_playwright().start()
        executable = os.environ.get('CHROMIUM_PATH') or shutil.which('chromium')
        cls.browser = cls.pw.chromium.launch(**({'executable_path': executable} if executable else {}))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 1440, 'height': 1050}, color_scheme='light', accept_downloads=True)
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.goto(self.url)
        self.page.locator('#story-list .story').first.wait_for()

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [], 'Uncaught browser errors')

    def search(self, text):
        self.page.fill('#search', text)
        self.page.wait_for_timeout(180)

    def snapshot(self):
        return self.page.evaluate("async () => { const {parseSnapshot} = await import('./assets/desk-core.mjs'); const data = parseSnapshot(await (await fetch('./snapshot.html')).text()); return data; }")

    def test_counts_use_embedded_records(self):
        model = self.snapshot()
        self.assertEqual(int(self.page.inner_text('#all-count')), len(model['stories']))
        self.assertEqual(int(self.page.inner_text('#partner-count')), sum(s['partner'] for s in model['stories']))
        self.assertEqual(self.page.locator('.story').count(), min(30, len(model['stories'])))
        self.assertIn('not live', self.page.inner_text('.stamp-label'))

    def test_partner_source_date_filters(self):
        self.page.click('[data-scope="partners"]')
        self.assertEqual(self.page.locator('.story .partner-key').count(), self.page.locator('.story').count())
        self.page.select_option('#source', 'montclairlocal.news')
        self.assertTrue(all('Montclair Local' in text for text in self.page.locator('.source-link').all_text_contents()))
        dates = self.page.locator('#day option').evaluate_all('(nodes) => nodes.map(n => n.value).filter(Boolean)')
        self.page.select_option('#day', dates[0])
        self.assertIn('matching your filters', self.page.inner_text('#result-count'))

    def test_search_supports_spaces_and_no_results(self):
        self.search('school ')
        self.assertEqual(self.page.input_value('#search'), 'school ')
        self.search('"school"')
        self.assertGreater(self.page.locator('.story').count(), 0)
        self.search('no-such-headline-zzzz')
        self.assertTrue(self.page.is_visible('#empty'))
        self.assertTrue(self.page.is_disabled('#export'))
        self.page.click('#empty-reset')
        self.assertGreater(self.page.locator('.story').count(), 0)

    def test_save_persists_and_remove_restores_focus(self):
        self.page.locator('.save-button').first.click()
        self.assertEqual(self.page.inner_text('#saved-count'), '1')
        self.page.reload()
        self.page.locator('.story').first.wait_for()
        self.page.click('[data-scope="saved"]')
        self.assertEqual(self.page.locator('.story').count(), 1)
        self.page.locator('.save-button').first.click()
        self.assertEqual(self.page.inner_text('#saved-count'), '0')
        self.assertTrue(self.page.is_visible('#empty'))
        self.assertEqual(self.page.evaluate('document.activeElement.id'), 'results-title')

    def test_saved_story_survives_a_new_snapshot(self):
        story = {'url': 'https://example.org/older', 'title': 'An earlier saved headline', 'source': 'Old newsroom', 'partner': False, 'day': '2026-08-01', 'timestamp': 1785585600000, 'when': 'Aug 1, 2026'}
        self.page.evaluate('(story) => localStorage.setItem("around-nj.saved.v1", JSON.stringify([story]))', story)
        self.page.reload()
        self.page.locator('.story').first.wait_for()
        self.page.click('[data-scope="saved"]')
        self.assertIn('An earlier saved headline', self.page.inner_text('#story-list'))
        self.assertIn('earlier snapshots', self.page.inner_text('#saved-note'))

    def test_compact_theme_and_keyboard(self):
        self.page.click('#density')
        self.assertEqual(self.page.get_attribute('#density', 'aria-pressed'), 'true')
        self.page.click('#theme')
        self.assertEqual(self.page.get_attribute('html', 'data-theme'), 'dark')
        self.page.reload()
        self.page.locator('.story').first.wait_for()
        self.assertEqual(self.page.get_attribute('html', 'data-theme'), 'dark')
        self.assertEqual(self.page.get_attribute('#density', 'aria-pressed'), 'true')
        self.page.locator('body').click(position={'x': 2, 'y': 2})
        self.page.keyboard.press('/')
        self.assertEqual(self.page.evaluate('document.activeElement.id'), 'search')
        self.page.keyboard.type('town / school')
        self.assertIn('/', self.page.input_value('#search'))

    def test_directory_filters_and_browse(self):
        self.page.click('.page-tabs [data-view-link="newsrooms"]')
        self.page.fill('#room-search', 'Montclair Local')
        self.assertEqual(self.page.locator('.room').count(), 1)
        self.page.locator('.room button').click()
        self.assertTrue(self.page.is_visible('#headlines'))
        self.assertEqual(self.page.input_value('#source'), 'montclairlocal.news')
        self.page.click('.page-tabs [data-view-link="newsrooms"]')
        self.page.fill('#room-search', '')
        self.page.select_option('#room-filter', 'missing')
        self.assertTrue(all('No feed listed' in text for text in self.page.locator('.room-status').all_text_contents()))

    def test_about_reports_difference_and_source_fallback(self):
        model = self.snapshot()
        self.page.click('.page-tabs [data-view-link="about"]')
        self.assertIn(str(len(model['stories'])), self.page.inner_text('#coverage-note'))
        self.assertIn('not a live health check', self.page.locator('#newsrooms').text_content())
        self.assertEqual(self.page.get_attribute('.about-view a', 'href'), 'snapshot.html')
        self.assertEqual(self.page.locator('#original-stats div').count(), len(model['stats']))

    def test_url_deep_link_back_and_forward(self):
        self.search('school')
        self.page.click('[data-scope="partners"]')
        url = self.page.url
        self.page.click('.page-tabs [data-view-link="newsrooms"]')
        self.page.go_back()
        self.assertTrue(self.page.is_visible('#headlines'))
        self.assertEqual(self.page.input_value('#search'), 'school')
        other = self.context.new_page()
        other.goto(url)
        other.locator('.story').first.wait_for()
        self.assertEqual(other.get_attribute('[data-scope="partners"]', 'aria-pressed'), 'true')
        self.assertEqual(other.input_value('#search'), 'school')
        other.close()

    def test_export_includes_every_match_not_just_page(self):
        model = self.snapshot()
        with self.page.expect_download() as event:
            self.page.click('#export')
        download = event.value
        rows = list(csv.reader(io.StringIO(Path(download.path()).read_text(encoding='utf-8-sig'))))
        self.assertEqual(len(rows) - 1, len(model['stories']))
        self.assertIn('URL', rows[0])
        self.assertTrue(all(row[-1].startswith(('https://', 'http://')) for row in rows[1:]))

    def test_more_and_print_include_all_results(self):
        total = int(self.page.inner_text('#all-count'))
        if total > 30:
            self.page.click('#load-more')
            self.assertEqual(self.page.locator('.story').count(), min(total, 60))
            self.assertEqual(self.page.evaluate('document.activeElement.tagName'), 'A')
        previous = self.page.locator('.story').count()
        self.page.evaluate('window.dispatchEvent(new Event("beforeprint"))')
        self.assertEqual(self.page.locator('.story').count(), total)
        self.page.evaluate('window.dispatchEvent(new Event("afterprint"))')
        self.assertEqual(self.page.locator('.story').count(), previous)

    def test_clipboard_fallback_and_private_scope(self):
        self.page.evaluate('Object.defineProperty(navigator, "clipboard", {value: {writeText: () => Promise.reject(new Error("denied"))}, configurable: true})')
        self.page.locator('.save-button').first.click()
        self.page.click('[data-scope="saved"]')
        self.page.click('#share')
        self.assertTrue(self.page.is_visible('#copy-dialog'))
        self.assertNotIn('scope=saved', self.page.input_value('#copy-value'))
        self.page.keyboard.press('Escape')
        self.assertFalse(self.page.is_visible('#copy-dialog'))

    def test_storage_failure_and_corruption_are_nonfatal(self):
        self.page.add_init_script('Object.defineProperty(window, "localStorage", {get() {throw new DOMException("denied", "SecurityError")}})')
        self.page.reload()
        self.page.locator('.story').first.wait_for()
        self.page.locator('.save-button').first.click()
        self.assertEqual(self.page.inner_text('#saved-count'), '1')
        self.assertTrue(self.page.is_visible('#storage-note'))

    def test_corrupt_saved_json_is_ignored(self):
        self.page.evaluate('localStorage.setItem("around-nj.saved.v1", "{broken-json")')
        self.page.reload()
        self.page.locator('.story').first.wait_for()
        self.assertEqual(self.page.inner_text('#saved-count'), '0')

    def test_unsafe_snapshot_markup_does_not_execute(self):
        html = '''<p class="meta">Friday, September 18, 2026, 12:01 PM EDT</p><ul class="stories"><li class="is-partner"><a href="https://example.org/a">&lt;img src=x onerror=alert(1)&gt;</a><span class="src">Safe source</span><span class="when">Fri 9:00 AM</span></li><li><a href="javascript:alert(1)">Unsafe URL</a><span class="src">Bad</span></li></ul>'''
        self.page.route('**/snapshot.html', lambda route: route.fulfill(status=200, content_type='text/html', body=html))
        self.page.reload()
        self.page.locator('.story').first.wait_for()
        self.assertEqual(self.page.locator('.story').count(), 1)
        self.assertEqual(self.page.locator('.story img').count(), 0)
        self.assertIn('<img', self.page.inner_text('.story h3'))

    def test_snapshot_failure_has_retry_and_reading_link(self):
        self.page.route('**/snapshot.html', lambda route: route.fulfill(status=503, body='Unavailable'))
        self.page.reload()
        self.page.get_by_role('button', name='Try again').wait_for()
        self.assertEqual(self.page.get_attribute('#load-state a', 'href'), 'snapshot.html')
        self.page.unroute('**/snapshot.html')
        self.page.get_by_role('button', name='Try again').click()
        self.page.locator('.story').first.wait_for()
        self.assertFalse(self.page.is_visible('#load-state'))

    def test_empty_snapshot_has_fallback(self):
        self.page.route('**/snapshot.html', lambda route: route.fulfill(status=200, content_type='text/html', body='<h1>No stories</h1>'))
        self.page.reload()
        self.page.get_by_role('button', name='Try again').wait_for()
        self.assertTrue(self.page.is_visible('#load-state a'))

    def test_no_javascript_has_original_reading_page(self):
        context = self.browser.new_context(java_script_enabled=False)
        page = context.new_page()
        page.goto(self.url)
        self.assertTrue(page.is_visible('noscript a'))
        page.locator('noscript a').click()
        self.assertGreater(page.locator('ul.stories li a').count(), 0)
        context.close()

    def test_reflow_all_views_and_reduced_motion(self):
        for width in [320, 375, 390, 768, 1024, 1440, 1920]:
            self.page.set_viewport_size({'width': width, 'height': 1000})
            for view in ['headlines', 'newsrooms', 'about']:
                self.page.click(f'.page-tabs [data-view-link="{view}"]')
                with self.subTest(width=width, view=view):
                    self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), width + 1)
        self.page.emulate_media(reduced_motion='reduce')
        self.assertEqual(self.page.locator('#theme').evaluate('(el) => getComputedStyle(el).transitionDuration'), '0s')

    def test_native_navigation_links_open_the_requested_view(self):
        self.page.click('.page-tabs [data-view-link="about"]')
        url = self.page.get_attribute('.page-tabs [data-view-link="headlines"]', 'href')
        other = self.context.new_page()
        other.goto(url)
        other.locator('.story').first.wait_for()
        self.assertTrue(other.is_visible('#headlines'))
        other.close()

    def test_invalid_saved_dates_and_theme_are_nonfatal(self):
        stories = [{'url': f'https://example.org/old-{i}', 'title': 'Saved headline', 'source': 'Old newsroom', 'day': day, 'timestamp': None, 'when': 'Time not supplied'} for i, day in enumerate(['2026-99-40', '2026-02-31'])]
        self.page.evaluate('(stories) => { localStorage.setItem("around-nj.saved.v1", JSON.stringify(stories)); localStorage.setItem("around-nj.theme.v1", "corrupted"); }', stories)
        self.page.reload()
        self.page.locator('.story').first.wait_for()
        self.page.click('[data-scope="saved"]')
        self.assertEqual(self.page.locator('.story').count(), 2)
        self.assertEqual(self.page.locator('#day option').count(), 1)
        self.page.emulate_media(color_scheme='dark')
        self.page.wait_for_function('document.documentElement.dataset.theme === "dark"')

    def test_capture_previews(self):
        artifacts = ROOT / 'artifacts'
        artifacts.mkdir(exist_ok=True)
        self.page.screenshot(path=str(artifacts / 'desktop.png'), full_page=False, animations='disabled')
        self.page.click('#theme')
        self.page.screenshot(path=str(artifacts / 'desktop-dark.png'), full_page=False, animations='disabled')
        self.page.click('#theme')
        self.page.set_viewport_size({'width': 390, 'height': 1000})
        self.page.screenshot(path=str(artifacts / 'mobile.png'), full_page=False, animations='disabled')

if __name__ == '__main__':
    unittest.main(verbosity=2)
