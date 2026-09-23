/* IMU Fixed options companion: global "Reset to defaults" button.
 *
 * Loaded by extension/options.html AFTER the engine script. The engine
 * re-renders its options DOM on tab switches, which destroys foreign nodes,
 * so besides an initial lookup this keeps a MutationObserver that re-inserts
 * the button right of Export whenever it goes missing. Everything is
 * defensive: if the engine page isn't ready, it retries briefly.
 *
 * (Site exclusions and popup position are native engine rows now —
 * Rules > Disabled websites, Popup > Popup position — no custom panel.)
 */
(function () {
	"use strict";

	var tries = 0;
	var observing = false;

	function resetAll() {
		if (!window.confirm("Reset ALL Image Max URL settings to defaults?\n\nThis clears synced settings (all devices) and reloads this page.")) {
			return;
		}
		var swallow = function () { try { if (chrome.runtime.lastError) {} } catch (e) {} };
		try { chrome.storage.sync.clear(swallow); } catch (e) {}
		try { chrome.storage.local.clear(swallow); } catch (e) {}
		setTimeout(function () { try { window.location.reload(); } catch (e) {} }, 400);
	}

	/* Returns true when no further work is needed right now. */
	function ensure() {
		try {
			var ex = document.getElementById("exportbtn");
			if (!ex || !ex.parentNode) return false;
			if (!document.getElementById("imufixed-resetbtn")) {
				var b = document.createElement("button");
				b.id = "imufixed-resetbtn";
				try { b.className = ex.className; } catch (e) {}
				b.textContent = "Reset to defaults";
				b.title = "Clear all IMU settings and restore defaults";
				b.style.marginLeft = "0.5em";
				b.onclick = resetAll;
				ex.parentNode.insertBefore(b, ex.nextSibling);
			}
			return true;
		} catch (e) { return false; }
	}

	function watch() {
		if (observing) return;
		try {
			var root = document.documentElement || document.body;
			if (!root || !window.MutationObserver) return;
			var mo = new MutationObserver(function () { ensure(); });
			mo.observe(root, { childList: true, subtree: true });
			observing = true;
		} catch (e) {}
	}

	function tick() {
		if (ensure()) { watch(); return; }
		if (++tries < 150) {
			setTimeout(tick, 100);
		} else {
			watch();
		}
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", function () { setTimeout(tick, 300); });
	} else {
		setTimeout(tick, 300);
	}
})();
