# IMU Fixed — no-slowdown clone + userscript right-click

Folder created for you so the original `maxurl/` checkout stays untouched.

## Files

| File | What it is | Size |
|---|---|---|
| `imu-fixed.user.js` | Full clone of upstream `userscript_smaller.user.js` (3.77 MB) + patches below. Install **this** instead of upstream if you want full 10k-site power + right-click. | ~3.79 MB |
| `imu-contextmenu-lite.user.js` | Standalone lightweight helper (~7 KB). No bundled rules, generic un-thumbnailing only (YT `maxresdefault`, `=s1024` avatars, `-200x200` stripping, `?w=` cleanup). Runs everywhere incl. YouTube with negligible cost. | ~7 KB |
| `build_patched.py` | Reproducible patch script: `python build_patched.py` rebuilds `imu-fixed.user.js` from `../maxurl/userscript_smaller.user.js`. | — |

Both pass `node --check`.

## Why YouTube Shorts was slow (verified in source)

1. **Parse cost on every page + every iframe.** `maxurl/manifest.json:23-29` injects `userscript.user.js` (7.4 MB) on `<all_urls>` with `all_frames:true`. Userscript header `userscript.meta.js:72-73,94` is `@include *` / `@match *://*/*` / `@run-at document-start`. V8 must parse it before YouTube's Polymer boot. Shorts icons (like/dislike/comments/title) hydrate late via XHR + images, so any main-thread block shows as "icons load slow".
2. **In-extension OFF ≠ unloaded.** `extension/popup.js:138` toggle only flips `imu_enabled` in storage. `src/userscript.ts:222 is_suspended()` only gates the `MutationObserver` (`156833,156881`), `do_mouseover` (`146728`) and redirect. It does **not** stop injection, `do_config()`'s hundreds of per-setting `getvalue` IPCs (`144741,145150`), or background `webRequestBlocking` listeners (`extension/background.js:562,904,919`) which add a sync round-trip to **every** image/media/XHR request on `<all_urls>`. `Ctrl+F5` doesn't help; browser-disable removes all three, hence instant.
3. **Userscript had no native right-click.** The `trigger_popup({is_contextmenu:true})` path (`src/userscript.ts:158193`) is only reachable via `chrome.runtime.onMessage type:"context_imu"` (`is_extension` branch) fed by `extension/background.js:1537 contextMenus.create`. The `mousedown` position tracker (`157587`) is also gated by `is_extension &&`. So userscript users could exclude YouTube but lost right-click enlarge.

## What the patch changes (`imu-fixed.user.js`)

1. **Header (manager-level, zero-cost on YT):**
   - `// @name` → `IMU Fixed - Image Max URL (no-slowdown + context menu)`
   - `// @run-at document-start` → `document-idle` (don't block first paint; redirect fires slightly later — acceptable for a context-menu-first build)
   - Added after `// @match *://*/*`:
     ```
     // @exclude *://*.youtube.com/*
     // @exclude *://*.youtu.be/*
     // @exclude *://*.youtube-nocookie.com/*
     // @exclude *://*.ytimg.com/*
     ```
     Tampermonkey/Violentmonkey then never injects on YouTube at all — same cost as browser-disabled.
2. **One-line upstream fix:** `if (is_extension && settings.extension_contextmenu` → `if ((is_extension || is_userscript) && settings.extension_contextmenu` (mirrors `src/userscript.ts:157587`). Lets the existing contextmenu position logic run for userscripts too.
3. **In-code SPA/disabled guard + custom menu (shim before final `do_config();`):**
   - `imuFixedShouldSkip()` returns true on `youtube.com|youtu.be|youtube-nocookie.com` (covers Shorts SPA navs where the manager doesn't re-inject) and on sync `GM_getValue("imu_enabled")===false`. When true we skip `do_config()` entirely (no settings storm, no observers) and stub `$$IMU_EXPORT$$`.
   - Custom floating panel (userscripts **cannot** add native context-menu entries — that's an extension-only API). On `contextmenu` (capture) we find `img/video/source/a`, store its URL, and show `Open larger image (IMU Fixed)` / `background tab` / `Copy URL` near the cursor. We deliberately don't `preventDefault()`, so your native menu still works.
   - Resolver order: full engine via `$$IMU_EXPORT$$` (= `bigimage_recursive`, `do_export` at `src/userscript.ts:142463`) with `iterations:8` + `GM_xmlhttpRequest` bridge and 8 s timeout → fallback to instant generic (`maxresdefault`, `=s1024`, size-suffix/query stripping). Generic needs no network.

## Install

1. Tampermonkey Dashboard → disable or remove upstream IMU (don't run both — they'd double-inject).
2. Tampermonkey → Utilities → Install from file → pick `imu-fixed.user.js` (full) . Optionally also install `imu-contextmenu-lite.user.js` on top — they coexist (different namespaces); lite is your fallback when full is skipped on YT/disabled.
3. Open a test image page (e.g. picsum), right-click an image → floating `IMU Fixed` panel → `Open larger image`.
4. Open `https://www.youtube.com/shorts/` → icons should load instantly (no injection: check Tampermonkey badge shows 0 running scripts).

To re-allow YouTube in the full build: delete the four `// @exclude` lines in `imu-fixed.user.js` header and reinstall. The in-code `imuFixedShouldSkip()` will still skip heavy init on YT but show no panel there — edit its regex if you want the panel on YT too.

## Rebuild

```powershell
python "C:\AITools\.Visual Studio Code\Image Max URL\imu-fixed\build_patched.py"
node --check "C:\AITools\.Visual Studio Code\Image Max URL\imu-fixed\imu-fixed.user.js"
```

Re-run after `git -C ../maxurl pull`.

## Limitations (honest)

- Parse cost off YouTube only via `@exclude`. On non-excluded sites with `imu_enabled=false` we still pay V8 parse of ~3.8 MB once per page (unavoidable in a single-file build); we skip everything after that.
- Custom panel is not a native menu entry. If you need a true native `Try to find larger image` entry, that requires the extension (`chrome.contextMenus` in `extension/background.js`) — use the extension outside YouTube, or set its Chrome Site access to `On specific sites` excluding `youtube.com`.
- Full-engine resolve needs `GM_xmlhttpRequest` + `@connect *`; some hardened managers block cross-origin — then generic fallback opens.
