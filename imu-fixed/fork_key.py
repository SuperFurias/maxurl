import base64
import hashlib
import json
import pathlib
import subprocess

ROOT = pathlib.Path(r"C:\AITools\.Visual Studio Code\Image-Max-URL-Fixed")
KEY = ROOT / "maxurl.pem"
PUB = ROOT / "maxurl.pub.der"

if not KEY.exists():
    subprocess.run(["openssl", "genrsa", "-out", str(KEY), "2048"], check=True)
    print("generated", KEY)
else:
    print("key exists, reusing", KEY)

subprocess.run(["openssl", "rsa", "-in", str(KEY), "-pubout", "-outform", "DER", "-out", str(PUB)],
               check=True, capture_output=True)
der = PUB.read_bytes()
PUB.unlink()
key_b64 = base64.b64encode(der).decode()
ext_id = "".join(chr(ord("a") + (b >> 4)) + chr(ord("a") + (b & 15)) for b in hashlib.sha256(der).digest()[:16])
print("extension id:", ext_id)

mp = ROOT / "manifest.json"
d = json.loads(mp.read_text(encoding="utf-8"))
d["key"] = key_b64
mp.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")

up = ROOT / "extension" / "updates.xml"
u = up.read_text(encoding="utf-8")
u = u.replace("momhpkepmajdopjgahiglmboldkepibg", ext_id)
u = u.replace("https://raw.githubusercontent.com/qsniyg/maxurl/master/build/ImageMaxURL_crx3.crx",
              "https://raw.githubusercontent.com/SuperFurias/maxurl/master/build/ImageMaxURL_crx3.crx")
u = u.replace('version="2026.6.0"', 'version="2026.6.6"')
up.write_text(u, encoding="utf-8")
print("manifest key + updates.xml done")
