#!/usr/bin/env python
"""Generate THIRD-PARTY-LICENSES.md from the installed environment.

Reads requirements.txt, then takes name / version / licence / source URL / full licence
text from each installed distribution's own metadata, and appends the vendored front-end
assets under static/ plus the USDA dataset notice. Runs offline.

    /home/markus/miniconda3/envs/opennourish/bin/python gen_licenses.py          # write
    /home/markus/miniconda3/envs/opennourish/bin/python gen_licenses.py --check  # verify only

--check exits 1 when THIRD-PARTY-LICENSES.md is not what this environment produces, so the
document cannot silently drift from the lock again. Re-run after every requirements.txt
regeneration (see DEV-README.md and upgrade-research/PLAN.md).
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import re
import sys
from importlib import metadata as md

ROOT = pathlib.Path(__file__).resolve().parent
LOCK = ROOT / "requirements.txt"
OUT = ROOT / "THIRD-PARTY-LICENSES.md"
STATIC = ROOT / "static"

# Vendored, not installed: nothing in the dependency graph records these, so they are listed
# here and verified by content hash. Versions come from each file's own banner where one
# exists; html5-qrcode.min.js carries no banner and was identified by matching its sha256
# against the upstream release artifact (byte-identical to html5-qrcode@2.3.8 on npm).
VENDORED = [
    {
        "path": "bootstrap.min.css",
        "name": "Bootstrap (CSS)",
        "upstream": "https://github.com/twbs/bootstrap",
        "licence": "MIT",
        "version": None,  # read from the file banner
    },
    {
        "path": "bootstrap.bundle.min.js",
        "name": "Bootstrap (bundle, includes @popperjs/core)",
        "upstream": "https://github.com/twbs/bootstrap",
        "licence": "MIT",
        "version": None,
    },
    {
        "path": "bootstrap-icons.css",
        "name": "Bootstrap Icons (CSS)",
        "upstream": "https://github.com/twbs/icons",
        "licence": "MIT",
        "version": None,
    },
    {
        "path": "fonts/bootstrap-icons.woff2",
        "name": "Bootstrap Icons (font)",
        "upstream": "https://github.com/twbs/icons",
        "licence": "MIT",
        "version": "1.11.3",
    },
    {
        "path": "chart.js",
        "name": "Chart.js",
        "upstream": "https://github.com/chartjs/Chart.js",
        "licence": "MIT",
        "version": None,
    },
    {
        "path": "html5-qrcode.min.js",
        "name": "html5-qrcode",
        "upstream": "https://github.com/mebjas/html5-qrcode",
        # Apache-2.0, which carries an express patent grant: keep the notice with the copy.
        "licence": "Apache-2.0",
        "version": "2.3.8",
    },
]

USDA_NOTICE = """The USDA FoodData Central dataset is a product of the U.S. Department of
Agriculture and is in the public domain. No copyright is claimed on the original data. Users
are free to use, modify, and redistribute the data without restriction. The pinned drop is the
CSV export named in `entrypoint.sh`."""

SOURCE_KEYS = ("source", "source code", "repository", "homepage", "documentation")


def canon(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def read_lock(path: pathlib.Path) -> list[tuple[str, str]]:
    pins: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if "==" in line:
            name, _, ver = line.partition("==")
            pins.append((name.strip(), ver.strip()))
    return pins


def licence_expression(dist: md.Distribution) -> str:
    expr = (dist.metadata.get("License-Expression") or "").strip()  # PEP 639
    if expr:
        return expr
    raw = (dist.metadata.get("License") or "").strip()
    if raw and len(raw) < 60 and "\n" not in raw:
        return raw
    classifiers = [
        c.split(" :: ")[-1]
        for c in (dist.metadata.get_all("Classifier") or [])
        if c.startswith("License ::") and not c.endswith("OSI Approved")
    ]
    if classifiers:
        return classifiers[-1]
    return "unspecified — see the source URL below"


def source_url(dist: md.Distribution, name: str) -> str:
    wanted: dict[str, str] = {}
    for entry in dist.metadata.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        wanted[label.strip().lower()] = url.strip()
    for key in SOURCE_KEYS:
        if wanted.get(key):
            return wanted[key]
    return f"https://pypi.org/project/{name}/"


def licence_files(dist: md.Distribution) -> list[tuple[str, str]]:
    """Return (basename, text) for licence texts shipped inside the wheel."""
    found: list[tuple[str, str]] = []
    for pkg_file in dist.files or ():
        rel = str(pkg_file)
        base = rel.rsplit("/", 1)[-1]
        is_licence = "dist-info/licenses/" in rel.lower() or base.upper().startswith(
            ("LICENSE", "COPYING", "NOTICE", "AUTHORS")
        )
        if not is_licence:
            continue
        try:
            text = (
                dist.locate_file(rel)
                .read_text(encoding="utf-8", errors="replace")
                .strip()
            )
        except OSError:
            continue
        if len(text) > 80:  # skip placeholder stubs
            found.append((base, text))
    seen, unique = set(), []
    for base, text in sorted(found, key=lambda x: x[0]):
        if text in seen:
            continue
        seen.add(text)
        unique.append((base, text))
    return unique


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def banner_version(path: pathlib.Path) -> str | None:
    """Pull a version out of a `/*! ... v1.2.3 ... */` banner, if the file has one."""
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:600]
    except OSError:
        return None
    m = re.search(r"v?(\d+\.\d+\.\d+(?:[-+][\w.]+)?)", head)
    return m.group(1) if m else None


def render_package(
    name: str, pinned: str, dist: md.Distribution | None, problems: list[str]
) -> str:
    if dist is None:
        problems.append(f"{name}: pinned in requirements.txt but not installed")
        return f"## {name}\n\n**Version:** {pinned}\n\n**Licence:** not installed — regenerate the environment.\n"

    version = md.version(dist.metadata["Name"])
    if version != pinned:
        problems.append(f"{name}: lock says {pinned}, environment has {version}")

    out = [f"## {name}", ""]
    out.append(f"**Version:** {version}  ")
    out.append(f"**Licence:** {licence_expression(dist)}  ")
    out.append(f"**Source:** {source_url(dist, name)}")
    out.append("")
    texts = licence_files(dist)
    if not texts:
        out.append(
            "> This distribution ships no licence file; the licence above is taken from its "
            "package metadata. Read the full text at the source URL."
        )
    for base, text in texts:
        if len(texts) > 1:
            out += [f"*{base}*", "", "```", text, "```", ""]
        else:
            out += ["```", text, "```"]
    return "\n".join(out).rstrip() + "\n"


def render_vendored() -> list[str]:
    out = ["## Vendored front-end assets", ""]
    out += [
        "Served straight from `static/`; there is no npm or bundler step, so these copies are",
        "distributed with the image and are tracked by content hash. The `.map` source-map",
        "siblings ship alongside them and carry the same licence.",
        "",
    ]
    for item in VENDORED:
        path = STATIC / item["path"]
        if not path.exists():
            out += [
                f"### {item['name']}",
                "",
                f"`static/{item['path']}` is missing.",
                "",
            ]
            continue
        version = item["version"] or banner_version(path) or "unidentified"
        out += [
            f"### {item['name']}",
            "",
            f"**Version:** {version}  ",
            f"**Licence:** {item['licence']}  ",
            f"**Source:** {item['upstream']}  ",
            f"**File:** `static/{item['path']}` (`{path.stat().st_size}` bytes)  ",
            f"**sha256:** `{sha256(path)}`",
            "",
        ]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if THIRD-PARTY-LICENSES.md is stale instead of writing it",
    )
    args = parser.parse_args()

    if not LOCK.exists():
        print(f"error: no lock file at {LOCK}", file=sys.stderr)
        return 2

    pins = read_lock(LOCK)
    by_name = {
        canon(d.metadata["Name"]): d
        for d in md.distributions()
        if d.metadata.get("Name")
    }

    problems: list[str] = []
    body: list[str] = [
        "# Third-party licences",
        "",
        f"Generated by `gen_licenses.py` from the {len(pins)} distributions pinned in",
        "`requirements.txt`, plus the vendored assets under `static/`. **Do not edit by hand** —",
        "change the lock, rebuild the environment, then regenerate:",
        "",
        "```bash",
        "$P gen_licenses.py            # $P = the conda env interpreter, see AGENTS.md",
        "$P gen_licenses.py --check    # fails if this file no longer matches the lock",
        "```",
        "",
        "Licence texts are the ones each wheel actually ships.",
        "",
        "## Summary",
        "",
        "| package | version | licence |",
        "|---|---|---|",
    ]

    rows: list[tuple[str, str, str]] = []
    sections: list[str] = []
    for name, pinned in sorted(pins, key=lambda p: canon(p[0])):
        dist = by_name.get(canon(name))
        sections.append(render_package(name, pinned, dist, problems))
        if dist is not None:
            rows.append(
                (name, md.version(dist.metadata["Name"]), licence_expression(dist))
            )

    body += [f"| {pkg} | {ver} | {lic} |" for pkg, ver, lic in rows]
    body += ["", "## Python packages", ""] + sections
    body += render_vendored()
    body += [
        "## USDA FoodData Central",
        "",
        "**Licence:** Public domain (U.S. Government work)",
        "**Source:** https://fdc.nal.usda.gov/download-datasets.html",
        "",
        " ".join(USDA_NOTICE.split()),
        "",
    ]

    text = "\n".join(body).rstrip() + "\n"

    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print(
                "THIRD-PARTY-LICENSES.md is stale — run `gen_licenses.py` after any lock or "
                "static/ change.",
                file=sys.stderr,
            )
            return 1
        print(f"THIRD-PARTY-LICENSES.md is current ({len(pins)} packages).")
        return 0

    OUT.write_text(text, encoding="utf-8")
    print(
        f"wrote {OUT.name}: {len(pins)} packages, {len(VENDORED)} vendored assets, {len(text)} bytes"
    )
    for p in problems:
        print(f"  warning: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
