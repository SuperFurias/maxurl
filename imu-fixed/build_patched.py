#!/usr/bin/env python3
"""Build imu-fixed.user.js from maxurl/userscript_smaller.user.js.
Applies:
 1. Header: rename, @run-at document-idle, @exclude youtube domains.
 2. One-line fix: enable extension_contextmenu path for userscripts too.
 3. Append IMU-FIXED shim (early-skip + custom right-click menu) before final do_config().
"""
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent  # fork root
SRC = ROOT / "userscript_smaller.user.js"
OUT = ROOT / "imu-fixed" / "imu-fixed.user.js"

SHIM = r"""
/* =====================================================================
 * IMU-FIXED PATCH (v1)
 * - Early-skip on YouTube + when imu_enabled==false (sync GM_getValue fast-path).
 *   Manager-level @exclude already prevents injection on YouTube; this guard
 *   additionally covers YouTube SPA navigations (Shorts) and disabled state,
 *   so we skip do_config()'s hundreds of async getvalue round-trips,
 *   MutationObserver setup, and popup machinery.
 * - Custom right-click helper for userscripts (native contextMenus API is
 *   extension-only). We show a small floating panel next to the cursor;
 *   we deliberately do NOT preventDefault() so the native menu still works.
 * ===================================================================== */
var imuFixedSkipReason = null;
function imuFixedShouldSkip() {
    try {
        var href = "";
        try { href = (window && window.location && window.location.href) || ""; } catch (e) {}
        if (/^https?:\/\/([^\/]*\.)?(youtube\.com|youtu\.be|youtube-nocookie\.com)(\/|$)/i.test(href)) {
            imuFixedSkipReason = "youtube-excluded";
            return true;
        }
    } catch (e) {}
    try {
        if (typeof GM_getValue !== "undefined") {
            try {
                var v = GM_getValue("imu_enabled", undefined);
                // NB: some managers return a Promise for GM.getValue only; sync GM_getValue returns real value.
                if (v === false || v === "false") { imuFixedSkipReason = "imu-disabled"; return true; }
            } catch (e) {}
        }
    } catch (e) {}
    return false;
}

var imuFixedCtxState = { url: null, x: 0, y: 0, el: null };
var imuFixedMenuEl = null;

function imuFixedGenericLarger(url) {
    try {
        if (!url || typeof url !== "string") return url;
        if (/^(data|blob):/i.test(url)) return url;
        var u = url;
        // YouTube thumbnails: hqdefault/mqdefault/sddefault -> maxresdefault, default -> hqdefault
        try {
            if (/i\.ytimg\.com\/vi\//i.test(u)) {
                if (/\/sddefault\.jpg/i.test(u)) return u.replace(/\/sddefault\.jpg/i, "/maxresdefault.jpg");
                if (/\/mqdefault\.jpg/i.test(u)) return u.replace(/\/mqdefault\.jpg/i, "/maxresdefault.jpg");
                if (/\/hqdefault\.jpg/i.test(u)) return u.replace(/\/hqdefault\.jpg/i, "/maxresdefault.jpg");
                if (/\/default\.jpg/i.test(u)) return u.replace(/\/default\.jpg/i, "/hqdefault.jpg");
            }
        } catch (e) {}
        // yt3 avatars: =s88-c-k etc -> =s1024 (google profile image sizing)
        try {
            if (/yt3\.ggpht\.com/i.test(u) || /ggpht\.com/i.test(u)) {
                var m = u.match(/^(.*?)=s\d+(-c.*)?$/);
                if (m) return m[1] + "=s1024" + (m[2] || "");
            }
        } catch (e) {}
        // Strip common thumbnail size suffixes before extension: -200x200, _300x300, -small, _thumb, etc.
        try {
            u = u.replace(/(-\d+x\d+)(\.(?:jpe?g|png|gif|webp|avif|bmp)(?:[?#]|$))/i, "$2");
            u = u.replace(/(_\d+x\d+)(\.(?:jpe?g|png|gif|webp|avif|bmp)(?:[?#]|$))/i, "$2");
        } catch (e) {}
        // Query-param sizes: ?w=200&h=200&s=... -> drop w/h/s when safe (keep other params)
        try {
            var qpos = u.indexOf("?");
            if (qpos > 0) {
                var base = u.substring(0, qpos);
                var qs = u.substring(qpos + 1);
                var hash = "";
                var hpos = qs.indexOf("#");
                if (hpos >= 0) { hash = qs.substring(hpos); qs = qs.substring(0, hpos); }
                var parts = qs.split("&");
                var kept = [];
                for (var i = 0; i < parts.length; i++) {
                    var kv = parts[i].split("=");
                    var k = (kv[0] || "").toLowerCase();
                    if (k === "w" || k === "h" || k === "width" || k === "height" || k === "s" || k === "size" || k === "thumb" || k === "thumbnail") {
                        continue;
                    }
                    kept.push(parts[i]);
                }
                if (kept.length !== parts.length) {
                    u = base + (kept.length ? ("?" + kept.join("&")) : "") + hash;
                }
            }
        } catch (e) {}
        return u;
    } catch (e) { return url; }
}

function imuFixedGetTargetUrl(target) {
    try {
        if (!target || !target.ownerDocument) return null;
        var el = target;
        // If right-click landed on a child (e.g. overlay), walk up to nearest media/link.
        var depth = 0;
        while (el && depth < 6) {
            try {
                var tag = (el.tagName || "").toUpperCase();
                if (tag === "IMG") {
                    return el.currentSrc || el.src || null;
                }
                if (tag === "VIDEO") {
                    if (el.currentSrc) return el.currentSrc;
                    if (el.src) return el.src;
                    if (el.poster) return el.poster;
                    var srcEl = el.querySelector ? el.querySelector("source[src]") : null;
                    if (srcEl && srcEl.src) return srcEl.src;
                    return null;
                }
                if (tag === "SOURCE" && el.src) return el.src;
                if (tag === "A" && el.href) {
                    // Prefer enclosed image if the link wraps one.
                    var img = el.querySelector ? el.querySelector("img") : null;
                    if (img && (img.currentSrc || img.src)) return img.currentSrc || img.src;
                    return el.href;
                }
            } catch (e) {}
            el = el.parentElement;
            depth++;
        }
    } catch (e) {}
    return null;
}

function imuFixedEnsureMenu() {
    try {
        if (imuFixedMenuEl && imuFixedMenuEl.isConnected) return imuFixedMenuEl;
        var d = document.createElement("div");
        d.setAttribute("data-imu-fixed", "ctx");
        d.style.cssText = "all:initial;position:fixed;z-index:2147483647;font-family:system-ui,sans-serif;font-size:13px;color:#111;background:#fff;border:1px solid #888;border-radius:8px;box-shadow:0 4px 18px rgba(0,0,0,.35);padding:6px;display:none;max-width:280px;";
        var title = document.createElement("div");
        title.textContent = "IMU Fixed";
        title.style.cssText = "all:initial;display:block;font-family:system-ui,sans-serif;font-size:11px;font-weight:700;color:#555;padding:2px 8px 4px;";
        d.appendChild(title);
        var mkbtn = function(label, cb) {
            var b = document.createElement("button");
            b.textContent = label;
            b.style.cssText = "all:initial;display:block;width:100%;text-align:left;font-family:system-ui,sans-serif;font-size:13px;color:#111;background:#fff;border:0;border-radius:6px;padding:7px 10px;cursor:pointer;";
            b.onmouseenter = function() { b.style.background = "#eee"; };
            b.onmouseleave = function() { b.style.background = "#fff"; };
            b.onclick = function(ev) { try { ev.stopPropagation(); } catch (e) {} imuFixedHideMenu(); try { cb(); } catch (e) {} };
            d.appendChild(b);
            return b;
        };
        mkbtn("Open larger image (IMU Fixed)", function() { imuFixedOpenLarger(false); });
        mkbtn("Open larger in background tab", function() { imuFixedOpenLarger(true); });
        mkbtn("Copy image URL", function() {
            try {
                var u = imuFixedCtxState.url;
                if (!u) return;
                if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(u); }
                else { var ta = document.createElement("textarea"); ta.value = u; document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); } catch (e) {} ta.remove(); }
            } catch (e) {}
        });
        document.documentElement.appendChild(d);
        imuFixedMenuEl = d;
        var hide = function() { imuFixedHideMenu(); };
        document.addEventListener("scroll", hide, true);
        document.addEventListener("mousedown", function(e) { try { if (imuFixedMenuEl && !imuFixedMenuEl.contains(e.target)) imuFixedHideMenu(); } catch (err) {} }, true);
        document.addEventListener("keydown", function(e) { try { if (e.key === "Escape") imuFixedHideMenu(); } catch (err) {} }, true);
        return d;
    } catch (e) { return null; }
}

function imuFixedHideMenu() {
    try { if (imuFixedMenuEl) imuFixedMenuEl.style.display = "none"; } catch (e) {}
}

function imuFixedShowMenu(x, y) {
    try {
        var m = imuFixedEnsureMenu();
        if (!m) return;
        m.style.display = "block";
        var w = 280, h = 140;
        try { w = m.offsetWidth || 280; h = m.offsetHeight || 140; } catch (e) {}
        var nx = Math.min(x, (window.innerWidth || 1000) - w - 8);
        var ny = Math.min(y, (window.innerHeight || 800) - h - 8);
        if (nx < 8) nx = 8;
        if (ny < 8) ny = 8;
        m.style.left = nx + "px";
        m.style.top = ny + "px";
        // Auto-hide after 6s so it never lingers over Shorts UI.
        try { setTimeout(imuFixedHideMenu, 6000); } catch (e) {}
    } catch (e) {}
}

function imuFixedDoRequestShim(opts) {
    // Bridges IMU's do_request() expectation (GM_xmlhttpRequest-like) to whatever GM API exists.
    try {
        var fn = null;
        try { if (typeof GM_xmlhttpRequest !== "undefined") fn = GM_xmlhttpRequest; } catch (e) {}
        try { if (!fn && typeof GM !== "undefined" && GM.xmlHttpRequest) fn = function(o) { return GM.xmlHttpRequest(o); }; } catch (e) {}
        if (!fn) return null;
        return fn({
            url: opts.url,
            method: opts.method || "GET",
            data: opts.data || "",
            headers: opts.headers || {},
            responseType: "text",
            onload: function(resp) {
                try {
                    opts.onload({
                        finalUrl: resp.finalUrl || opts.url,
                        readyState: 4,
                        responseText: resp.responseText || "",
                        status: resp.status || 0
                    });
                } catch (e) {}
            },
            onerror: function() { try { opts.onload({ finalUrl: opts.url, readyState: 4, responseText: "", status: 0 }); } catch (e) {} }
        });
    } catch (e) { return null; }
}

function imuFixedOpenLarger(background) {
    var url = imuFixedCtxState.url;
    if (!url) return;
    var done = false;
    var openUrl = function(u) {
        if (done) return;
        done = true;
        try {
            if (!u) u = url;
            // Prefer GM_openInTab (keeps userscript referer handling), fall back to window.open.
            if (!background) {
                try { if (typeof GM_openInTab !== "undefined") { GM_openInTab(u, false); return; } } catch (e) {}
                try { if (typeof GM !== "undefined" && GM.openInTab) { GM.openInTab(u, false); return; } } catch (e) {}
                window.open(u, "_blank");
            } else {
                try { if (typeof GM_openInTab !== "undefined") { GM_openInTab(u, true); return; } } catch (e) {}
                try { if (typeof GM !== "undefined" && GM.openInTab) { GM.openInTab(u, true); return; } } catch (e) {}
                window.open(u, "_blank");
            }
        } catch (e) {
            try { window.open(url, "_blank"); } catch (err) {}
        }
    };
    // 1) Try full IMU engine if it finished loading (works for 10k+ sites).
    try {
        var exp = null;
        try { exp = (typeof $$IMU_EXPORT$$ !== "undefined") ? $$IMU_EXPORT$$ : null; } catch (e) {}
        if (exp && !imuFixedShouldSkip()) {
            var timedOut = false;
            var timer = null;
            try { timer = setTimeout(function() { timedOut = true; openUrl(imuFixedGenericLarger(url)); }, 8000); } catch (e) {}
            try {
                exp(url, {
                    fill_object: true,
                    iterations: 8,
                    use_cache: true,
                    urlcache_time: 3600,
                    exclude_videos: false,
                    include_pastobjs: true,
                    force_page: false,
                    allow_thirdparty: false,
                    do_request: function(o) { imuFixedDoRequestShim(o); },
                    cb: function(result) {
                        try { if (timer) clearTimeout(timer); } catch (e) {}
                        if (timedOut) return;
                        try {
                            if (result && result.length && result[0] && result[0].url && result[0].url !== url) {
                                openUrl(result[0].url);
                            } else {
                                openUrl(imuFixedGenericLarger(url));
                            }
                        } catch (e) { openUrl(imuFixedGenericLarger(url)); }
                    }
                });
                return; // async path will open
            } catch (e) {
                try { if (timer) clearTimeout(timer); } catch (err) {}
            }
        }
    } catch (e) {}
    // 2) Instant generic fallback (no network, covers YT thumbs/avatars + common -200x200 patterns).
    openUrl(imuFixedGenericLarger(url));
}

try {
    (function imuFixedInitContextMenu() {
        if (typeof document === "undefined" || !document.addEventListener) return;
        // Never interfere with YouTube: native menu only, zero IMU UI.
        document.addEventListener("contextmenu", function(e) {
            try {
                var href = "";
                try { href = (window && window.location && window.location.href) || ""; } catch (err) {}
                if (/^https?:\/\/([^\/]*\.)?(youtube\.com|youtu\.be|youtube-nocookie\.com)(\/|$)/i.test(href)) return;
                var u = imuFixedGetTargetUrl(e.target);
                if (!u) return;
                imuFixedCtxState.url = u;
                imuFixedCtxState.x = e.clientX;
                imuFixedCtxState.y = e.clientY;
                imuFixedCtxState.el = e.target;
                imuFixedShowMenu(e.clientX, e.clientY);
            } catch (err) {}
        }, true);
    })();
} catch (e) {}

try {
    if (typeof GM_registerMenuCommand !== "undefined") {
        try { GM_registerMenuCommand("IMU Fixed: open larger from last right-click", function() { imuFixedOpenLarger(false); }); } catch (e) {}
    }
} catch (e) {}
/* ==== END IMU-FIXED PATCH ==== */
"""

