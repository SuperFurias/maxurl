# IMU Fixed Extension — unpacked build (no Shorts slowdown)

Built at the fork root (manifest 2026.6.0 → **2026.6.6**). Load `imu-fixed-extension/` unpacked; the root checkout stays pristine apart from the committed patches.

## What changed and why

**1. `manifest.json` — no static excludes, no iframes, no paint-blocking**
- No `exclude_matches`: static excludes can't change without a reinstall (MV2 has no dynamic content-script registration), so per-site control is a **runtime host blocklist** instead (section 5). YouTube works out of the box; excluding it again is one line in options, no rebuild.
- `all_frames`: `true` → `false` — upstream injected into every ad/chat/embed iframe on every page. Main frames (where you actually browse) are unaffected.
- `run_at`: added `"document_idle"` (was default-idle implicit; now explicit so a future upstream `document_start` can't regress first paint).
- `background.scripts[1]` / `content_scripts[0].js`: `userscript.user.js` → byte-identical `userscript-bg.js` / `userscript.user.js`. Chrome rejects non-`.js` background scripts (`Invalid background script mime type`); content script renamed for the same reason.
- `extension/options.html`: its `<script src="../userscript.user.js">` (the whole options UI is rendered by the engine itself via `do_options()`) now points at `../userscript.user.js` plus the `imu-fixed-options.js` companion. Missing file = the infinite-"loading" options page.
- `name` kept as **`Image Max URL`** on purpose: `src/userscript.ts:check_if_extension()` gates extension behavior on that exact string. Renaming would silently demote the build to userscript-mode.
- Native right-click entry (`Try to find larger image (IMU)`, `extension/background.js:create_contextmenu`) is untouched — extensions keep the real context menu, unlike userscripts.

**2. `extension/background.js` — webRequest listeners follow the enable toggle**
- Upstream registers blocking listeners on `<all_urls>` for `image/media/xhr/main_frame/sub_frame` at load (`onBeforeSendHeaders`, `onHeadersReceived`, `onResponseStarted`) and never removes them. Every Shorts icon/avatar/API call paid a sync extension round-trip even with `imu_enabled=false`.
- Patch: `imuFixedEnabled` cache + `imuFixedSetWebRequest(on)` add/remove. Wired into the two existing `imu_enabled` code paths — initial `on_ready(get_option("imu_enabled"))` and live `chrome.storage.onChanged` — alongside `update_browseraction_enabled`.
- Defense-in-depth early returns (`if (!imuFixedEnabled) return {};` / `return;`) at the top of both blocking listeners in case a request is already in flight during the toggle.
- `onResponseStarted`'s anonymous callback was named (`onResponseStarted_listener`) so it can be removed. No other behavior changed.

**3. Console-noise fixes (v2–v5) — same behavior, fewer scary red lines**
- `chrome.tabs.sendMessage` fan-outs (settings broadcast, popupaction forward, `broadcast_message`, download progress, `context_imu` forward, all-tabs query helper) now skip `chrome://`, `chrome-extension://`, `edge://`, `about:`, webstore/gallery URLs and demote missing-receiver `lastError` to `debug()` instead of `console.error`. Blocklisted-host tabs have no content script by design, so messaging them was pure noise.
- The install-time triple was proven by stack trace to come from `hotload()` (fixed in v4, same treatment); the v3/v5 fan-out guards cover the remaining senders. Real errors still reach `handle_error()`.
- `storage.set` paths (`set_option`, `setvalue` handler) now use lastError-checked callbacks: quota errors become one `console.warn`, never `Unchecked runtime.lastError`.
- `Notifications not allowed` warn removed: `notifications` is an *optional* permission (`manifest.json:66-71`), so its absence is normal; the handler now returns silently.

**5. Disabled websites = native Rules row**
- `imu_fixed_disabled_hosts` is registered in `settings_meta` (`category: "rules"`, `type: "textarea"`): **Rules tab → Disabled websites**, one host per line, subdomains match automatically, empty runs everywhere. It renders, validates, imports/exports, reverts, and tab-filters like every other row — no bolted-on panel.
- Enforcement is two-layer: the content script fetches only `imu_enabled` + the list first (single IPC) and bails before the hundreds-setting storm, observers, and listeners; the background additionally skips blocklisted request hosts in both blocking `webRequest` listeners, live, even while globally enabled.
- Honest residual: a blocklisted host still pays one V8 parse + one IPC per navigation (MV2 content scripts can't be un-injected at runtime), and already-open tabs apply the list on reload — request handling, however, stops immediately.
**4. Popup spawns centered, natively configurable**
- Upstream default `mouseover_position` is `"cursor"` (`src/userscript.ts:15880`), so the enlarged popup anchors at the mouse — left side when your cursor is left, exactly like your screenshot.
- This build flips the default to `"center"` (`Popup position → Page middle`, same switch as `src/userscript.ts:18119`) in both shipped `.js` copies (the background copy never renders popups, so it's a no-op there).
- One caveat: if your synced settings already stored `"cursor"` (options UI was once opened/saved with it), the stored value wins over the new default. Then flip it once manually: IMU options → **Popup** section → **Popup position** → **Page middle**. Fresh profiles get center automatically.

**6. Reset to defaults + dark-mode revert fix**
- **Reset to defaults** button sits right of Export (`extension/imu-fixed-options.js`). Tab switches re-render the options DOM and destroy foreign nodes, so a MutationObserver re-inserts it whenever it goes missing. It confirms, clears `chrome.storage.sync` + `local`, and reloads; the background's `onChanged` path is clear-safe (undefined `newValue` falls back to defaults instead of throwing in `JSON.parse`).
- Dark mode: `update_dark_mode()` flips the *live* default to `true` on dark systems via `set_default_value` without storing anything, while the row compared against the baked default (`false`) — so follow-system looked modified and offered a ⮌ revert that would have cemented light mode. `orig_settings` now mirrors the flip, so follow-system counts as default; explicit user choices still flag and revert normally.
- Rule toggles ("Possibly upscaled images", "Rules using brute-force", and siblings): same defect class, different mechanism. The baked literal says `false`, but the `option_to_problems` loop (`src/userscript.ts:20386`) flips them to `true` at load unless excluded — *after* the `orig_settings` snapshot. So every fresh/reset profile showed them ON + flagged, and no reset could turn them "off" because the loop re-enables them on every load **by design** (these rule families ship enabled). The mirror fix makes fresh == ON + unflagged; reverting now means "back to on". To actually keep them off, toggle them off — that state flags correctly and persists.
- Deliberate deviation: **Rules using brute-force ships OFF** in this build. Upstream enables it despite its own "rate limiting or IP bans" warning; binary-searching a stranger's server without explicit opt-in is not a sane default. The warning text is untouched, the row still works, and a stored ON still wins (your choice is respected). Consequence: Deezer-style originals that need brute-forcing won't resolve until you opt in. "Possibly upscaled images" carries no such warning and stays at the upstream default (on).

## Install (Chromium)

1. Disable/remove upstream Image Max URL (don't run both — double content scripts + double webRequest handlers).
2. Drag&drop `build/ImageMaxURL_crx3.crx` onto `chrome://extensions` (Developer mode on) and click **Install**. Alternative: Developer mode → **Load unpacked** → select `imu-fixed-extension/`.
3. Right-click images elsewhere → `Try to find larger image (IMU)` still works. Open `youtube.com/shorts` → icons instant.
4. Toggle test: IMU popup → disable → Shorts stays fast AND other sites stop paying request overhead (verified: listeners removed; icon shows `(disabled)`).
5. After loading, reload open tabs once so the new content scripts take effect.

## Your pasted errors, one by one

| Error | Verdict | Status in 2026.6.6 |
|---|---|---|
| `Manifest version 2 is deprecated…` | Warning, not error. Upstream is MV2; Chromium sideload still installs the MV2 CRX (store distribution is gone). A real MV3 migration (`webRequestBlocking` → `declarativeNetRequest`, persistent background → service worker) is a separate project — the header-rewriting core can't be ported 1:1. | Documented, not patchable here |
| `Invalid background script mime type for 'background.scripts[1]'` | **Fatal, fixed.** Chrome won't load `.user.js` as a background script. | Fixed: `userscript-bg.js` / `userscript-content.js` |
| Options page stuck on "loading" forever | The options UI is rendered by the engine itself, so if the engine file is missing `do_options()` never runs. | Fixed: points at `../userscript.user.js` plus the companion script |
| `Notifications not allowed` | Benign upstream noise (optional permission absent). | Silenced |
| `cannot be scripted due to ExtensionsSettings policy` / `extensions gallery cannot be scripted` / `tab was closed` | Proven by stack trace (`handle_error` ← `hotload`'s `executeScript` callback): on install, `hotload()` injects the engine into every open tab; webstore/gallery/policy-blocked/closed tabs fail by design. | Fixed in v4 (unscriptable URLs skipped, rest demoted to `debug()`); the v3 fan-out guards cover the remaining senders |
| `message port closed before a response was received` ×40 | Mostly install-transient (ports die while the background restarts) plus no-receiver tabs. Clears after reload. | Reduced (guarded fan-outs); remainder is transient |
| `message port closed…` from content with `extension_error_handler` stack | Content `set_value()` and `redirect` always pass response callbacks, but the background never answered those two types — so *every* settings write and *every* redirect logged it. | Fixed: both now `respond({})` with `return true` (full sender audit: all other callback senders already had responders) |
| `Could not establish connection. Receiving end does not exist` | No content script in that tab (blocklisted host, `chrome://`, unloaded tab). | Swallowed to `debug()` |
| `exceeds MAX_WRITE_OPERATIONS_PER_MINUTE quota` | Write storm on fresh install: every injected tab upgrades/persists settings at once against `chrome.storage.sync` (~120 writes/min limit). Settles after first run; failed writes only delay that tab's settings sync. | Checked callback + single warn; storm itself is upstream behavior |

## YouTube / heavy sites: use Rules > Disabled websites

Recommended: add `https://www.youtube.com/` under Rules > Disabled websites in the options page (comma-separated; matches the domain and its subdomains).

Why this happens: this is upstream behavior, not a fork regression — in fact it is why this fork exists. After years on the original extension: with it enabled, YouTube Shorts icons (comments, title, likes, etc.) take a very long time to load while scrolling. The extension injects its content script on `<all_urls>` in every frame and keeps blocking `webRequest` listeners on all traffic. On most pages that cost is invisible, but YouTube (especially Shorts) hydrates icons and the player late via XHR + images while the main thread is contended, so it shows up as laggy or broken UI. Per-site disable unloads the content script and removes the request listeners for those hosts while the extension keeps working everywhere else.

That list exists precisely for the few sites that don't behave with the extension loaded — if another heavy SPA or media site misbehaves, add its domain the same way instead of toggling the whole extension off.

## Rebuild

```powershell
# from the fork root:
python imu-fixed/build_extension.py
node --check imu-fixed-extension/extension/background.js
```

Re-run after pulling upstream (then re-apply `imu-fixed/apply_source_patches.py`
if the patches were reset). (`imu-fixed-extension/README.md` is copied from
`imu-fixed/extension-README.md` on each build, so edit that file.)

## Honest limitations

- Background page (`persistent:true`) still parses the full rules **once** at browser start. One-time cost, not per-page; MV2 gives no way around it without splitting the bundle.
- MV2 content scripts can't be un-injected at runtime, so a blocklisted host still pays one V8 parse + one 2-key IPC per navigation before the fast-bail — versus the old hundreds-key storm plus observers plus listeners. Toggle-off behaves the same way everywhere via the same path.
- With the default empty blocklist and the toggle on, YouTube pays the full engine cost again (your choice — that's what "still works on YouTube" costs). Toggle off (listeners detach globally) or add the hosts to Rules → Disabled websites to get the fast path back.
