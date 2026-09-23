#!/usr/bin/env python3
"""Apply the IMU Fixed source patches to a pristine qsniyg/maxurl checkout.

Usage (from the fork root):
    python imu-fixed/apply_source_patches.py [fork-root]

Idempotent-guard: refuses to run twice (asserts no imuFixed* markers and no
imu_fixed_disabled_hosts key). After upstream pulls, re-run; any assert that
fails names the drifted anchor to update.

Patches (see fork README for rationale):
  P1  defaults: mouseover_position "cursor" -> "center"
  P2  defaults: + imu_fixed_disabled_hosts: ""
  P3  settings_meta: + Disabled websites row (category "rules", textarea)
  P4  update_dark_mode: mirror system default into orig_settings
  P5  problems loop: bruteforce forced off + mirror effective values to orig
  P6  do_config: two-key fast-bail wrapper (blocklist / global off)
  P7  locale: strip pt-BR (fork is English-only; other locales untouched)
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent
TS = ROOT / "src" / "userscript.ts"


def main():
    text = TS.read_text(encoding="utf-8")
    assert "imuFixedDoConfigOrig" not in text, "already patched (P6 present)"
    assert "imu_fixed_disabled_hosts" not in text, "already patched (P2/P3 present)"

    # P1: center default (line-anchored so inline requires:{...} can't match)
    m = re.findall(r'^([ \t]*)mouseover_position: "cursor",$', text, re.M)
    assert len(m) == 1, f"P1 anchor: {len(m)}"
    ind = m[0]
    text = text.replace(f'\n{ind}mouseover_position: "cursor",',
                        f'\n{ind}mouseover_position: "center",', 1)

    # P2: blocklist default right after it
    text = text.replace(f'\n{ind}mouseover_position: "center",',
                        f'\n{ind}mouseover_position: "center",\n{ind}imu_fixed_disabled_hosts: "",', 1)

    # P3: meta row before the mouseover_position meta block
    m2 = re.findall(r'\n([ \t]*)mouseover_position: \{\n', text)
    assert len(m2) == 1, f"P3 anchor: {len(m2)}"
    ind2 = m2[0]
    meta = (f'\n{ind2}imu_fixed_disabled_hosts: {{\n'
            f'{ind2}\tname: "Disabled websites",\n'
            f'{ind2}\tdescription: "Websites where the extension never loads its engine (one host per line, subdomains match automatically, empty runs everywhere). Request handling stops immediately; full effect after reload.",\n'
            f'{ind2}\ttype: "textarea",\n'
            f'{ind2}\tcategory: "rules"\n'
            f'{ind2}}},')
    text = text.replace(f'\n{ind2}mouseover_position: {{\n', meta + f'\n{ind2}mouseover_position: {{\n', 1)

    # P4: dark-mode system default must not flag the row as modified
    m3 = re.findall(r'^([ \t]*)set_default_value\("dark_mode", true\);', text, re.M)
    assert len(m3) == 1, f"P4 anchor: {len(m3)}"
    ind3 = m3[0]
    text = text.replace(f'{ind3}set_default_value("dark_mode", true);',
                        f'{ind3}set_default_value("dark_mode", true);\n'
                        f'{ind3}try {{ orig_settings["dark_mode"] = true; }} catch (e) {{}}', 1)

    # P5: bruteforce off by default + mirror effective problem defaults to orig
    m4 = re.findall(r'^([ \t]*)(settings\[option\] = array_indexof\(default_options\.exclude_problems, problem\) < 0;)',
                    text, re.M)
    assert len(m4) == 1, f"P5 anchor: {len(m4)}"
    ind4, stmt4 = m4[0]
    text = text.replace(f'{ind4}{stmt4}',
                        f'{ind4}{stmt4}\n'
                        f'{ind4}try {{ if (option === "allow_bruteforce") {{ settings[option] = false; }} }} catch (e) {{}}\n'
                        f'{ind4}try {{ orig_settings[option] = settings[option]; }} catch (e) {{}}', 1)

    # P6: fast-bail wrapper (single 2-key IPC before the full settings storm)
    m5 = re.findall(r'\n([ \t]*)function do_config\(\) \{', text)
    assert len(m5) == 1, f"P6 anchor: {len(m5)}"
    ind5 = m5[0]
    helpers = (
        f'\n{ind5}/* ==== IMU-FIXED: runtime host blocklist fast-path (single IPC) ==== */\n'
        f'{ind5}function imuFixedParseHosts(text) {{\n'
        f'{ind5}\tvar out = [];\n'
        f'{ind5}\ttry {{\n'
        f'{ind5}\t\tString(text || "").split(/[\\n,;]+/).forEach(function(line) {{\n'
        f'{ind5}\t\t\tvar h = String(line || "").trim().toLowerCase();\n'
        f'{ind5}\t\t\th = h.replace(/^\\*\\./, "").replace(/^https?:\\/\\//, "").split(/[\\/\\s]/)[0];\n'
        f'{ind5}\t\t\tif (h) out.push(h);\n'
        f'{ind5}\t\t}});\n'
        f'{ind5}\t}} catch (e) {{}}\n'
        f'{ind5}\treturn out;\n'
        f'{ind5}}}\n'
        f'{ind5}function imuFixedHostBlocked(host, listText) {{\n'
        f'{ind5}\ttry {{\n'
        f'{ind5}\t\thost = String(host || "").toLowerCase();\n'
        f'{ind5}\t\tif (!host) return false;\n'
        f'{ind5}\t\tvar list = imuFixedParseHosts(listText);\n'
        f'{ind5}\t\tfor (var i = 0; i < list.length; i++) {{\n'
        f'{ind5}\t\t\tvar e = list[i];\n'
        f'{ind5}\t\t\tif (host === e || host.slice(-e.length - 1) === "." + e) return true;\n'
        f'{ind5}\t\t}}\n'
        f'{ind5}\t}} catch (e2) {{}}\n'
        f'{ind5}\treturn false;\n'
        f'{ind5}}}\n'
        f'{ind5}function do_config() {{\n'
        f'{ind5}\ttry {{\n'
        f'{ind5}\t\tget_values(["imu_enabled", "imu_fixed_disabled_hosts"], function(fast) {{\n'
        f'{ind5}\t\t\ttry {{\n'
        f'{ind5}\t\t\t\tvar imuFixedOff = false;\n'
        f'{ind5}\t\t\t\ttry {{ imuFixedOff = !fast || fast.imu_enabled === false || fast.imu_enabled === "false"; }} catch (e3) {{}}\n'
        f'{ind5}\t\t\t\tvar imuFixedBlocked = false;\n'
        f'{ind5}\t\t\t\ttry {{\n'
        f'{ind5}\t\t\t\t\tvar imuFixedHn = "";\n'
        f'{ind5}\t\t\t\t\ttry {{ imuFixedHn = (window.location && window.location.hostname) || ""; }} catch (e4) {{}}\n'
        f'{ind5}\t\t\t\t\timuFixedBlocked = imuFixedHostBlocked(imuFixedHn, (fast && fast.imu_fixed_disabled_hosts) || "");\n'
        f'{ind5}\t\t\t\t}} catch (e5) {{}}\n'
        f'{ind5}\t\t\t\tif (imuFixedBlocked || imuFixedOff) {{\n'
        f'{ind5}\t\t\t\t\ttry {{ settings.imu_enabled = false; }} catch (e6) {{}}\n'
        f'{ind5}\t\t\t\t\ttry {{ console.log("[IMU Fixed] host-disabled/off, skipping heavy init"); }} catch (e7) {{}}\n'
        f'{ind5}\t\t\t\t\treturn;\n'
        f'{ind5}\t\t\t\t}}\n'
        f'{ind5}\t\t\t}} catch (e8) {{}}\n'
        f'{ind5}\t\t\timuFixedDoConfigOrig();\n'
        f'{ind5}\t\t}});\n'
        f'{ind5}\t}} catch (e9) {{ imuFixedDoConfigOrig(); }}\n'
        f'{ind5}}}\n'
        f'{ind5}function imuFixedDoConfigOrig() {{'
    )
    text = text.replace(f'\n{ind5}function do_config() {{', helpers, 1)

    # P7: English-only fork: strip pt-BR (header rows, translation entries,
    # supported_languages list entry, language-name block). pt-PT untouched.
    text = strip_ptbr(text)

    TS.write_text(text, encoding="utf-8")
    print("P1-P6 applied to", TS)


def strip_ptbr(text):
    lines = text.split("\n")
    out = []
    skipped = {"header": 0, "dict": 0, "list": 0, "langblock": 0, "localeblock": 0}
    i = 0

    def drop_block(start):
        depth = 0
        while start < len(lines):
            depth += lines[start].count("{") - lines[start].count("}")
            start += 1
            if depth <= 0:
                break
        return start

    while i < len(lines):
        l = lines[i]
        if re.match(r"^\s*//\s*@[A-Za-z_]+:pt-BR\b", l):
            skipped["header"] += 1
            i += 1
            continue
        if re.match(r'^\s*"pt-BR":\{\s*$', l.replace(" ", "")):
            i = drop_block(i)
            skipped["localeblock"] += 1
            continue
        if re.match(r'^\s*"pt-BR":', l):
            skipped["dict"] += 1
            i += 1
            continue
        if re.match(r'^\s*"pt-BR",\s*$', l):
            skipped["list"] += 1
            i += 1
            continue
        if re.match(r'^\s*"Portugu(\\u00EA|ê)s \(Brasil\)": \{$', l):
            i = drop_block(i)
            skipped["langblock"] += 1
            continue
        out.append(l)
        i += 1
    assert skipped["header"] >= 1, "P7 anchor: no pt-BR header rows"
    assert skipped["dict"] >= 1, "P7 anchor: no pt-BR dict entries"
    assert skipped["list"] == 1, f"P7 anchor: list entries {skipped['list']}"
    assert skipped["langblock"] == 1, f"P7 anchor: lang blocks {skipped['langblock']}"
    assert skipped["localeblock"] == 1, f"P7 anchor: locale blocks {skipped['localeblock']}"
    out = fix_dangling_commas(out)
    result = "\n".join(out)
    assert "pt-BR" not in result, "P7 incomplete: pt-BR remains"
    assert "pt_BR" not in result, "P7 incomplete: pt_BR remains"
    assert "Brasil" not in result, "P7 incomplete: Brasil remains"
    print("P7 stripped", skipped)
    return result


def fix_dangling_commas(lines):
    # tools/remcomments.js JSON.parses the strings table: a removed last
    # entry must not leave a trailing comma (neutral in JS/TS objects).
    fixed = 0
    for i in range(len(lines)):
        if not lines[i].rstrip().endswith(","):
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j < len(lines) and re.match(r"^\s*[}\]]", lines[j]):
            lines[i] = lines[i].rstrip()[:-1]
            fixed += 1
    print("P7 dangling commas fixed:", fixed)
    return lines


if __name__ == "__main__":
    main()
