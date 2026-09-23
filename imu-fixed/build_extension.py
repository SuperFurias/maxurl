#!/usr/bin/env python3
"""Assemble imu-fixed-extension/ (load-unpacked build) from the fork tree.

All functional changes live in the committed sources:
  - engine behavior: src/userscript.ts (see imu-fixed/apply_source_patches.py)
  - extension behavior: extension/background.js, manifest.json,
    extension/options.html, extension/imu-fixed-options.js
This script only assembles and enforces packaging guarantees (idempotent):
  - manifest: no static excludes, document_idle, single-frame, engine filenames
  - userscript-bg.js freshness (regenerated copy of the built engine)
Usage from the fork root:  python imu-fixed/build_extension.py
Full engine rebuild first (after pulls):  npm install && npm run build
"""
import hashlib
import json
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent  # fork root
OUT = ROOT / "imu-fixed-extension"


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def main():
    engine = ROOT / "userscript.user.js"
    bg_src = ROOT / "userscript-bg.js"
    assert engine.exists(), "run npm run build first"

    # Keep the committed background copy in sync with the built engine.
    if not bg_src.exists() or sha(engine) != sha(bg_src):
        shutil.copy2(engine, bg_src)
        print("userscript-bg.js refreshed from userscript.user.js")

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "extension").mkdir(parents=True)
    (OUT / "resources").mkdir(parents=True)

    data = json.loads((ROOT / "manifest.json").read_bytes().decode("utf-8"))
    assert data["name"] == "Image Max URL", data["name"]
    cs = data["content_scripts"][0]
    cs.pop("exclude_matches", None)
    cs["all_frames"] = False
    cs["run_at"] = "document_idle"
    cs["js"] = ["userscript.user.js"]
    data["background"]["scripts"] = ["extension/background.js", "userscript-bg.js"]
    (OUT / "manifest.json").write_bytes((json.dumps(data, indent=2) + "\n").encode("utf-8"))

    # Apache-2.0 s4(a): every distributed copy carries the license text.
    shutil.copy2(ROOT / "LICENSE.txt", OUT / "LICENSE.txt")

    shutil.copy2(engine, OUT / "userscript.user.js")
    shutil.copy2(bg_src, OUT / "userscript-bg.js")
    for f in (ROOT / "extension").glob("*"):
        if f.is_file():
            shutil.copy2(f, OUT / "extension" / f.name)
    for f in (ROOT / "resources").glob("*"):
        if f.is_file():
            shutil.copy2(f, OUT / "resources" / f.name)

    opt = (OUT / "extension" / "options.html").read_text(encoding="utf-8")
    assert "../userscript.user.js" in opt, "options.html engine ref missing"
    assert "imu-fixed-options.js" in opt, "options.html companion ref missing"

    readme = ROOT / "imu-fixed" / "extension-README.md"
    if readme.exists():
        shutil.copy2(readme, OUT / "README.md")
    print("assembled:", sorted(p.name for p in OUT.rglob("*") if p.is_file()))


if __name__ == "__main__":
    main()
