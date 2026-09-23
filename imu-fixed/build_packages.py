#!/usr/bin/env python3
"""Build the shippable Chromium CRX from the fork tree.

Chromium-only: Firefox/XPI distribution was removed from this fork.
Provenance: CRX3 files assembled by third-party signers (python zip +
npx crx3) do not raise the install prompt, while a byte-equivalent tree
packed by Chromium's own packer installs. This script therefore packs
with an in-folder Chrome for Testing binary and signs with the
browser-generated key, exactly mirroring the working artifact.

One-time packer setup (inside this folder, untracked):
    npx --yes @puppeteer/browsers install chrome@stable --path Temp/cft

Run from fork root (order matters):
    python imu-fixed/build_extension.py   # refresh imu-fixed-extension/
    python imu-fixed/build_packages.py    # -> build/ImageMaxURL_crx3.crx
Requires: maxurl-opera.pem (gitignored browser-generated packing key;
never committed). NOTE: packing runs headed (headless silently skips it);
a Chrome window flashes briefly during the build.

Output (committed):
  build/ImageMaxURL_crx3.crx - Chromium/Opera, CRX3. The manifest inside
    carries no "key" (upstream Opera practice); the extension ID is pinned
    by the packing key, see extension/updates.xml.
"""
import glob
import json
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
UNPACKED = ROOT / "imu-fixed-extension"
TMP = ROOT / "imu-fixed" / "tmp_pkg"
BUILD = ROOT / "build"


def find_chrome():
    hits = sorted(glob.glob(str(ROOT / "Temp" / "cft" / "chrome" / "*" / "chrome-win64" / "chrome.exe")))
    assert hits, ("Chrome packer missing: run "
                  "npx --yes @puppeteer/browsers install chrome@stable --path Temp/cft")
    return hits[-1]


def main():
    assert "imu_fixed_disabled_hosts" in (UNPACKED / "userscript.user.js").read_text(
        encoding="utf-8", errors="replace"), "unpacked tree is stale, run build_extension.py first"
    if TMP.exists():
        shutil.rmtree(TMP)
    shutil.copytree(UNPACKED, TMP)
    man = json.loads((TMP / "manifest.json").read_text(encoding="utf-8"))
    man.pop("key", None)  # upstream Opera practice: no key in manifest
    (TMP / "manifest.json").write_bytes((json.dumps(man, indent=2) + "\n").encode("utf-8"))
    key = ROOT / "maxurl-opera.pem"
    assert key.exists(), "browser packing key missing (maxurl-opera.pem, gitignored)"
    out_crx = TMP.with_suffix(".crx")  # chrome writes <dir>.crx next to dir
    if out_crx.exists():
        out_crx.unlink()
    profile = TMP.parent / "tmp_profile"
    cmd = [find_chrome(), "--disable-gpu", "--no-first-run",
           f"--user-data-dir={profile}", f"--pack-extension={TMP}",
           f"--pack-extension-key={key}"]
    subprocess.run(cmd, check=False, cwd=ROOT)
    assert out_crx.exists(), "packer produced no CRX"
    target = BUILD / "ImageMaxURL_crx3.crx"
    shutil.move(str(out_crx), str(target))
    shutil.rmtree(TMP, ignore_errors=True)
    shutil.rmtree(profile, ignore_errors=True)
    print("packed", target, f"{target.stat().st_size // 1024} KiB")


if __name__ == "__main__":
    main()
