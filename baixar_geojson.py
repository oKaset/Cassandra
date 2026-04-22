"""
baixar_geojson.py
Downloads the Portuguese municipalities GeoJSON from GADM (reliable mirror),
bypassing macOS LibreSSL certificate verification issues.
Run once: python baixar_geojson.py
"""

import ssl
import urllib.request
import os

# GADM 4.1 — Portugal level 2 = concelhos (municipalities)
# This is a stable, versioned URL that does not require authentication.
URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_PRT_2.json"
OUTPUT = "municipios.geojson"

# Create an unverified SSL context to work around macOS LibreSSL issues.
# Safe here because we are downloading public, read-only geodata.
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

print(f"Downloading from:\n  {URL}\n")

with urllib.request.urlopen(URL, context=ctx) as response:
    total = int(response.headers.get("Content-Length", 0))
    downloaded = 0
    chunk_size = 65536  # 64 KB
    with open(OUTPUT, "wb") as f:
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = downloaded / total * 100
                print(f"\r  {downloaded / 1_048_576:.1f} MB / {total / 1_048_576:.1f} MB ({pct:.0f}%)", end="", flush=True)

size_mb = os.path.getsize(OUTPUT) / 1_048_576
print(f"\n\nSaved: {OUTPUT}  ({size_mb:.2f} MB)")

if size_mb < 0.5:
    print("WARNING: file is suspiciously small — the download may have failed.")
else:
    print("Download looks good. You can now run: python mapa_cassandra.py")
