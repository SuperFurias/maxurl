// ==UserScript==
// @name              IMU Fixed Lite - Right-click larger image (no slowdown)
// @namespace         imu-fixed
// @version           1.0.0
// @description       Lightweight right-click helper: open larger/original image without the 7MB IMU parse cost. No MutationObserver, no webRequest, runs at document-idle. Companion to imu-fixed.user.js.
// @match             *://*/*
// @grant             GM_openInTab
// @grant             GM.registerMenuCommand
// @grant             GM_setClipboard
// @grant             GM.setClipboard
// @run-at            document-idle
// @license           Apache-2.0
// ==/UserScript==
(function () {
    'use strict';
    var ENABLED_KEY = 'imu_fixed_lite_enabled';
    var enabled = true;
    try {
        if (typeof GM_getValue !== 'undefined') {
            var v = GM_getValue(ENABLED_KEY, undefined);
            if (v === false || v === 'false') enabled = false;
        }
    } catch (e) {}
    try {
        if (typeof GM_registerMenuCommand !== 'undefined') {
            GM_registerMenuCommand('IMU Lite: toggle on/off', function () {
                enabled = !enabled;
                try {
                    if (typeof GM_setValue !== 'undefined') GM_setValue(ENABLED_KEY, enabled);
                } catch (e) {}
                try { alert('IMU Lite ' + (enabled ? 'enabled' : 'disabled')); } catch (e) {}
            });
        }
    } catch (e) {}

    function genericLarger(url) {
        try {
            if (!url || typeof url !== 'string') return url;
            if (/^(data|blob):/i.test(url)) return url;
            var u = url;
            try {
                if (/i\.ytimg\.com\/vi\//i.test(u)) {
                    if (/\/sddefault\.jpg/i.test(u)) return u.replace(/\/sddefault\.jpg/i, '/maxresdefault.jpg');
                    if (/\/mqdefault\.jpg/i.test(u)) return u.replace(/\/mqdefault\.jpg/i, '/maxresdefault.jpg');
                    if (/\/hqdefault\.jpg/i.test(u)) return u.replace(/\/hqdefault\.jpg/i, '/maxresdefault.jpg');
                    if (/\/default\.jpg/i.test(u)) return u.replace(/\/default\.jpg/i, '/hqdefault.jpg');
                }
            } catch (e) {}
            try {
                if (/yt3\.ggpht\.com/i.test(u) || /ggpht\.com/i.test(u)) {
                    var m = u.match(/^(.*?)=s\d+(-c.*)?$/);
                    if (m) return m[1] + '=s1024' + (m[2] || '');
                }
            } catch (e) {}
            try {
                u = u.replace(/(-\d+x\d+)(\.(?:jpe?g|png|gif|webp|avif|bmp)(?:[?#]|$))/i, '$2');
                u = u.replace(/(_\d+x\d+)(\.(?:jpe?g|png|gif|webp|avif|bmp)(?:[?#]|$))/i, '$2');
            } catch (e) {}
            try {
                var qpos = u.indexOf('?');
                if (qpos > 0) {
                    var base = u.substring(0, qpos);
                    var qs = u.substring(qpos + 1);
                    var hash = '';
                    var hpos = qs.indexOf('#');
                    if (hpos >= 0) { hash = qs.substring(hpos); qs = qs.substring(0, hpos); }
                    var parts = qs.split('&');
                    var kept = [];
                    for (var i = 0; i < parts.length; i++) {
                        var k = ((parts[i].split('=')[0]) || '').toLowerCase();
                        if (k === 'w' || k === 'h' || k === 'width' || k === 'height' || k === 's' || k === 'size' || k === 'thumb' || k === 'thumbnail') continue;
                        kept.push(parts[i]);
                    }
                    if (kept.length !== parts.length) u = base + (kept.length ? ('?' + kept.join('&')) : '') + hash;
                }
            } catch (e) {}
            return u;
        } catch (e) { return url; }
    }

    function targetUrl(t) {
        try {
            var el = t, depth = 0;
            while (el && depth < 6) {
                var tag = (el.tagName || '').toUpperCase();
                if (tag === 'IMG') return el.currentSrc || el.src || null;
                if (tag === 'VIDEO') {
                    if (el.currentSrc) return el.currentSrc;
                    if (el.src) return el.src;
                    if (el.poster) return el.poster;
                    var s = el.querySelector ? el.querySelector('source[src]') : null;
                    if (s && s.src) return s.src;
                    return null;
                }
                if (tag === 'SOURCE' && el.src) return el.src;
                if (tag === 'A' && el.href) {
                    var img = el.querySelector ? el.querySelector('img') : null;
                    if (img && (img.currentSrc || img.src)) return img.currentSrc || img.src;
                    return el.href;
                }
                el = el.parentElement; depth++;
            }
        } catch (e) {}
        return null;
    }

    var state = { url: null };
    var menu = null;
    function ensureMenu() {
        if (menu && menu.isConnected) return menu;
        var d = document.createElement('div');
        d.style.cssText = 'all:initial;position:fixed;z-index:2147483647;font-family:system-ui,sans-serif;font-size:13px;color:#111;background:#fff;border:1px solid #888;border-radius:8px;box-shadow:0 4px 18px rgba(0,0,0,.35);padding:6px;display:none;max-width:280px;';
        var mk = function (label, cb) {
            var b = document.createElement('button');
            b.textContent = label;
            b.style.cssText = 'all:initial;display:block;width:100%;text-align:left;font-family:system-ui,sans-serif;font-size:13px;color:#111;background:#fff;border:0;border-radius:6px;padding:7px 10px;cursor:pointer;';
            b.onmouseenter = function () { b.style.background = '#eee'; };
            b.onmouseleave = function () { b.style.background = '#fff'; };
            b.onclick = function (ev) { try { ev.stopPropagation(); } catch (e) {} hide(); try { cb(); } catch (err) {} };
            d.appendChild(b);
        };
        mk('Open larger image (IMU Lite)', function () { openLarger(false); });
        mk('Open larger in background tab', function () { openLarger(true); });
        mk('Copy image URL', function () {
            try {
                if (!state.url) return;
                if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(state.url);
                else if (typeof GM_setClipboard !== 'undefined') GM_setClipboard(state.url);
                else if (typeof GM !== 'undefined' && GM.setClipboard) GM.setClipboard(state.url);
            } catch (e) {}
        });
        document.documentElement.appendChild(d);
        menu = d;
        document.addEventListener('scroll', hide, true);
        document.addEventListener('mousedown', function (e) { try { if (menu && !menu.contains(e.target)) hide(); } catch (err) {} }, true);
        document.addEventListener('keydown', function (e) { try { if (e.key === 'Escape') hide(); } catch (err) {} }, true);
        return d;
    }
    function hide() { try { if (menu) menu.style.display = 'none'; } catch (e) {} }
    function show(x, y) {
        var m = ensureMenu(); if (!m) return;
        m.style.display = 'block';
        var w = 280, h = 130;
        try { w = m.offsetWidth || 280; h = m.offsetHeight || 130; } catch (e) {}
        m.style.left = Math.max(8, Math.min(x, (window.innerWidth || 1000) - w - 8)) + 'px';
        m.style.top = Math.max(8, Math.min(y, (window.innerHeight || 800) - h - 8)) + 'px';
        setTimeout(hide, 6000);
    }
    function openLarger(bg) {
        var u = state.url; if (!u) return;
        var big = genericLarger(u);
        try {
            if (typeof GM_openInTab !== 'undefined') { GM_openInTab(big, !!bg); return; }
        } catch (e) {}
        try { window.open(big, '_blank'); } catch (e) {}
    }

    // Single listener, document-idle, no observers. Negligible cost on Shorts.
    document.addEventListener('contextmenu', function (e) {
        try {
            if (!enabled) return;
            var u = targetUrl(e.target);
            if (!u) return;
            state.url = u;
            show(e.clientX, e.clientY);
        } catch (err) {}
    }, true);
})();
