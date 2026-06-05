import json
import urllib.request
import os

os.makedirs('web/libs/pyodide', exist_ok=True)

base_url = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/"
files = [
    "pyodide.mjs",
    "pyodide.asm.js",
    "pyodide.asm.wasm",
    "pyodide-lock.json"
]

print("Downloading Pyodide core files...")
for f in files:
    url = base_url + f
    dest = os.path.join('web/libs/pyodide', f)
    if not os.path.exists(dest):
        print(f"Downloading {f}...")
        urllib.request.urlretrieve(url, dest)
    else:
        print(f"{f} already exists.")

print("Reading lockfile to find packages...")
with open('web/libs/pyodide/pyodide-lock.json') as lf:
    lock = json.load(lf)

# Find numpy
numpy_info = lock['packages']['numpy']
numpy_file = numpy_info['file_name']
print(f"Numpy package file: {numpy_file}")

# We also need micropip and its dependencies
micropip_file = lock['packages']['micropip']['file_name']
packaging_file = lock['packages']['packaging']['file_name']

for pkg_file in [numpy_file, micropip_file, packaging_file]:
    url = base_url + pkg_file
    dest = os.path.join('web/libs/pyodide', pkg_file)
    if not os.path.exists(dest):
        print(f"Downloading {pkg_file}...")
        urllib.request.urlretrieve(url, dest)
    else:
        print(f"{pkg_file} already exists.")

print("Done downloading pyodide offline assets.")
