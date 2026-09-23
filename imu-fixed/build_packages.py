#!/usr/bin/env python3
"""Build fork-signed distributables from the fork tree.

Port of the firefox/chrome branches of tools/package_extension.sh, plus the
fork additions (userscript-bg.js, imu-fixed-options.js). Run from fork root:
    python imu-fixed/build_packages.py
Requires: npm run build first (fresh userscript_smaller.user.js).

Outputs (committed, like upstream):
  build/ImageMaxURL_unsigned.xpi  - Firefox (unsigned; smaller engine, AMO
                                    lines stripped, no key/update_url)
  build/ImageMaxURL_crx3.crx      - Chromium, CRX3 signed with the fork key
                                    (maxurl.pem, gitignored, never committed).
                                    Needs its manifest "key" to match, which
                                    it does since the fork key went in.
Not reproducible here (removed from the fork):
  build/ImageMaxURL_signed.xpi    - needs Mozilla signing with upstream creds
  build/ImageMaxURL_crx2.crx / _opera.crx - legacy/edge cases, see upstream
"""
import json
import pathlib
import re
import shutil
import subprocess
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
TMP = ROOT / "imu-fixed" / "tmp_pkg"
BUILD = ROOT / "build"

BASEFILES = [
    "LICENSE.txt", "manifest.json", "userscript.user.js",
    "resources/logo_40.png", "resources/logo_48.png", "resources/logo_96.png",
    "resources/disabled_40.png", "resources/disabled_48.png", "resources/disabled_96.png",
    "extension/background.js", "extension/options.css", "extension/options.html",
    "extension/popup.js", "extension/popup.html",
    "extension/welcome.html", "extension/welcome.js",
]
NONFFFILES = ["lib/ffmpeg.js", "lib/stream_parser.js"]
NONAMOFILES = ["lib/testcookie_slowaes.js", "lib/cryptojs_aes.js", "lib/jszip.js",
               "lib/shaka.debug.js", "lib/acorn_interpreter.js", "lib/BigInteger.js"]
# Fork additions (referenced by our manifest/options page):
FORKFILES = ["userscript-bg.js", "extension/imu-fixed-options.js"]

AMO_RE = re.compile(r"/\* *AMO_REMOVE *\*/")


def read(p):
    return (ROOT / p).read_bytes().decode("utf-8", errors="replace")


def stage(engine_content, firefox):
    """Mirror the repo-relative layout into TMP with per-target transforms."""
    if TMP.exists():
        shutil.rmtree(TMP)
    files = {}
    for p in BASEFILES + NONFFFILES + NONAMOFILES + FORKFILES:
        if p == "userscript.user.js" or p == "userscript-bg.js":
            files[p] = engine_content
        else:
            files[p] = read(p)
    if firefox:
        for p in ("userscript.user.js", "userscript-bg.js", "extension/background.js"):
            files[p] = "\n".join(l for l in files[p].split("\n") if not AMO_RE.search(l))
        files["userscript.user.js"] = files["userscript.user.js"].replace(
            "has_ffmpeg_lib = true", "has_ffmpeg_lib = false")
        files["userscript-bg.js"] = files["userscript-bg.js"].replace(
            "has_ffmpeg_lib = true", "has_ffmpeg_lib = false")
        man = json.loads(files["manifest.json"])
        for k in ("options_page", "key", "update_url"):
            man.pop(k, None)
        files["manifest.json"] = json.dumps(man, indent=2) + "\n"
        json.loads(files["manifest.json"])  # validate
    for p, content in files.items():
        dest = TMP / p
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content.encode("utf-8"))
    return files


def zip_out(zip_path, files):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(files):
            z.write(TMP / p, p)
    print("wrote", zip_path, f"{zip_path.stat().st_size // 1024} KiB")


def main():
    smaller = read("userscript_smaller.user.js")
    assert "imuFixedDoConfigOrig" in smaller, "engine was not built from patched sources"
    full = read("userscript.user.js")

    # Firefox unsigned XPI (smaller engine, like upstream)
    files = stage(smaller, firefox=True)
    zip_out(BUILD / "ImageMaxURL_unsigned.xpi", files)

    # Chromium zip + CRX3 (full engine, like unpacked; no AMO/manifest transforms)
    files = stage(full, firefox=False)
    chrome_zip = BUILD / "ImageMaxURL_chrome.zip"
    zip_out(chrome_zip, files)
    key = ROOT / "maxurl.pem"
    assert key.exists(), "fork signing key missing (see imu-fixed/fork_key.py)"
    import os
    # crx3 reads the zip from stdin (upstream: cat "$zip" | npx crx3 ...)
    cmd = ["npx", "crx3", "-p", str(key), "-o",
           str(BUILD / "ImageMaxURL_crx3.crx")]
    if os.name == "nt":
        cmd = ["cmd", "/c"] + cmd
    subprocess.run(cmd, input=chrome_zip.read_bytes(), check=True, cwd=ROOT)
    chrome_zip.unlink()
    shutil.rmtree(TMP, ignore_errors=True)
    print("signed", BUILD / "ImageMaxURL_crx3.crx")


if __name__ == "__main__":
    main()
