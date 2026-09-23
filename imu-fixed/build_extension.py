#!/usr/bin/env python3
"""Assemble imu-fixed-extension/ (unpacked Chrome extension) from maxurl/.

Patches (see README for rationale):
 1. manifest.json: content_scripts += exclude_matches (youtube), all_frames=false,
    run_at=document_idle, version bump. NAME KEPT as "Image Max URL" because
    src/userscript.ts check_if_extension() gates on that exact name.
 2. extension/background.js: gate the 3 blocking webRequest listeners behind
    imu_enabled (cached). When disabled we removeListener, so YouTube requests
    no longer round-trip through the extension. Defense-in-depth early-returns
    remain in case of races.
"""
import json, pathlib, re, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent  # fork root
SRC = ROOT  # upstream tree lives at the fork root
OUT = ROOT / "imu-fixed-extension"

YOUTUBE_EXCLUDES = []  # retired: static manifest excludes replaced by the
# runtime host blocklist (options page -> imu_fixed_disabled_hosts). Kept as
# an empty list so any leftover reference is a no-op, not a silent re-exclude.

# ---------------------------------------------------------------- manifest
def patch_manifest():
    raw = (SRC / "manifest.json").read_bytes().decode("utf-8")
    data = json.loads(raw)
    assert data["name"] == "Image Max URL", data["name"]
    cs = data["content_scripts"][0]
    # No static exclude_matches: the runtime host blocklist (options page)
    # decides per-site loading, so YouTube and everything else keeps working
    # until the user excludes them. (Static excludes can't change without a
    # reinstall; MV2 offers no dynamic content-script registration.)
    cs.pop("exclude_matches", None)
    cs["all_frames"] = False
    cs["run_at"] = "document_idle"
    # NOTE: filenames use .js (not .user.js): Chrome refuses non-.js background
    # scripts ("Invalid background script mime type"). Content script renamed too.
    cs["js"] = ["userscript-content.js"]
    data["background"]["scripts"] = ["extension/background.js", "userscript-bg.js"]
    old_ver = data.get("version", "2026.6.0")
    data["version"] = "2026.6.6"
    (OUT / "manifest.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return old_ver, data["version"]

# --------------------------------------------------------------- background
GATING_PRELUDE = r"""
/* ==== IMU-FIXED: webRequest gating (no-slowdown when disabled) ====
 * Upstream registers blocking webRequest listeners on <all_urls> at load and
 * never removes them, so every image/media/XHR (e.g. YouTube Shorts icons,
 * avatars, youtubei API) pays a sync extension round-trip even with
 * imu_enabled=false. We cache the flag and add/remove the listeners.
 */
var imuFixedEnabled = true;
var imuFixedWebRequestOn = false;
// Pages Chrome never lets us script: messaging them only produces
// "Receiving end does not exist" / "cannot be scripted" console noise.
var imuFixedUnscriptableUrl = function(url) {
  return /^(chrome|chrome-extension|edge|about|moz-extension):/.test(url) ||
    /^https?:\/\/(chrome\.google\.com|chromewebstore\.google\.com|microsoftedge\.microsoft\.com|addons\.mozilla\.org)\//.test(url);
};
var imuFixedQuotaWarned = false;
var imuFixedNoteWriteError = function(where) {
  if (chrome.runtime.lastError) {
    if (!imuFixedQuotaWarned || chrome.runtime.lastError.message.indexOf("quota") < 0) {
      console.warn(where + ": " + chrome.runtime.lastError.message);
      if (chrome.runtime.lastError.message.indexOf("quota") >= 0) imuFixedQuotaWarned = true;
    }
  }
};
"""

def patch_background():
    raw = (SRC / "extension" / "background.js").read_bytes().decode("utf-8", errors="replace")
    raw = raw.replace("\r", "")
    orig_len = len(raw)

    # 1) prelude after the state vars block
    anchor = "var notifications = {};"
    assert anchor in raw, "anchor vars not found"
    raw = raw.replace(anchor, anchor + "\n" + GATING_PRELUDE, 1)

    # 2) onBeforeSendHeaders: wrap registration in add/remove fns
    old_bsh = """try {
\tchrome.webRequest.onBeforeSendHeaders.addListener(
\t\tonBeforeSendHeaders_listener, onBeforeSendHeaders_filter,
\t\t['blocking', 'requestHeaders', 'extraHeaders']
\t);
} catch (e) {
\tchrome.webRequest.onBeforeSendHeaders.addListener(
\t\tonBeforeSendHeaders_listener, onBeforeSendHeaders_filter,
\t\t['blocking', 'requestHeaders']
\t);
}"""
    # file may use tabs or spaces; normalize via regex
    m = re.search(r"try\s*\{\s*\n\s*chrome\.webRequest\.onBeforeSendHeaders\.addListener\(\s*\n\s*onBeforeSendHeaders_listener,\s*onBeforeSendHeaders_filter,\s*\n\s*\['blocking',\s*'requestHeaders',\s*'extraHeaders'\]\s*\n\s*\);\s*\n\}\s*catch\s*\(e\)\s*\{\s*\n\s*chrome\.webRequest\.onBeforeSendHeaders\.addListener\(\s*\n\s*onBeforeSendHeaders_listener,\s*onBeforeSendHeaders_filter,\s*\n\s*\['blocking',\s*'requestHeaders'\]\s*\n\s*\);\s*\n\}", raw)
    assert m, "onBeforeSendHeaders registration block not found"
    raw = raw[:m.start()] + """function imuFixedAddBeforeSendHeaders() {
\ttry {
\t\tchrome.webRequest.onBeforeSendHeaders.addListener(
\t\t\tonBeforeSendHeaders_listener, onBeforeSendHeaders_filter,
\t\t\t['blocking', 'requestHeaders', 'extraHeaders']
\t\t);
\t} catch (e) {
\t\tchrome.webRequest.onBeforeSendHeaders.addListener(
\t\t\tonBeforeSendHeaders_listener, onBeforeSendHeaders_filter,
\t\t\t['blocking', 'requestHeaders']
\t\t);
\t}
}
function imuFixedRemoveBeforeSendHeaders() {
\ttry { chrome.webRequest.onBeforeSendHeaders.removeListener(onBeforeSendHeaders_listener); } catch (e) {}
}""" + raw[m.end():]

    # 3) onHeadersReceived registration -> add/remove fns
    m2 = re.search(r"try\s*\{\s*\n\s*chrome\.webRequest\.onHeadersReceived\.addListener\(onHeadersReceived,\s*\{\s*\n\s*urls:\s*\['<all_urls>'\],\s*\n\s*types:\s*received_types\s*\n\s*\},\s*\['blocking',\s*'responseHeaders',\s*'extraHeaders'\]\);\s*\n\}\s*catch\s*\(e\)\s*\{\s*\n\s*chrome\.webRequest\.onHeadersReceived\.addListener\(onHeadersReceived,\s*\{\s*\n\s*urls:\s*\['<all_urls>'\],\s*\n\s*types:\s*received_types\s*\n\s*\},\s*\['blocking',\s*'responseHeaders'\]\);\s*\n\}", raw)
    assert m2, "onHeadersReceived registration block not found"
    raw = raw[:m2.start()] + """function imuFixedAddHeadersReceived() {
\ttry {
\t\tchrome.webRequest.onHeadersReceived.addListener(onHeadersReceived, {
\t\t\turls: ['<all_urls>'],
\t\t\ttypes: received_types
\t\t}, ['blocking', 'responseHeaders', 'extraHeaders']);
\t} catch (e) {
\t\tchrome.webRequest.onHeadersReceived.addListener(onHeadersReceived, {
\t\t\turls: ['<all_urls>'],
\t\t\ttypes: received_types
\t\t}, ['blocking', 'responseHeaders']);
\t}
}
function imuFixedRemoveHeadersReceived() {
\ttry { chrome.webRequest.onHeadersReceived.removeListener(onHeadersReceived); } catch (e) {}
}""" + raw[m2.end():]

    # 4) onResponseStarted anonymous -> named + add/remove fns
    m3 = re.search(r"chrome\.webRequest\.onResponseStarted\.addListener\(function\(details\)\s*\{", raw)
    assert m3, "onResponseStarted registration not found"
    raw = raw[:m3.start()] + "var onResponseStarted_listener = function(details) {" + raw[m3.end():]
    # find the closing of that call: "}, {\n\turls: ['<all_urls>'],\n\ttypes: ['xmlhttprequest', 'main_frame', 'sub_frame']\n}, ['responseHeaders']);"
    m4 = re.search(r"\},\s*\{\s*\n\s*urls:\s*\['<all_urls>'\],\s*\n\s*types:\s*\['xmlhttprequest',\s*'main_frame',\s*'sub_frame'\]\s*\n\},\s*\['responseHeaders'\]\);", raw)
    assert m4, "onResponseStarted filter block not found"
    raw = raw[:m4.start()] + """};
var imuFixedResponseStartedFilter = {
\turls: ['<all_urls>'],
\ttypes: ['xmlhttprequest', 'main_frame', 'sub_frame']
};
function imuFixedAddResponseStarted() {
\ttry { chrome.webRequest.onResponseStarted.addListener(onResponseStarted_listener, imuFixedResponseStartedFilter, ['responseHeaders']); } catch (e) {}
}
function imuFixedRemoveResponseStarted() {
\ttry { chrome.webRequest.onResponseStarted.removeListener(onResponseStarted_listener); } catch (e) {}
}""" + raw[m4.end():]

    # 5) central toggler (defined once, after the add/remove fns)
    toggler = """
function imuFixedSetWebRequest(on) {
\tif (on && !imuFixedWebRequestOn) {
\t\timuFixedAddBeforeSendHeaders();
\t\timuFixedAddHeadersReceived();
\t\timuFixedAddResponseStarted();
\t\timuFixedWebRequestOn = true;
\t} else if (!on && imuFixedWebRequestOn) {
\t\timuFixedRemoveBeforeSendHeaders();
\t\timuFixedRemoveHeadersReceived();
\t\timuFixedRemoveResponseStarted();
\t\timuFixedWebRequestOn = false;
\t}
}
// default-on (matches upstream); corrected async once storage loads.
imuFixedSetWebRequest(true);
"""
    raw = raw.replace("function imuFixedRemoveResponseStarted() {\n\ttry { chrome.webRequest.onResponseStarted.removeListener(onResponseStarted_listener); } catch (e) {}\n}",
                      "function imuFixedRemoveResponseStarted() {\n\ttry { chrome.webRequest.onResponseStarted.removeListener(onResponseStarted_listener); } catch (e) {}\n}" + toggler, 1)

    # 6) defense-in-depth early returns at top of the two blocking listeners
    raw = raw.replace(
        "var onBeforeSendHeaders_listener = function(details) {\n\tdebug(\"onBeforeSendHeaders\", details);",
        "var onBeforeSendHeaders_listener = function(details) {\n\tif (!imuFixedEnabled) return {};\n\tdebug(\"onBeforeSendHeaders\", details);",
        1,
    )
    raw = raw.replace(
        "var onHeadersReceived = function(details) {\n\tdebug(\"onHeadersReceived\", details);",
        "var onHeadersReceived = function(details) {\n\tif (!imuFixedEnabled) return;\n\tdebug(\"onHeadersReceived\", details);",
        1,
    )

    # 7) wire into existing imu_enabled plumbing (both initial load + live toggle)
    old_init = 'on_ready(function() {\n\tget_option("imu_enabled", update_browseraction_enabled, true);\n});'
    assert old_init in raw, "imu_enabled init hook not found"
    raw = raw.replace(
        old_init,
        'on_ready(function() {\n\tget_option("imu_enabled", function(enabled) {\n\t\timuFixedEnabled = !!enabled;\n\t\timuFixedSetWebRequest(imuFixedEnabled);\n\t\tupdate_browseraction_enabled(enabled);\n\t}, true);\n});',
        1,
    )
    old_change = '\t\tif (key === "imu_enabled") {\n\t\t\tupdate_browseraction_enabled(JSON.parse(changes[key].newValue));\n\t\t}'
    assert old_change in raw, "imu_enabled change hook not found"
    raw = raw.replace(
        old_change,
        '\t\tif (key === "imu_enabled") {\n\t\t\timuFixedEnabled = !!JSON.parse(changes[key].newValue);\n\t\t\timuFixedSetWebRequest(imuFixedEnabled);\n\t\t\tupdate_browseraction_enabled(JSON.parse(changes[key].newValue));\n\t\t}',
        1,
    )

    (OUT / "extension" / "background.js").write_text(raw, encoding="utf-8")
    return orig_len, len(raw)


def patch_background_v2():
    """Second pass on the already-patched background.js (v2 fixes):
      - silent notifications absence (optional permission, not an error)
      - skip unscriptable tabs in settings broadcast + swallow lastError
      - lastError-checked storage writes (quotaExceeded becomes a warn, not red)
    """
    p = OUT / "extension" / "background.js"
    raw = p.read_bytes().decode("utf-8", errors="replace")
    raw = raw.replace("\r", "")

    def rep(old, new, what):
        nonlocal raw
        assert old in raw, f"v2 hook missing: {what}"
        raw = raw.replace(old, new, 1)

    # a) notifications are an *optional* permission; absence is normal, not a warning
    rep('\t\tconsole.warn("Notifications not allowed");',
        '\t\treturn; // IMU-FIXED: notifications is an optional permission; silent when absent',
        "notifications warn")

    # b) popupaction forward: tab may have no content script (excluded YT, chrome://)
    rep(("\t} else if (message.type === \"popupaction\") {\n"
         "\t\tif (message.data.action) {\n"
         "\t\t\tchrome.tabs.query({active: true, currentWindow: true}, function(tabs) {\n"
         "\t\t\t\tvar currentTab = tabs[0];\n"
         "\t\t\t\tchrome.tabs.sendMessage(currentTab.id, message);\n"
         "\t\t\t});\n"
         "\t\t}"),
        ("\t} else if (message.type === \"popupaction\") {\n"
         "\t\tif (message.data.action) {\n"
         "\t\t\tchrome.tabs.query({active: true, currentWindow: true}, function(tabs) {\n"
         "\t\t\t\tvar currentTab = tabs[0];\n"
         "\t\t\t\tif (!currentTab) return;\n"
         "\t\t\t\tif (currentTab.url && imuFixedUnscriptableUrl(currentTab.url)) return;\n"
         "\t\t\t\tchrome.tabs.sendMessage(currentTab.id, message, function() {\n"
         "\t\t\t\t\tif (chrome.runtime.lastError) { debug('popupaction: no receiver in tab', currentTab.id); }\n"
         "\t\t\t\t});\n"
         "\t\t\t});\n"
         "\t\t}"),
        "popupaction forward")

    # c) setvalue writes: surface quota errors as checked warns (incl. contextmenu toggle)
    rep(("\t} else if (message.type === \"setvalue\") {\n"
         "\t\tstorage.set(message.data, function() {\n"
         "\t\t\tif (\"extension_contextmenu\" in message.data) {"),
        ("\t} else if (message.type === \"setvalue\") {\n"
         "\t\tstorage.set(message.data, function() {\n"
         "\t\t\timuFixedNoteWriteError('setvalue');\n"
         "\t\t\tif (\"extension_contextmenu\" in message.data) {"),
        "setvalue write")

    # d) set_option writes: same treatment (kills 'Unchecked runtime.lastError')
    rep(("function set_option(name, value) {\n"
         "\tstorage.set({[name]: JSON.stringify(value)});\n"
         "}"),
        ("function set_option(name, value) {\n"
         "\tstorage.set({[name]: JSON.stringify(value)}, function() {\n"
         "\t\timuFixedNoteWriteError('set_option(' + name + ')');\n"
         "\t});\n"
         "}"),
        "set_option")

    # e) settings broadcast: skip unscriptable tabs, swallow missing-receiver errors.
    #    (YouTube tabs are now excluded from content scripts, so they have no
    #    receiver by design; chrome://, webstore and closed tabs never did.)
    rep(("\tchrome.tabs.query({}, function (tabs) {\n"
         "\t\ttabs.forEach((tab) => {\n"
         "\t\t\ttry {\n"
         "\t\t\t\tdebug(\"Sending storage changes to tab\", tab.id);\n"
         "\n"
         "\t\t\t\tchrome.tabs.sendMessage(tab.id, JSON.parse(JSON.stringify(message)));\n"
         "\t\t\t} catch (e) {\n"
         "\t\t\t\tconsole.error(e);\n"
         "\t\t\t}\n"
         "\t\t});\n"
         "\t});"),
        ("\tchrome.tabs.query({}, function (tabs) {\n"
         "\t\ttabs.forEach((tab) => {\n"
         "\t\t\ttry {\n"
         "\t\t\t\tif (tab.url && imuFixedUnscriptableUrl(tab.url)) return;\n"
         "\t\t\t\tdebug(\"Sending storage changes to tab\", tab.id);\n"
         "\n"
         "\t\t\t\tchrome.tabs.sendMessage(tab.id, JSON.parse(JSON.stringify(message)), function() {\n"
         "\t\t\t\t\tif (chrome.runtime.lastError) { debug('settings_update: no receiver in tab', tab.id); }\n"
         "\t\t\t\t});\n"
         "\t\t\t} catch (e) {\n"
         "\t\t\t\tconsole.error(e);\n"
         "\t\t\t}\n"
         "\t\t});\n"
         "\t});"),
        "settings broadcast")

    p.write_bytes(raw.encode("utf-8"))


def patch_background_v3():
    """Third pass (v3 fixes):
      - download-progress sendMessage: swallow missing-receiver errors
        (source of 'The tab was closed.')
      - all-tabs query fan-out: missing-receiver lastError -> debug(), not
        handle_error() (source of the {"message":...} console triple on
        excluded-YouTube / chrome:// / webstore tabs)
      - contextmenu forward: skip unscriptable tabs, swallow misses
        (right-clicking where no content script runs)
      - broadcast_message: same guarded fan-out
    """
    p = OUT / "extension" / "background.js"
    raw = p.read_bytes().decode("utf-8", errors="replace").replace("\r", "")

    def rep(old, new, what):
        nonlocal raw
        assert old in raw, f"v3 hook missing: {what}"
        raw = raw.replace(old, new, 1)

    rep(("\tif (obj.tabid !== background_userscript_tabid) {\n"
         "\t\tchrome.tabs.sendMessage(obj.tabid, message_data);\n"
         "\t} else {"),
        ("\tif (obj.tabid !== background_userscript_tabid) {\n"
         "\t\tchrome.tabs.sendMessage(obj.tabid, message_data, function() {\n"
         "\t\t\tif (chrome.runtime.lastError) { debug('download progress: no receiver in tab', obj.tabid); }\n"
         "\t\t});\n"
         "\t} else {"),
        "download progress")

    rep(("\t\t\tchrome.tabs.sendMessage(tab.id, JSON.parse(JSON.stringify(message)), {}, (response) => {\n"
         "\t\t\t\thandle_error();\n"),
        ("\t\t\tchrome.tabs.sendMessage(tab.id, JSON.parse(JSON.stringify(message)), {}, (response) => {\n"
         "\t\t\t\tif (chrome.runtime.lastError && /Receiving end|Could not establish|cannot be scripted|tab was closed|message port closed|ExtensionsSettings|extensions gallery/i.test(chrome.runtime.lastError.message || '')) {\n"
         "\t\t\t\t\tdebug('query tabs: no receiver in tab', tab.id);\n"
         "\t\t\t\t} else {\n"
         "\t\t\t\t\thandle_error();\n"
         "\t\t\t\t}\n"),
        "tabs query fan-out")

    rep(("function contextmenu_imu(data, tab) {\n"
         "\tdebug(\"contextMenu\", data);\n"
         "\tchrome.tabs.sendMessage(tab.id, {\n"
         "\t\t\"type\": \"context_imu\"\n"
         "\t});\n"
         "}"),
        ("function contextmenu_imu(data, tab) {\n"
         "\tdebug(\"contextMenu\", data);\n"
         "\tif (tab && tab.url && imuFixedUnscriptableUrl(tab.url)) return;\n"
         "\tchrome.tabs.sendMessage(tab.id, {\n"
         "\t\t\"type\": \"context_imu\"\n"
         "\t}, function() {\n"
         "\t\tif (chrome.runtime.lastError) { debug('context_imu: no receiver in tab', tab && tab.id); }\n"
         "\t});\n"
         "}"),
        "contextmenu forward")

    rep(("var broadcast_message = function(message) {\n"
         "\tchrome.tabs.query({}, function(tabs) {\n"
         "\t\tfor (var i = 0; i < tabs.length; i++) {\n"
         "\t\t\tchrome.tabs.sendMessage(tabs[i].id, message);\n"
         "\t\t}\n"
         "\t});\n"
         "};"),
        ("var broadcast_message = function(message) {\n"
         "\tchrome.tabs.query({}, function(tabs) {\n"
         "\t\tfor (var i = 0; i < tabs.length; i++) {\n"
         "\t\t\t(function(tab) {\n"
         "\t\t\t\tif (tab.url && imuFixedUnscriptableUrl(tab.url)) return;\n"
         "\t\t\t\tchrome.tabs.sendMessage(tab.id, message, function() {\n"
         "\t\t\t\t\tif (chrome.runtime.lastError) { debug('broadcast: no receiver in tab', tab.id); }\n"
         "\t\t\t\t});\n"
         "\t\t\t})(tabs[i]);\n"
         "\t\t}\n"
         "\t});\n"
         "};"),
        "broadcast_message")

    p.write_bytes(raw.encode("utf-8"))


def patch_background_v4():
    """Fourth pass (v4 fixes):
      - hotload(): on install it executeScripts the engine into every open
        http(s) tab; webstore/gallery/policy-blocked/closed tabs fail, and the
        bare handle_error() printed the ExtensionsSettings/gallery/tab-closed
        triple. Skip unscriptable URLs upfront, demote the rest to debug().
    """
    p = OUT / "extension" / "background.js"
    raw = p.read_bytes().decode("utf-8", errors="replace").replace("\r", "")

    def rep(old, new, what):
        nonlocal raw
        assert old in raw, f"v4 hook missing: {what}"
        raw = raw.replace(old, new, 1)

    rep(("\t\t\ttry {\n"
         "\t\t\t\tif (!tab || tab.discarded || !tab.url) continue;\n"
         "\t\t\t\tif (!/^(https?|file):\\/\\//.test(tab.url)) continue;\n"
         "\t\t\t} catch (e) {\n"),
        ("\t\t\ttry {\n"
         "\t\t\t\tif (!tab || tab.discarded || !tab.url) continue;\n"
         "\t\t\t\tif (!/^(https?|file):\\/\\//.test(tab.url)) continue;\n"
         "\t\t\t\tif (imuFixedUnscriptableUrl(tab.url)) continue;\n"
         "\t\t\t} catch (e) {\n"),
        "hotload url filter")

    rep(("\t\t\t\tsetTimeout(function() {\n"
         "\t\t\t\t\tchrome.tabs.executeScript(tab.id, {\n"
         "\t\t\t\t\t\tfile: userscript_file\n"
         "\t\t\t\t\t}, function(){handle_error();});\n"
         "\t\t\t\t}, 1);\n"),
        ("\t\t\t\tsetTimeout(function() {\n"
         "\t\t\t\t\tchrome.tabs.executeScript(tab.id, {\n"
         "\t\t\t\t\t\tfile: userscript_file\n"
         "\t\t\t\t\t}, function() {\n"
         "\t\t\t\t\t\tif (chrome.runtime.lastError && /cannot be scripted|ExtensionsSettings|extensions gallery|tab was closed|Receiving end|Could not establish/i.test(chrome.runtime.lastError.message || '')) {\n"
         "\t\t\t\t\t\t\tdebug('hotload: cannot script tab', tab.id);\n"
         "\t\t\t\t\t\t} else {\n"
         "\t\t\t\t\t\t\thandle_error();\n"
         "\t\t\t\t\t\t}\n"
         "\t\t\t\t\t});\n"
         "\t\t\t\t}, 1);\n"),
        "hotload callback")

    p.write_bytes(raw.encode("utf-8"))


def patch_background_v5():
    """Fifth pass (v5: runtime blocklist enforcement in the background).
      - Cache the blocklist (imuFixedBlockedHosts), refreshed on startup and
        on every imu_fixed_disabled_hosts change (undefined-safe for resets).
      - Both blocking webRequest listeners skip blocklisted request hosts:
        zero header processing there even while globally enabled (live).
      - Harden the imu_enabled onChanged path against storage.clear()
        (newValue undefined after a reset) which previously threw inside
        JSON.parse and killed the whole listener.
    """
    p = OUT / "extension" / "background.js"
    raw = p.read_bytes().decode("utf-8", errors="replace").replace("\r", "")

    def rep(old, new, what):
        nonlocal raw
        assert old in raw, f"v5 hook missing: {what}"
        raw = raw.replace(old, new, 1)

    rep("function imuFixedSetWebRequest(on) {",
        ("var imuFixedBlockedHosts = [];\n"
         "function imuFixedParseHostsBg(text) {\n"
         "\tvar out = [];\n"
         "\ttry {\n"
         "\t\tString(text || \"\").split(/[\\n,;]+/).forEach(function(line) {\n"
         "\t\t\tvar h = String(line || \"\").trim().toLowerCase();\n"
         "\t\t\th = h.replace(/^\\*\\./, \"\").replace(/^https?:\\/\\//, \"\").split(/[\\/\\s]/)[0];\n"
         "\t\t\tif (h) out.push(h);\n"
         "\t\t});\n"
         "\t} catch (e) {}\n"
         "\treturn out;\n"
         "}\n"
         "function imuFixedGetHost(url) {\n"
         "\ttry {\n"
         "\t\tvar m = String(url || \"\").match(/^[a-z]+:\\/\\/([^\\/:?#]+)/i);\n"
         "\t\treturn m ? m[1].toLowerCase() : \"\";\n"
         "\t} catch (e2) { return \"\"; }\n"
         "}\n"
         "function imuFixedHostBlockedBg(host) {\n"
         "\ttry {\n"
         "\t\thost = String(host || \"\").toLowerCase();\n"
         "\t\tif (!host || !imuFixedBlockedHosts.length) return false;\n"
         "\t\tfor (var i = 0; i < imuFixedBlockedHosts.length; i++) {\n"
         "\t\t\tvar e = imuFixedBlockedHosts[i];\n"
         "\t\t\tif (host === e || host.slice(-e.length - 1) === \".\" + e) return true;\n"
         "\t\t}\n"
         "\t} catch (e3) {}\n"
         "\treturn false;\n"
         "}\n"
         "function imuFixedRefreshBlockedHosts() {\n"
         "\ttry {\n"
         "\t\tget_option(\"imu_fixed_disabled_hosts\", function(v) {\n"
         "\t\t\ttry { imuFixedBlockedHosts = imuFixedParseHostsBg(typeof v === \"string\" ? v : \"\"); } catch (e4) {}\n"
         "\t\t}, \"\");\n"
         "\t} catch (e5) {}\n"
         "}\n"
         "function imuFixedSetWebRequest(on) {"),
        "blocked-hosts helpers")

    rep("\tif (!imuFixedEnabled) return {};",
        ("\tif (!imuFixedEnabled) return {};\n"
         "\tif (imuFixedHostBlockedBg(imuFixedGetHost(details.url))) return {};"),
        "request-headers host skip")

    rep("\tif (!imuFixedEnabled) return;",
        ("\tif (!imuFixedEnabled) return;\n"
         "\tif (imuFixedHostBlockedBg(imuFixedGetHost(details.url))) return;"),
        "headers-received host skip")

    rep(("on_ready(function() {\n"
         "\tget_option(\"imu_enabled\", function(enabled) {\n"
         "\t\timuFixedEnabled = !!enabled;\n"
         "\t\timuFixedSetWebRequest(imuFixedEnabled);\n"
         "\t\tupdate_browseraction_enabled(enabled);\n"
         "\t}, true);\n"
         "});"),
        ("on_ready(function() {\n"
         "\tget_option(\"imu_enabled\", function(enabled) {\n"
         "\t\timuFixedEnabled = !!enabled;\n"
         "\t\timuFixedSetWebRequest(imuFixedEnabled);\n"
         "\t\tupdate_browseraction_enabled(enabled);\n"
         "\t\timuFixedRefreshBlockedHosts();\n"
         "\t}, true);\n"
         "});"),
        "init refresh")

    rep(("\t\tif (key === \"imu_enabled\") {\n"
         "\t\t\timuFixedEnabled = !!JSON.parse(changes[key].newValue);\n"
         "\t\t\timuFixedSetWebRequest(imuFixedEnabled);\n"
         "\t\t\tupdate_browseraction_enabled(JSON.parse(changes[key].newValue));\n"
         "\t\t}"),
        ("\t\tif (key === \"imu_enabled\") {\n"
         "\t\t\tvar imuFixedEnabledVal = true;\n"
         "\t\t\ttry { if (changes[key].newValue !== undefined) imuFixedEnabledVal = JSON.parse(changes[key].newValue); } catch (e6) { imuFixedEnabledVal = true; }\n"
         "\t\t\timuFixedEnabled = !!imuFixedEnabledVal;\n"
         "\t\t\timuFixedSetWebRequest(imuFixedEnabled);\n"
         "\t\t\tupdate_browseraction_enabled(imuFixedEnabledVal);\n"
         "\t\t}\n"
         "\t\tif (key === \"imu_fixed_disabled_hosts\") {\n"
         "\t\t\timuFixedRefreshBlockedHosts();\n"
         "\t\t}"),
        "onChanged hardening")

    p.write_bytes(raw.encode("utf-8"))


def patch_content_native(text):
    """Register imu_fixed_disabled_hosts as a first-class engine setting
    (Rules tab, textarea) and stop follow-system dark mode looking modified.
      a) defaults entry (default ""), next to mouseover_position.
      b) settings_meta entry with category "rules", type "textarea".
      c) update_dark_mode mutates the live default to true on dark systems;
         mirror that into orig_settings so the row isn't flagged modified
         with a revert button that would cement light mode.
    """
    m = re.findall(r'\n([ \t]*)mouseover_position: "center",', text)
    assert len(m) == 1, f"position default anchor: {len(m)}"
    ind = m[0]
    text = text.replace(f'\n{ind}mouseover_position: "center",',
                        f'\n{ind}mouseover_position: "center",\n{ind}imu_fixed_disabled_hosts: "",', 1)

    m2 = re.findall(r'\n([ \t]*)mouseover_position: \{\n', text)
    assert len(m2) == 1, f"position meta anchor: {len(m2)}"
    ind2 = m2[0]
    meta = (f'\n{ind2}imu_fixed_disabled_hosts: {{\n'
            f'{ind2}\tname: "Disabled websites",\n'
            f'{ind2}\tdescription: "Websites where the extension never loads its engine (one host per line, subdomains match automatically, empty runs everywhere). Request handling stops immediately; full effect after reload.",\n'
            f'{ind2}\ttype: "textarea",\n'
            f'{ind2}\tcategory: "rules"\n'
            f'{ind2}}},')
    text = text.replace(f'\n{ind2}mouseover_position: {{\n', meta + f'\n{ind2}mouseover_position: {{\n', 1)

    m3 = re.findall(r'^([ \t]*)set_default_value\("dark_mode", true\);', text, re.M)
    assert len(m3) == 1, f"dark hook: {len(m3)}"
    ind3 = m3[0]
    text = text.replace(f'{ind3}set_default_value("dark_mode", true);',
                        f'{ind3}set_default_value("dark_mode", true);\n{ind3}try {{ orig_settings["dark_mode"] = true; }} catch (e) {{}}', 1)

    # d) rule-family toggles (allow_bruteforce, allow_possibly_upscaled, ...):
    #    baked literal says false, but the option_to_problems loop below flips
    #    them to true at load (unless excluded via default_options) AFTER the
    #    orig_settings snapshot. Every fresh/reset profile therefore showed
    #    them ON + flagged modified, and reset could never turn them "off"
    #    because the loop re-enables them on every load by design. Mirror the
    #    effective values into orig so fresh == unflagged and revert means
    #    "back to the true default (on)". Stored user values still win (they
    #    load later via update_setting_from_host).
    m4 = re.findall(r'^([ \t]*)(settings\[option\] = array_indexof\(default_options\.exclude_problems, problem\) < 0;)',
                    text, re.M)
    assert len(m4) == 1, f"problems loop hook: {len(m4)}"
    ind4, stmt4 = m4[0]
    text = text.replace(f'{ind4}{stmt4}',
                        f'{ind4}{stmt4}\n'
                        f'{ind4}try {{ if (option === "allow_bruteforce") {{ settings[option] = false; }} }} catch (e10) {{}}\n'
                        f'{ind4}try {{ orig_settings[option] = settings[option]; }} catch (e) {{}}', 1)
    return text


def patch_content_fastbail(text):
    """Insert the runtime host-blocklist fast-path in front of do_config().

    do_config() normally fires hundreds of per-setting getvalue IPCs and then
    start() attaches observers/listeners. The wrapper first fetches only TWO
    keys (imu_enabled, imu_fixed_disabled_hosts); on blocklisted hosts (or a
    global off) it flips settings.imu_enabled=false and returns WITHOUT the
    storm, the observers, or any listeners. Residual cost on excluded hosts:
    one V8 parse + one IPC. Extension/options pages (hostname "") never match.
    """
    assert text.count("\n\tfunction do_config() {") == 1, "do_config decl not unique"
    assert "imuFixedHostBlocked" not in text, "fast-bail already applied"

    helpers = (
        "\n\t/* ==== IMU-FIXED: runtime host blocklist fast-path (single IPC) ==== */\n"
        "\tfunction imuFixedParseHosts(text) {\n"
        "\t\tvar out = [];\n"
        "\t\ttry {\n"
        "\t\t\tString(text || \"\").split(/[\\n,;]+/).forEach(function(line) {\n"
        "\t\t\t\tvar h = String(line || \"\").trim().toLowerCase();\n"
        "\t\t\t\th = h.replace(/^\\*\\./, \"\").replace(/^https?:\\/\\//, \"\").split(/[\\/\\s]/)[0];\n"
        "\t\t\t\tif (h) out.push(h);\n"
        "\t\t\t});\n"
        "\t\t} catch (e) {}\n"
        "\t\treturn out;\n"
        "\t}\n"
        "\tfunction imuFixedHostBlocked(host, listText) {\n"
        "\t\ttry {\n"
        "\t\t\thost = String(host || \"\").toLowerCase();\n"
        "\t\t\tif (!host) return false;\n"
        "\t\t\tvar list = imuFixedParseHosts(listText);\n"
        "\t\t\tfor (var i = 0; i < list.length; i++) {\n"
        "\t\t\t\tvar e = list[i];\n"
        "\t\t\t\tif (host === e || host.slice(-e.length - 1) === \".\" + e) return true;\n"
        "\t\t\t}\n"
        "\t\t} catch (e2) {}\n"
        "\t\treturn false;\n"
        "\t}\n"
        "\tfunction do_config() {\n"
        "\t\ttry {\n"
        "\t\t\tget_values([\"imu_enabled\", \"imu_fixed_disabled_hosts\"], function(fast) {\n"
        "\t\t\t\ttry {\n"
        "\t\t\t\t\tvar imuFixedOff = false;\n"
        "\t\t\t\t\ttry { imuFixedOff = !fast || fast.imu_enabled === false || fast.imu_enabled === \"false\"; } catch (e3) {}\n"
        "\t\t\t\t\tvar imuFixedBlocked = false;\n"
        "\t\t\t\t\ttry {\n"
        "\t\t\t\t\t\tvar imuFixedHn = \"\";\n"
        "\t\t\t\t\t\ttry { imuFixedHn = (window.location && window.location.hostname) || \"\"; } catch (e4) {}\n"
        "\t\t\t\t\t\timuFixedBlocked = imuFixedHostBlocked(imuFixedHn, (fast && fast.imu_fixed_disabled_hosts) || \"\");\n"
        "\t\t\t\t\t} catch (e5) {}\n"
        "\t\t\t\t\tif (imuFixedBlocked || imuFixedOff) {\n"
        "\t\t\t\t\t\ttry { settings.imu_enabled = false; } catch (e6) {}\n"
        "\t\t\t\t\t\ttry { console.log(\"[IMU Fixed] host-disabled/off, skipping heavy init\"); } catch (e7) {}\n"
        "\t\t\t\t\t\treturn;\n"
        "\t\t\t\t\t}\n"
        "\t\t\t\t} catch (e8) {}\n"
        "\t\t\t\timuFixedDoConfigOrig();\n"
        "\t\t\t});\n"
        "\t\t} catch (e9) { imuFixedDoConfigOrig(); }\n"
        "\t}\n"
        "\tfunction imuFixedDoConfigOrig() {"
    )
    return text.replace("\n\tfunction do_config() {", helpers, 1)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "extension").mkdir(parents=True)
    (OUT / "resources").mkdir(parents=True)

    old_ver, new_ver = patch_manifest()

    # content scripts: pristine full rules, renamed to .js (Chrome mime check).
    # background page: same file under a second .js name (background pages also
    # reject the .user.js extension).
    # One behavioral default change (both copies, keeps them identical):
    #   mouseover_position "cursor" -> "center" (Popup position: Page middle),
    # so the enlarged popup spawns centered instead of at the cursor.
    # The bg copy never renders popups (is_extension_bg), so this is a no-op there.
    _full = (SRC / "userscript.user.js").read_bytes().decode("utf-8", errors="replace")
    _full = _full.replace("\r", "")
    assert _full.count('mouseover_position: "cursor"') >= 1, "position default not found"
    _full = _full.replace('mouseover_position: "cursor"', 'mouseover_position: "center"', 1)
    _full = patch_content_native(_full)
    _full = patch_content_fastbail(_full)
    (OUT / "userscript-content.js").write_text(_full, encoding="utf-8")
    (OUT / "userscript-bg.js").write_text(_full, encoding="utf-8")
    for f in (SRC / "extension").glob("*"):
        if f.name == "background.js":
            continue
        shutil.copy2(f, OUT / "extension" / f.name)
    # options.html pulls the whole engine via <script>; point it at the
    # renamed copy (missing file = infinite "loading"). Companion options
    # script (blocklist UI, position shortcut, reset) loads right after.
    shutil.copy2(ROOT / "imu-fixed" / "imu-fixed-options.js",
                 OUT / "extension" / "imu-fixed-options.js")
    _opt = OUT / "extension" / "options.html"
    _opt_text = _opt.read_text(encoding="utf-8")
    assert "../userscript.user.js" in _opt_text, "options.html script ref not found"
    _opt_text = _opt_text.replace("../userscript.user.js", "../userscript-content.js")
    assert "imu-fixed-options.js" not in _opt_text, "options companion already injected"
    _opt_text = _opt_text.replace('<script src="../userscript-content.js"></script>',
                                  '<script src="../userscript-content.js"></script>\n    <script src="imu-fixed-options.js"></script>',
                                  1)
    _opt.write_text(_opt_text, encoding="utf-8")
    for f in (SRC / "resources").glob("*"):
        if f.is_file():
            shutil.copy2(f, OUT / "resources" / f.name)

    o_len, n_len = patch_background()
    patch_background_v2()
    patch_background_v3()
    patch_background_v4()
    patch_background_v5()
    # README source of truth lives outside OUT (main() wipes OUT on rebuild)
    _readme_src = ROOT / "imu-fixed" / "extension-README.md"
    if _readme_src.exists():
        shutil.copy2(_readme_src, OUT / "README.md")
    print(f"manifest {old_ver} -> {new_ver}")
    print(f"background {o_len} -> {n_len} chars")
    print("copied:", sorted(p.name for p in OUT.rglob("*") if p.is_file()))

if __name__ == "__main__":
    main()