def main():
    if not SRC.exists():
        print(f"missing src {SRC}", file=sys.stderr)
        sys.exit(1)
    raw = SRC.read_bytes().decode("utf-8", errors="replace")
    orig_len = len(raw)

    # --- 1) header patches ---
    # rename (first @name line only)
    raw, n_name = re.subn(r"// @name\s+Image Max URL", "// @name              IMU Fixed - Image Max URL (no-slowdown + context menu)", raw, count=1)
    # run-at -> document-idle (fixes document-start main-thread block on every page)
    raw, n_run = re.subn(r"// @run-at\s+document-start", "// @run-at            document-idle", raw, count=1)
    # insert @exclude lines after @match line (manager-level: zero parse cost on YouTube)
    def _add_excludes(m):
        return (m.group(0)
                + "\n// @exclude           *://*.youtube.com/*"
                + "\n// @exclude           *://*.youtu.be/*"
                + "\n// @exclude           *://*.youtube-nocookie.com/*"
                + "\n// @exclude           *://*.ytimg.com/*")
    raw, n_match = re.subn(r"// @match\s+\*://\*/\*", _add_excludes, raw, count=1)

    # --- 2) one-line userscript contextmenu enabler ---
    # original (TS): if (is_extension && settings.extension_contextmenu && event.type === "mousedown")
    # built JS keeps same shape; allow userscript too.
    raw2, n_ctx = re.subn(
        r"if\s*\(\s*is_extension\s*&&\s*settings\.extension_contextmenu",
        "if ((is_extension || is_userscript) && settings.extension_contextmenu",
        raw,
    )

    # --- 3) guarded do_config + shim (replace LAST do_config(); call) ---
    idx = raw2.rfind("do_config();")
    if idx < 0:
        print("FATAL: do_config(); not found", file=sys.stderr)
        sys.exit(1)
    guarded = (
        SHIM
        + "\ntry {\n"
        + "    if (!imuFixedShouldSkip()) {\n"
        + "        do_config();\n"
        + "    } else {\n"
        + '        try { console.log("[IMU Fixed] skipped heavy init (" + imuFixedSkipReason + ")"); } catch (e) {}\n'
        + "        try { $$IMU_EXPORT$$ = function(u, o) { if (o && typeof o.cb === 'function') { try { o.cb(null); } catch (e) {} } return u; }; } catch (e) {}\n"
        + "    }\n"
        + "} catch (e) { try { do_config(); } catch (err) {} }\n"
    )
    raw3 = raw2[:idx] + guarded + raw2[idx + len("do_config();"):]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(raw3.encode("utf-8"))
    print(f"src_bytes={SRC.stat().st_size} out_bytes={OUT.stat().st_size} name={n_name} run={n_run} match={n_match} ctx_fix={n_ctx}")

if __name__ == "__main__":
    main()
