"""Exercise the actual bridge JavaScript with dependency-free browser mocks."""

from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch

from objectivity.browser_storage import browser_storage


HTML = Path(__file__).resolve().parents[1] / "objectivity" / "browser_component" / "index.html"
HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const {webcrypto} = require('crypto');
const source = fs.readFileSync(0, 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
const KEY = 'objectivity-ethics-assistant.progress.v1';
const store = new Map();
let queue = Promise.resolve();
const locks = {request(_name, _options, fn) {
  const result = queue.then(fn);
  queue = result.catch(() => {});
  return result;
}};
function mount(flags = {}) {
  const posts = [];
  const targets = [];
  const parent = {postMessage(message, target) {posts.push(message); targets.push(target);}};
  const status = {textContent: ''};
  let receive;
  const browser = {
    console, URL, TextEncoder, Uint8Array, crypto: webcrypto,
    document: {referrer: flags.referrer === undefined ? 'https://assistant.example/app' : flags.referrer, body: {style: {}}, getElementById() {return status;}},
    localStorage: {
      getItem(key) {
        if (flags.denied) throw Object.assign(new Error('blocked'), {name: 'SecurityError'});
        return store.has(key) ? store.get(key) : null;
      },
      setItem(key, value) {
        if (flags.quota) throw Object.assign(new Error('full'), {name: 'QuotaExceededError'});
        store.set(key, flags.badReadback ? value + 'damaged' : value);
      },
    },
    navigator: {locks: flags.noLocks ? undefined : locks},
    window: {parent, location: {origin: 'https://assistant.example'}, addEventListener(name, callback) {assert.equal(name, 'message'); receive = callback;}},
  };
  vm.runInNewContext(source, browser);
  return {
    posts, status, targets,
    async send(command, foreign = false, eventOrigin = 'https://assistant.example') {
      receive({source: foreign ? {} : parent, origin: eventOrigin, data: {type: 'streamlit:render', args: {command}}});
      for (let i = 0; i < 100; i++) {
        const found = posts.find(post => post.type === 'streamlit:setComponentValue' && post.value.id === command.id);
        if (found) return found.value;
        await new Promise(resolve => setImmediate(resolve));
      }
      return null;
    },
  };
}
async function test() {
TEST_BODY
}
test().then(() => process.stdout.write('PASS')).catch(error => {console.error(error); process.exitCode = 1;});
"""


class BrowserStorageWrapperTests(unittest.TestCase):
    def test_component_uses_stable_key_and_no_unacknowledged_success(self):
        command = {"id": "request", "op": "read"}
        with patch("objectivity.browser_storage._component", return_value=None) as component:
            self.assertIsNone(browser_storage(command))
            component.assert_called_once_with(command=command, key="objectivity_browser_storage", default=None)

    def test_only_dictionary_response_is_exposed(self):
        with patch("objectivity.browser_storage._component", return_value="not a response"):
            self.assertIsNone(browser_storage({"id": "request", "op": "read"}))
        result = {"id": "request", "op": "read", "status": "ok", "data": None, "token": None}
        with patch("objectivity.browser_storage._component", return_value=result):
            self.assertEqual(browser_storage({"id": "request", "op": "read"}), result)


@unittest.skipUnless(shutil.which("node"), "Node is needed only for optional bridge JavaScript unit checks")
class BrowserStorageJavascriptTests(unittest.TestCase):
    def run_js(self, body):
        result = subprocess.run(
            ["node", "-e", HARNESS.replace("TEST_BODY", body)],
            input=HTML.read_text(), text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "PASS")

    def test_missing_read_does_not_create_a_record(self):
        self.run_js("""
const frame = mount();
const result = await frame.send({id:'read', op:'read'});
assert.equal(result.status, 'ok'); assert.equal(result.data, null); assert.equal(result.token, null);
assert.equal(store.size, 0);
assert.equal(frame.posts[0].type, 'streamlit:componentReady');
""")

    def test_write_survives_component_remount_and_reopen(self):
        self.run_js("""
const saved = await mount().send({id:'write', op:'write', expected_token:null, data:'{"scenario":"A fictional case"}'});
assert.equal(saved.status, 'ok'); assert.ok(saved.token);
const reopened = await mount().send({id:'reopen', op:'read'});
assert.equal(reopened.token, saved.token); assert.equal(reopened.data, saved.data);
""")

    def test_duplicate_write_after_remount_is_idempotent(self):
        self.run_js("""
const command = {id:'write', op:'write', expected_token:null, data:'{"scenario":"fiction"}'};
const first = await mount().send(command);
const repeated = await mount().send(command);
assert.equal(repeated.status, 'ok'); assert.equal(repeated.token, first.token);
""")

    def test_compare_and_swap_prevents_stale_tab_overwrite(self):
        self.run_js("""
const first = await mount().send({id:'one', op:'write', expected_token:null, data:'one'});
const second = await mount().send({id:'two', op:'write', expected_token:first.token, data:'two'});
const stale = await mount().send({id:'stale', op:'write', expected_token:first.token, data:'stale'});
assert.equal(stale.status, 'conflict'); assert.equal(stale.data, 'two'); assert.equal(stale.token, second.token);
assert.equal(JSON.parse(store.get(KEY)).data, 'two');
""")

    def test_concurrent_tabs_cannot_both_overwrite_same_revision(self):
        self.run_js("""
const a = mount(), b = mount();
const results = await Promise.all([
 a.send({id:'a', op:'write', expected_token:null, data:'a'}),
 b.send({id:'b', op:'write', expected_token:null, data:'b'})
]);
assert.equal(results.filter(value => value.status === 'ok').length, 1);
assert.equal(results.filter(value => value.status === 'conflict').length, 1);
""")

    def test_clear_removes_content_and_has_a_new_token(self):
        self.run_js("""
const saved = await mount().send({id:'save', op:'write', expected_token:null, data:'sensitive fictional data'});
const command = {id:'clear', op:'clear', expected_token:saved.token};
const clear = await mount().send(command);
assert.equal(clear.status, 'ok'); assert.equal(clear.data, null); assert.notEqual(clear.token, saved.token);
assert.ok(!store.get(KEY).includes('sensitive fictional data'));
const duplicate = await mount().send(command);
assert.equal(duplicate.token, clear.token); assert.equal(duplicate.status, 'ok');
const read = await mount().send({id:'read', op:'read'});
assert.equal(read.data, null); assert.equal(read.token, clear.token);
""")

    def test_stale_clear_cannot_delete_newer_progress(self):
        self.run_js("""
const old = await mount().send({id:'old', op:'write', expected_token:null, data:'old'});
const newer = await mount().send({id:'new', op:'write', expected_token:old.token, data:'new'});
const clear = await mount().send({id:'clear', op:'clear', expected_token:old.token});
assert.equal(clear.status, 'conflict'); assert.equal(JSON.parse(store.get(KEY)).data, 'new');
""")

    def test_corruption_is_preserved_until_conditional_clear(self):
        self.run_js("""
store.set(KEY, '{broken');
const read = await mount().send({id:'read', op:'read'});
assert.equal(read.status, 'corrupt'); assert.ok(read.token.startsWith('corrupt:')); assert.equal(read.raw, '{broken');
assert.equal(store.get(KEY), '{broken');
const clear = await mount().send({id:'clear', op:'clear', expected_token:read.token});
assert.equal(clear.status, 'ok'); assert.equal(clear.data, null);
""")

    def test_blocked_storage_full_storage_and_missing_locks_never_claim_saved(self):
        self.run_js("""
for (const flags of [{denied:true}, {quota:true}, {noLocks:true}, {badReadback:true}]) {
 store.clear();
 const result = await mount(flags).send({id:JSON.stringify(flags), op:'write', expected_token:null, data:'fiction'});
 assert.equal(result.status, 'unavailable'); assert.equal(result.data, null);
}
""")

    def test_foreign_messages_are_ignored_and_duplicate_messages_do_not_loop(self):
        self.run_js("""
const frame = mount();
assert.equal(await frame.send({id:'foreign', op:'read'}, true), null);
const command = {id:'read', op:'read'};
await frame.send(command);
const count = frame.posts.length;
await frame.send(command);
assert.equal(frame.posts.length, count);
""")

    def test_oversized_payload_does_not_overwrite(self):
        self.run_js("""
const result = await mount().send({id:'large', op:'write', expected_token:null, data:'x'.repeat(2*1024*1024+1)});
assert.equal(result.status, 'unavailable'); assert.equal(store.size, 0);
""")

    def test_foreign_parent_cannot_read_data_even_with_matching_foreign_referrer(self):
        self.run_js("""
await mount().send({id:'save', op:'write', expected_token:null, data:'private fictional account'});
const hostile = mount({referrer:'https://hostile.example/embed'});
assert.equal(await hostile.send({id:'steal', op:'read'}, false, 'https://hostile.example'), null);
assert.ok(hostile.posts.every(message => message.type !== 'streamlit:setComponentValue'));
assert.ok(hostile.targets.every(target => target === 'https://assistant.example'));
""")

    def test_missing_referrer_does_not_allow_spoofed_origin_or_wildcard_responses(self):
        self.run_js("""
const frame = mount({referrer:''});
assert.equal(await frame.send({id:'spoof', op:'read'}, false, 'https://hostile.example'), null);
const legitimate = await frame.send({id:'legitimate', op:'read'});
assert.equal(legitimate.status, 'ok');
assert.ok(frame.targets.every(target => target === 'https://assistant.example'));
""")


if __name__ == "__main__":
    unittest.main()
