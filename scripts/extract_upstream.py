#!/usr/bin/env python3
"""Extract the unchanged local Lean import closure from a pinned openai/math checkout.

Usage: python3 scripts/extract_upstream.py /path/to/openai-math [--destination DIR]
The checkout must be at UPSTREAM_COMMIT. Every copied byte is checked against its
Git blob before copying. No network requests or package downloads are performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path


UPSTREAM_URL = "https://github.com/openai/math.git"
UPSTREAM_COMMIT = "adc7f1241b42e322a6451854ab7e4b4c146bf78a"
SOLUTION_MODULE = "OAI.NumberTheory.DirichletL.Nonvanishing"
CHALLENGE_MODULE = "ComparatorChallenges.QuasiRiemannHypothesis"
MATHLIB_COMMIT = "d13f23b723b8a846827a245b89c10fc7d3f11612"
THEOREM = "OAI.riemannZeta_ne_zero_of_seven_eighths_lt_re"
RELLICH_COMMIT = "70f85d4c1bf99c6e7d61e8be4daa6f3664d08d23"
PNT_COMMIT = "c39a751132c88b6e8080b74c74023fd95b3d8be0"
PNT_DEPENDENCIES = {
    "LeanArchitect": "468e8f58fb4ad6e6ad672a08da6d0d0531e95a97",
    "checkdecls": "3d425859e73fcfbef85b9638c2a91708ef4a22d4",
    "leancert": "7f91b6eb3567437f6cfac03ed279706603ee22f4",
    "PrimeCert": "0803c2f6bd289c09704c7d352bb8fcf770cbb9b2",
}
# Exact dependency list from mathlib's lake-manifest.json at MATHLIB_COMMIT.
# These same records appear in the pinned openai/math manifest.
MATHLIB_DEPENDENCIES = {
    "plausible": "118aa17ee84656b8bd727fef7c458ee8c833385c",
    "LeanSearchClient": "ddf04cf3949fa556442341e87d47f9f6e6074707",
    "importGraph": "e928b72544873815af278d38681b31c0293588e3",
    "proofwidgets": "106ff4fafc74ef4ac99d81dbf3ab399118f497a5",
    "aesop": "355695d523e41d0554926416cba2a2b3544fbbc9",
    "Qq": "6a489d9af5d0c47e5b259e2e8bcdfc1811b5a259",
    "batteries": "f2effa3d803fda822b1f97b806c47cf2adfbcbc2",
    "Cli": "e92c9f15fdfacc8536f31cfb3b7ad26c3c8cd204",
}


def git(source: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(source), *args])


def without_comments(text: str) -> str:
    """Mask nested Lean comments and string literals, preserving line boundaries."""
    result = list(text)
    i = 0
    depth = 0
    in_string = False
    while i < len(text):
        if depth:
            if text.startswith("/-", i):
                depth += 1
                result[i:i + 2] = "  "
                i += 2
            elif text.startswith("-/", i):
                depth -= 1
                result[i:i + 2] = "  "
                i += 2
            else:
                if text[i] != "\n":
                    result[i] = " "
                i += 1
        elif in_string:
            if text[i] == "\\" and i + 1 < len(text):
                result[i:i + 2] = "  "
                i += 2
            else:
                if text[i] == '"':
                    in_string = False
                if text[i] != "\n":
                    result[i] = " "
                i += 1
        elif text.startswith("/-", i):
            depth = 1
            result[i:i + 2] = "  "
            i += 2
        elif text.startswith("--", i):
            end = text.find("\n", i)
            if end == -1:
                end = len(text)
            result[i:end] = " " * (end - i)
            i = end
        elif text[i] == '"':
            in_string = True
            result[i] = " "
            i += 1
        else:
            i += 1
    return "".join(result)


def imports(data: bytes) -> list[str]:
    """Read the module header; fail on import syntax this extractor cannot parse."""
    text = without_comments(data.decode("utf-8"))
    tokens = text.split()
    result: list[str] = []
    i = 0
    if tokens[:1] == ["prelude"]:
        i += 1
    if tokens[i:i + 1] == ["module"]:
        i += 1
    while i < len(tokens):
        # Lean 4 module headers can attach visibility/meta modifiers to imports.
        start = i
        while i < len(tokens) and tokens[i] in {"public", "private", "meta"}:
            i += 1
        if i >= len(tokens) or tokens[i] != "import":
            i = start
            break
        i += 1
        if i >= len(tokens) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9'.]*", tokens[i]):
            raise ValueError("Unsupported import syntax in module header")
        result.append(tokens[i])
        i += 1
    # A second import after a non-header token is suspicious, not silently omitted.
    if re.search(r"(?m)^\s*(?:(?:public|private|meta)\s+)*import\s", " ".join(tokens[i:])):
        raise ValueError("Import outside the parsed module header")
    return result


def module_path(name: str) -> Path:
    return Path(*name.split(".")).with_suffix(".lean")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="openai/math repository checkout")
    parser.add_argument("--destination", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    source = args.source.resolve()
    destination = args.destination.resolve()
    head = git(source, "rev-parse", "HEAD").decode().strip()
    if head != UPSTREAM_COMMIT:
        raise SystemExit(f"Expected upstream {UPSTREAM_COMMIT}; checkout is {head}")

    blobs: dict[str, str] = {}
    for line in git(source, "ls-tree", "-r", "--full-tree", UPSTREAM_COMMIT, "lean").splitlines():
        metadata, path = line.split(b"\t", 1)
        _mode, object_type, oid = metadata.split()
        if object_type == b"blob":
            blobs[path.decode()] = oid.decode()

    def checked_data(path: Path) -> bytes:
        relative = path.relative_to(source).as_posix()
        data = path.read_bytes()
        blob_hash = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if blobs.get(relative) != blob_hash:
            raise SystemExit(f"Source bytes differ from the pinned upstream Git blob: {relative}")
        return data

    lean_root = source / "lean"
    pending = [SOLUTION_MODULE, CHALLENGE_MODULE]
    local: dict[str, tuple[bytes, list[str]]] = {}
    external: set[str] = set()
    while pending:
        module = pending.pop()
        if module in local:
            continue
        path = lean_root / module_path(module)
        if not path.is_file():
            raise SystemExit(f"Missing local module: {module}")
        data = checked_data(path)
        module_imports = imports(data)
        local[module] = (data, module_imports)
        for dependency in module_imports:
            if (lean_root / module_path(dependency)).is_file():
                pending.append(dependency)
            elif dependency.split(".")[0] in {"Mathlib", "Lean", "Init", "Std", "RellichKondrachov", "MathlibExtensions", "PrimeNumberTheoremAnd"}:
                external.add(dependency)
            else:
                raise SystemExit(f"Unresolved external dependency: {dependency}")

    destination.mkdir(parents=True, exist_ok=True)
    records = []
    for module, (data, module_imports) in sorted(local.items()):
        relative = module_path(module)
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
        records.append({
            "path": relative.as_posix(),
            "upstream_path": "lean/" + relative.as_posix(),
            "git_blob_sha1": blobs["lean/" + relative.as_posix()],
            "module": module,
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "imports": module_imports,
        })

    support_files = ["ComparatorChallenges/QuasiRiemannHypothesis.json", "lean-toolchain", "LICENSE", "patches/rellich-kondrachov-lean4341.patch", "patches/PrimeNumberTheoremAnd-lean4341.patch"]
    for relative in support_files:
        data = checked_data(lean_root / relative)
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
        records.append({
            "path": relative,
            "upstream_path": "lean/" + relative,
            "git_blob_sha1": blobs["lean/" + relative],
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        })

    config = json.loads(checked_data(lean_root / "ComparatorChallenges/QuasiRiemannHypothesis.json"))
    upstream_lake_manifest = json.loads(checked_data(lean_root / "lake-manifest.json"))
    upstream_packages = {package["name"]: package for package in upstream_lake_manifest["packages"]}
    selected_revisions = {"mathlib": MATHLIB_COMMIT, **MATHLIB_DEPENDENCIES, "«rellich-kondrachov»": RELLICH_COMMIT, "PrimeNumberTheoremAnd": PNT_COMMIT, **PNT_DEPENDENCIES}
    selected_packages = []
    for name, revision in selected_revisions.items():
        package_record = upstream_packages[name]
        if package_record["rev"] != revision:
            raise SystemExit(f"Unexpected upstream dependency revision for {name}")
        selected_packages.append(package_record)
    lake_manifest = {
        "version": upstream_lake_manifest["version"],
        "packagesDir": upstream_lake_manifest["packagesDir"],
        "packages": selected_packages,
        "name": "quasi_riemann_seven_eighths",
        "lakeDir": upstream_lake_manifest["lakeDir"],
        "fixedToolchain": upstream_lake_manifest["fixedToolchain"],
    }
    lake_manifest_text = json.dumps(lake_manifest, indent=2) + "\n"
    (destination / "lake-manifest.json").write_text(lake_manifest_text, encoding="utf-8")
    package = f'''# Standalone extraction; Lean source files are unchanged from openai/math.
name = "quasi_riemann_seven_eighths"
version = "0.1.0"
defaultTargets = ["OAI"]

[leanOptions]
autoImplicit = false

[[require]]
name = "PrimeNumberTheoremAnd"
git = "https://github.com/AlexKontorovich/PrimeNumberTheoremAnd.git"
rev = "{PNT_COMMIT}"

[[require]]
name = "rellich-kondrachov"
git = "https://github.com/abenenson/rellich-kondrachov.git"
rev = "{RELLICH_COMMIT}"

# Preserve openai/math overrides for the PNT package dependencies.
[[require]]
name = "LeanArchitect"
git = "https://github.com/hanwenzhu/LeanArchitect.git"
rev = "{PNT_DEPENDENCIES['LeanArchitect']}"

[[require]]
name = "checkdecls"
git = "https://github.com/PatrickMassot/checkdecls.git"
rev = "{PNT_DEPENDENCIES['checkdecls']}"

[[require]]
name = "leancert"
git = "https://github.com/alerad/leancert.git"
rev = "{PNT_DEPENDENCIES['leancert']}"

[[require]]
name = "PrimeCert"
git = "https://github.com/b-mehta/PrimeCert.git"
rev = "{PNT_DEPENDENCIES['PrimeCert']}"

# Keep shared mathlib last so it overrides older dependency requirements.
[[require]]
name = "mathlib"
git = "https://github.com/leanprover-community/mathlib4.git"
rev = "{MATHLIB_COMMIT}"

[[lean_lib]]
name = "OAI"
roots = ["{SOLUTION_MODULE}"]
globs = ["OAI.+"]

[[lean_lib]]
name = "ComparatorChallenges"
roots = ["{CHALLENGE_MODULE}"]
globs = ["ComparatorChallenges.+"]
'''
    (destination / "lakefile.toml").write_text(package, encoding="utf-8")
    solution_data = [data for module, (data, _deps) in local.items() if module != CHALLENGE_MODULE]
    solution_text = [data.decode("utf-8") for data in solution_data]
    source_statistics = {
        "bytes": sum(len(data) for data in solution_data),
        "physical_lines": sum(len(content.splitlines()) for content in solution_text),
        "nonblank_lines": sum(sum(bool(line.strip()) for line in content.splitlines())
                              for content in solution_text),
    }
    code_findings = []
    for module, (data, _deps) in sorted(local.items()):
        if module == CHALLENGE_MODULE:
            continue
        code = without_comments(data.decode("utf-8"))
        for finding in re.finditer(r"\b(?:sorry|admit|axiom|unsafe|native_decide)\b", code):
            code_findings.append({
                "path": module_path(module).as_posix(),
                "line": code.count("\n", 0, finding.start()) + 1,
                "token": finding.group(),
            })
    manifest = {
        "schema_version": 1,
        "upstream": {"url": UPSTREAM_URL, "commit": UPSTREAM_COMMIT},
        "extraction": {
            "solution_module": SOLUTION_MODULE,
            "challenge_module": CHALLENGE_MODULE,
            "theorem": THEOREM,
            "method": "Transitive local import closure; exact bytes verified against upstream Git blobs",
            "local_solution_modules": len(local) - 1,
            "challenge_modules": 1,
            "external_import_roots": dict(sorted(Counter(x.split('.')[0] for x in external).items())),
            "external_imports": sorted(external),
            "missing_local_dependencies": [],
            "solution_source_statistics": source_statistics,
            "static_source_scan": {
                "method": "Comment/string-aware token search; Comparator performs the authoritative axiom/kernel check",
                "findings": code_findings,
            },
        },
        "toolchain": checked_data(lean_root / "lean-toolchain").decode().strip(),
        "mathlib": {"url": "https://github.com/leanprover-community/mathlib4.git", "commit": MATHLIB_COMMIT},
        "dependency_manifest": {
            "method": "Retain mathlib, its eight manifest dependencies, Rellich, PrimeNumberTheoremAnd and its four additional dependencies from upstream lake-manifest.json, preserving pinned package records",
            "mathlib_manifest_url": f"https://raw.githubusercontent.com/leanprover-community/mathlib4/{MATHLIB_COMMIT}/lake-manifest.json",
            "dependencies": selected_revisions,
            "generated_lake_manifest_sha256": hashlib.sha256(lake_manifest_text.encode()).hexdigest(),
        },
        "rellich": {
            "url": "https://github.com/abenenson/rellich-kondrachov.git",
            "commit": RELLICH_COMMIT,
            "compatibility_patch": "patches/rellich-kondrachov-lean4341.patch",
            "patch_method": "Apply exact upstream compatibility patch to pinned Rellich checkout before building",
        },
        "prime_number_theorem_and": {
            "url": "https://github.com/AlexKontorovich/PrimeNumberTheoremAnd.git",
            "commit": PNT_COMMIT,
            "compatibility_patch": "patches/PrimeNumberTheoremAnd-lean4341.patch",
            "patch_method": "Apply exact upstream compatibility patch to pinned PNT checkout before any root Lake invocation",
        },
        "comparator_config": config,
        "challenge_placeholder": "The upstream challenge theorem uses sorry intentionally; it is the trusted statement. The solution is in OAI.",
        "files": sorted(records, key=lambda x: x["path"]),
        "generated_lakefile_sha256": hashlib.sha256(package.encode()).hexdigest(),
    }
    (destination / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    for record in records:
        actual = hashlib.sha256((destination / record["path"]).read_bytes()).hexdigest()
        if actual != record["sha256"]:
            raise SystemExit(f"Post-copy hash mismatch: {record['path']}")
    print(json.dumps({
        "copied_lean_files": len(local),
        "solution_closure_files": len(local) - 1,
        "copied_support_files": len(support_files),
        "external_import_roots": manifest["extraction"]["external_import_roots"],
        "all_source_and_destination_hashes_verified": True,
        "destination": str(destination),
    }, indent=2))


if __name__ == "__main__":
    main()
