#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Generate and verify a deterministic, evidence-backed source closure."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
from pathlib import Path, PurePosixPath


ALLOWED_LICENSES = {"Apache-2.0", "BSD-3-Clause", "MIT"}
FORBIDDEN_LICENSE = re.compile(
    r"(?:^|[^A-Za-z])(?:A?GPL|LGPL|CC-BY-NC|NONCOMMERCIAL)", re.IGNORECASE
)
PID_PREFIX = re.compile(r"^\s*(?:(?:\[pid\s+(\d+)\]|(\d+))\s+)?(.*)$")
SYSCALL_RESULT = re.compile(r"^(\w+)\((.*)\)\s+=\s+(-?\d+)")
SPDX_COMMENT = re.compile(
    rb"^\s*(?:/\*+|//+|#+|--+)\s*SPDX-License-Identifier:\s*([^\r\n*]+)"
)
MAP_OBJECT = re.compile(r"(?<!\S)([^\s()]+\.a\([^)]+\.o\)|[^\s()]+\.o)(?!\S)")
LICENSE_BOUNDARY_NAMES = ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING")
# rename(2) moves content between names; renameat(2) and renameat2(2) take a
# directory descriptor before each path. The indexes are (old, new).
RENAME_PATH_INDEXES = {"rename": (0, 1), "renameat": (1, 3), "renameat2": (1, 3)}
# `/dev/fd/N` and `/proc/<pid>/fd/N` are descriptor aliases, not files: a shell
# process substitution passes one to a child, which opens it to read a pipe.
# They are consumption of a descriptor, never of a source file.
DESCRIPTOR_ALIAS = re.compile(r"^/(?:dev/fd|proc/(?:self|\d+)/fd)/\d+$")


def die(message: str) -> None:
    raise SystemExit(f"source-closure: ERROR: {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(131072), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_git(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(root), *arguments], capture_output=True, check=False
    )


def check_license(expression: str) -> None:
    if FORBIDDEN_LICENSE.search(expression) or expression not in ALLOWED_LICENSES:
        die(f"unknown, compound, or forbidden license expression: {expression}")


def load_roots(path: Path) -> list[dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != 1 or not isinstance(document.get("roots"), list):
        die("invalid roots declaration")
    roots = []
    for raw in document["roots"]:
        root = dict(raw)
        for key in ("name", "path", "repository", "commit", "license", "role"):
            if not root.get(key):
                die(f"source root missing {key}")
        root["path"] = str(Path(root["path"]).resolve())
        root["provenance"] = root.get("provenance", "git-exact")
        if root["provenance"] not in {"git-exact", "patched-tree"}:
            die(f"unsupported provenance mode for {root['name']}")
        if root["provenance"] == "patched-tree" and not root.get("patch_policy"):
            die(f"patched-tree root requires patch_policy: {root['name']}")
        check_license(root["license"])
        overrides = root.get("license_overrides", [])
        for override in overrides:
            relative = PurePosixPath(override.get("path", ""))
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                die(f"invalid license override path in {root['name']}")
            check_license(override["license"])
            override["path"] = relative.as_posix().rstrip("/")
            override["require_spdx"] = bool(override.get("require_spdx", False))
        root["license_overrides"] = sorted(overrides, key=lambda item: item["path"])
        roots.append(root)
    if len({root["name"] for root in roots}) != len(roots):
        die("duplicate source-root name")
    return sorted(roots, key=lambda item: item["name"])


def dep_record(path: Path) -> tuple[Path, set[Path]]:
    text = path.read_text(encoding="utf-8").replace("\\\n", " ")
    if ":" not in text:
        die(f"malformed depfile: {path}")
    target, prerequisites = text.split(":", 1)
    tokens = {Path(token) for token in shlex.split(prerequisites) if token != "\\"}
    return Path(target.strip()), tokens


def decode_trace_path(value: str) -> Path:
    return Path(bytes(value, "utf-8").decode("unicode_escape"))


def syscall_arguments(text: str) -> list[str]:
    """Split strace arguments without splitting quoted/nested expressions."""
    arguments = []
    start = 0
    depth = 0
    quoted = False
    escaped = False
    for index, character in enumerate(text):
        if escaped:
            escaped = False
        elif character == "\\" and quoted:
            escaped = True
        elif character == '"':
            quoted = not quoted
        elif not quoted and character in "[{(":
            depth += 1
        elif not quoted and character in "]})":
            depth -= 1
        elif not quoted and depth == 0 and character == ",":
            arguments.append(text[start:index].strip())
            start = index + 1
    arguments.append(text[start:].strip())
    return arguments


def quoted_path(argument: str, context: str) -> Path:
    match = re.fullmatch(r'"((?:[^"\\]|\\.)*)"', argument)
    if not match:
        die(f"cannot parse path argument in {context}: {argument}")
    return decode_trace_path(match.group(1))


def resolve_trace_path(
    raw_path: Path, pid: str, state: dict[str, dict], dirfd: str | None, context: str
) -> Path:
    if raw_path.is_absolute():
        return Path(os.path.abspath(raw_path))
    if pid not in state:
        die(f"relative path for pid {pid} has no inherited cwd state in {context}")
    if dirfd is None or dirfd == "AT_FDCWD":
        base = state[pid]["cwd"][0]
    else:
        descriptor_match = re.match(r"^(\d+)(?:<.*>)?$", dirfd)
        if not descriptor_match:
            die(f"unresolved dirfd {dirfd} for pid {pid} in {context}")
        descriptor = int(descriptor_match.group(1))
        if descriptor not in state[pid]["fds"]:
            die(f"unresolved dirfd {descriptor} for pid {pid} in {context}")
        base = state[pid]["fds"][descriptor]
    return Path(os.path.abspath(base / raw_path))


def trace_paths(path: Path, initial_cwd: Path, with_generated: bool = False):
    found: set[Path] = set()
    generated: set[Path] = set()
    directories: set[Path] = set()
    unfinished: dict[str, str] = {}
    state: dict[str, dict] = {}
    initial_pid: str | None = None

    def ensure_state(pid: str) -> None:
        if pid in state:
            return
        # With vfork(), strace can report the child's exec/open calls before
        # it reports the parent's resumed syscall and child PID.  At that
        # point there must be exactly one pending process-creation syscall;
        # any other situation is ambiguous and must fail closed.
        parents = [
            parent
            for parent, call in unfinished.items()
            if re.match(r"^(?:clone|clone3|fork|vfork)\(", call) and parent in state
        ]
        if len(parents) != 1:
            die(
                f"relative path for pid {pid} has no inherited cwd state "
                "from an unambiguous pending process creation"
            )
        parent = parents[0]
        state[pid] = {"cwd": [state[parent]["cwd"][0]], "fds": dict(state[parent]["fds"])}

    for raw_line in path.open("r", encoding="utf-8", errors="replace"):
        raw_line = raw_line.rstrip("\n")
        prefix = PID_PREFIX.match(raw_line)
        if not prefix:
            continue
        pid = prefix.group(1) or prefix.group(2) or "main"
        line = prefix.group(3)
        if initial_pid is None:
            initial_pid = pid
            state[pid] = {"cwd": [initial_cwd.resolve()], "fds": {}}
        if "<unfinished ...>" in line:
            unfinished[pid] = line.replace("<unfinished ...>", "")
            continue
        resumed = re.match(r"^<\.\.\.\s+\w+\s+resumed>(.*)$", line)
        if resumed:
            if pid not in unfinished:
                die(f"orphan resumed syscall for pid {pid} in {path}")
            line = unfinished.pop(pid) + resumed.group(1)
        match = SYSCALL_RESULT.match(line)
        if not match:
            continue
        syscall, argument_text, result_text = match.groups()
        result = int(result_text)
        if result < 0:
            continue
        arguments = syscall_arguments(argument_text)
        path_index = {
            "open": 0, "openat": 1, "openat2": 1, "execve": 0,
            "stat": 0, "statx": 1, "newfstatat": 1, "access": 0,
            "readlink": 0, "readlinkat": 1,
        }.get(syscall)
        needs_state = syscall in {
            "clone", "clone3", "fork", "vfork", "chdir", "fchdir",
        }
        rename_indexes = RENAME_PATH_INDEXES.get(syscall)
        if rename_indexes is not None:
            needs_state |= any(
                not quoted_path(arguments[index], line).is_absolute()
                for index in rename_indexes
            )
        if path_index is not None:
            candidate = quoted_path(arguments[path_index], line)
            needs_state |= not candidate.is_absolute() or "O_DIRECTORY" in argument_text
        if pid not in state and needs_state:
            ensure_state(pid)
        if syscall in {"clone", "clone3", "fork", "vfork"}:
            if pid not in state:
                die(f"successful {syscall} from pid {pid} without cwd state")
            shared_cwd = syscall.startswith("clone") and "CLONE_FS" in argument_text
            child_cwd = state[pid]["cwd"] if shared_cwd else [state[pid]["cwd"][0]]
            state.setdefault(
                str(result), {"cwd": child_cwd, "fds": dict(state[pid]["fds"])}
            )
            continue
        if syscall == "chdir":
            target = resolve_trace_path(quoted_path(arguments[0], line), pid, state, None, line)
            state[pid]["cwd"][0] = target
            continue
        if syscall == "fchdir":
            descriptor_match = re.match(r"^(\d+)(?:<.*>)?$", arguments[0])
            if not descriptor_match:
                die(f"successful fchdir has unparseable fd for pid {pid}: {arguments[0]}")
            descriptor = int(descriptor_match.group(1))
            if pid not in state or descriptor not in state[pid]["fds"]:
                die(f"successful fchdir has unresolved fd {descriptor} for pid {pid}")
            state[pid]["cwd"][0] = state[pid]["fds"][descriptor]
            continue
        if syscall == "close":
            if pid in state:
                state[pid]["fds"].pop(int(arguments[0]), None)
            continue
        if syscall == "fcntl":
            old_descriptor = int(arguments[0])
            duplicates = len(arguments) > 1 and arguments[1] in {
                "F_DUPFD", "F_DUPFD_CLOEXEC"
            }
            if duplicates and pid in state and old_descriptor in state[pid]["fds"]:
                state[pid]["fds"][result] = state[pid]["fds"][old_descriptor]
            continue
        if syscall in {"dup", "dup2", "dup3"}:
            old_descriptor = int(arguments[0])
            if pid in state and old_descriptor in state[pid]["fds"]:
                state[pid]["fds"][result] = state[pid]["fds"][old_descriptor]
            continue
        if rename_indexes is not None:
            # A rename moves content that already exists under another name.
            # Build systems write `X.tmpNNNN` with O_CREAT and rename it onto
            # `X`, so the destination is a build product although it was never
            # opened with a creating flag; CMake produces 84 such files in the
            # protected build. The destination inherits the SOURCE'S PROOF and
            # nothing more: an unproved source leaves the destination unproved,
            # so a rename can never launder an undeclared input into a
            # generated one.
            old_index, new_index = rename_indexes
            old_dirfd = arguments[0] if old_index == 1 else None
            new_dirfd = arguments[2] if new_index == 3 else None
            old_path = resolve_trace_path(
                quoted_path(arguments[old_index], line), pid, state, old_dirfd, line
            )
            new_path = resolve_trace_path(
                quoted_path(arguments[new_index], line), pid, state, new_dirfd, line
            )
            if old_path in generated:
                # The proof stays on both names: `generated` records what the
                # trace proved, not what the filesystem still holds, and the
                # source name is itself consumed by the stat calls around the
                # rename.
                generated.add(new_path)
            continue
        if path_index is None:
            continue
        dirfd = arguments[0] if path_index == 1 else None
        resolved = resolve_trace_path(
            quoted_path(arguments[path_index], line), pid, state, dirfd, line
        )
        if syscall in {"open", "openat", "openat2"} and (
            "O_DIRECTORY" in argument_text or candidate in {Path("."), Path("..")}
        ):
            if pid not in state:
                die(f"directory fd opened by pid {pid} without inherited state")
            state[pid]["fds"][result] = resolved
            directories.add(resolved)
        else:
            if syscall in {"open", "openat", "openat2"}:
                if any(flag in argument_text for flag in ("O_CREAT", "O_TRUNC", "O_EXCL")):
                    generated.add(resolved)
                if "O_WRONLY" not in argument_text:
                    found.add(resolved)
            else:
                if "st_mode=S_IFDIR" in argument_text:
                    directories.add(resolved)
                else:
                    found.add(resolved)
    if unfinished:
        die(f"unterminated syscalls in {path}: pids {sorted(unfinished)}")
    # Build-created intermediates are linkage evidence, not vendored source.
    # Existing directories are traversal metadata, not source files. Missing
    # paths remain so locate() fails closed unless the trace proved creation.
    aliases = {path for path in found if DESCRIPTOR_ALIAS.match(path.as_posix())}
    consumed = found - generated - directories - aliases
    return (consumed, generated) if with_generated else consumed


def consumed_paths(arguments: argparse.Namespace) -> set[Path]:
    paths: set[Path] = set()
    generated: set[Path] = set()
    for trace in arguments.strace:
        consumed, trace_generated = trace_paths(Path(trace), Path(arguments.cwd), True)
        paths.update(consumed); generated.update(trace_generated)
    for depfile in arguments.depfile:
        paths.update(dep_record(Path(depfile))[1])
    for record_path in capture_records(arguments):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        depfile = record.get("depfile")
        if not depfile:
            continue
        record_cwd = Path(record["cwd"])
        _, prerequisites = dep_record(Path(depfile))
        paths.update(path if path.is_absolute() else record_cwd / path for path in prerequisites)
    cwd = Path(arguments.cwd).resolve()
    normalized = {path if path.is_absolute() else cwd / path for path in paths}
    return normalized - generated


def capture_records(arguments: argparse.Namespace) -> list[Path]:
    result = []
    for directory in getattr(arguments, "capture", []):
        result.extend(Path(directory).glob("compiles/*.json"))
    return sorted(result)


def locate(path: Path, roots: list[dict]) -> tuple[dict, Path, Path]:
    lexical = Path(os.path.abspath(path))
    if not lexical.exists():
        die(f"consumed file is missing: {lexical}")
    if not lexical.is_file():
        die(f"consumed path is not a file: {lexical}")
    resolved = lexical.resolve()
    matches = []
    for root in roots:
        base = Path(root["path"])
        try:
            relative = lexical.relative_to(base)
        except ValueError:
            continue
        try:
            resolved.relative_to(base.resolve())
        except ValueError:
            die(f"symlink escapes source root: {lexical}")
        matches.append((len(base.parts), root, relative))
    if not matches:
        die(f"consumed file escapes declared source roots: {lexical}")
    _, root, relative = max(matches, key=lambda item: item[0])
    return root, relative, resolved


def license_rule(root: dict, relative: Path) -> tuple[str, bool]:
    selected = (root["license"], False)
    selected_length = -1
    relative_text = relative.as_posix()
    for override in root["license_overrides"]:
        prefix = override["path"]
        if (relative_text == prefix or relative_text.startswith(prefix + "/")) and len(prefix) > selected_length:
            selected = (override["license"], override["require_spdx"])
            selected_length = len(prefix)
    # A nested licence file is an unreviewed boundary unless an override covers it.
    current = relative.parent
    while current.parts:
        if any((Path(root["path"]) / current / name).is_file() for name in LICENSE_BOUNDARY_NAMES):
            if selected_length < len(current.as_posix()):
                die(f"nested license boundary lacks an override: {root['name']}/{current}")
        current = current.parent
    return selected


def file_license(path: Path, root: dict, relative: Path) -> str:
    expressions = set()
    for line in path.read_bytes().splitlines():
        match = SPDX_COMMENT.match(line)
        if match:
            expressions.add(match.group(1).decode("ascii", "replace").strip())
    if len(expressions) > 1:
        die(f"multiple SPDX expressions in {path}: {sorted(expressions)}")
    declared, require_spdx = license_rule(root, relative)
    if require_spdx and not expressions:
        die(f"SPDX identifier required by override: {root['name']}/{relative}")
    expression = next(iter(expressions), declared)
    check_license(expression)
    return expression


def origin_for(root: dict, relative: Path, resolved: Path) -> dict:
    origin = {
        "repository": root["repository"],
        "commit": root["commit"],
        "path": relative.as_posix(),
    }
    if root["provenance"] == "patched-tree":
        origin["patch_policy"] = root["patch_policy"]
        origin["content_sha256"] = sha256(resolved)
        return origin
    result = run_git(Path(root["path"]), "show", f"{root['commit']}:{relative.as_posix()}")
    if result.returncode:
        die(f"file absent from declared origin: {root['name']}/{relative}")
    if hashlib.sha256(result.stdout).hexdigest() != sha256(resolved):
        die(f"current bytes differ from declared origin blob: {root['name']}/{relative}")
    blob = run_git(Path(root["path"]), "rev-parse", f"{root['commit']}:{relative.as_posix()}")
    if blob.returncode:
        die(f"cannot resolve declared origin blob: {root['name']}/{relative}")
    origin["blob"] = blob.stdout.decode().strip()
    return origin


def closure_entries(arguments: argparse.Namespace, roots: list[dict]) -> list[dict]:
    entries = {}
    for path in consumed_paths(arguments):
        root, relative, resolved = locate(path, roots)
        key = (root["name"], relative.as_posix())
        entries[key] = {
            "source_root": root["name"],
            "path": relative.as_posix(),
            "sha256": sha256(resolved),
            "license": file_license(resolved, root, relative),
            "role": root["role"],
            "origin": origin_for(root, relative, resolved),
        }
    return [entries[key] for key in sorted(entries)]


def public_root(root: dict) -> dict:
    keys = ("name", "repository", "commit", "license", "role", "provenance")
    result = {key: root[key] for key in keys}
    if root["provenance"] == "patched-tree":
        result["patch_policy"] = root["patch_policy"]
    result["license_overrides"] = root["license_overrides"]
    return result


def write_json(path: str, document: dict) -> None:
    Path(path).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def make_sbom(manifest: dict) -> dict:
    serialized = json.dumps(manifest, sort_keys=True).encode()
    files = []
    for index, entry in enumerate(manifest["files"], 1):
        files.append({
            "SPDXID": f"SPDXRef-File-{index}",
            "fileName": f"{entry['source_root']}/{entry['path']}",
            "checksums": [{"algorithm": "SHA256", "checksumValue": entry["sha256"]}],
            "licenseConcluded": entry["license"],
            "licenseInfoInFiles": [entry["license"]],
            "copyrightText": "NOASSERTION",
        })
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "brickwright-source-closure",
        "documentNamespace": "https://brickwright.example/spdx/source-closure/" + hashlib.sha256(serialized).hexdigest(),
        "creationInfo": {"created": "1970-01-01T00:00:00Z", "creators": ["Tool: source_closure.py"]},
        "files": files,
    }


def normalized_build_path(path: Path, cwd: Path) -> str:
    absolute = path if path.is_absolute() else cwd / path
    normalized = Path(os.path.abspath(absolute))
    try:
        return normalized.relative_to(cwd).as_posix()
    except ValueError:
        return normalized.as_posix()


def map_identities(map_paths: list[str], cwd: Path) -> set[str]:
    identities = set()
    for map_path in map_paths:
        for token in MAP_OBJECT.findall(Path(map_path).read_text(encoding="utf-8", errors="replace")):
            archive = re.fullmatch(r"(.+\.a)\((.+\.o)\)", token)
            if archive:
                identities.add(normalized_build_path(Path(archive.group(1)), cwd) + f"({archive.group(2)})")
            else:
                identities.add(normalized_build_path(Path(token), cwd))
    return identities


def make_link_evidence(arguments: argparse.Namespace, manifest: dict, roots: list[dict]) -> dict:
    cwd = Path(arguments.cwd).resolve()
    manifested_paths = {}
    roots_by_name = {root["name"]: root for root in roots}
    for entry in manifest["files"]:
        absolute = (Path(roots_by_name[entry["source_root"]]["path"]) / entry["path"]).resolve()
        manifested_paths[absolute] = f"{entry['source_root']}/{entry['path']}"
    dependencies: dict[str, set[str]] = {}
    all_sources = set()
    for depfile in arguments.depfile:
        target, paths = dep_record(Path(depfile))
        target_id = normalized_build_path(target, cwd)
        sources = set()
        for path in paths:
            root, relative, _ = locate(path if path.is_absolute() else cwd / path, roots)
            source_id = f"{root['name']}/{relative.as_posix()}"
            sources.add(source_id)
            all_sources.add(source_id)
        if target_id in dependencies:
            die(f"ambiguous duplicate depfile target: {target_id}")
        dependencies[target_id] = sources
    for record_path in capture_records(arguments):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record_cwd = Path(record["cwd"])
        target, paths = dep_record(Path(record["depfile"]))
        target_id = normalized_build_path(record_cwd / target, cwd)
        sources = set()
        for path in paths:
            absolute = (path if path.is_absolute() else record_cwd / path).resolve()
            source_id = manifested_paths.get(absolute)
            if source_id is None:
                continue  # closure_entries already proved this prerequisite generated
            sources.add(source_id); all_sources.add(source_id)
        if target_id in dependencies and dependencies[target_id] != sources:
            die(f"ambiguous duplicate captured target: {target_id}")
        dependencies[target_id] = sources
    objects = {}
    basename_index: dict[str, list[str]] = {}
    for item in arguments.object:
        path = Path(item)
        if not path.is_file():
            die(f"object is missing: {path}")
        identity = normalized_build_path(path, cwd)
        if identity in objects:
            die(f"duplicate object input: {identity}")
        objects[identity] = path
        basename_index.setdefault(path.name, []).append(identity)
    map_objects = map_identities(arguments.map, cwd)
    for identity in map_objects:
        if "/" not in identity and "(" not in identity and len(basename_index.get(identity, [])) > 1:
            die(f"ambiguous basename-only map object: {identity}")
    rows = []
    for identity in sorted(objects):
        rows.append({
            "path": identity,
            "sha256": sha256(objects[identity]),
            "mentioned_in_map": identity in map_objects,
            "sources": sorted(dependencies.get(identity, set())),
        })
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    return {
        "schema": 1,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "map_files": [{"path": Path(item).name, "sha256": sha256(Path(item))} for item in sorted(arguments.map)],
        "map_objects": sorted(map_objects),
        "objects": rows,
        "depfile_prerequisites": sorted(all_sources),
    }


def generate(arguments: argparse.Namespace) -> None:
    if not arguments.depfile and not arguments.capture:
        die("compiler evidence requires --depfile or --capture")
    roots = load_roots(Path(arguments.roots))
    manifest = {
        "schema": 1,
        "allowed_licenses": sorted(ALLOWED_LICENSES),
        "source_roots": [public_root(root) for root in roots],
        "files": closure_entries(arguments, roots),
    }
    link_evidence = None
    if arguments.evidence:
        link_evidence = make_link_evidence(arguments, manifest, roots)
    write_json(arguments.output, manifest)
    write_json(arguments.sbom, make_sbom(manifest))
    if link_evidence is not None:
        write_json(arguments.evidence, link_evidence)


def verify(arguments: argparse.Namespace) -> None:
    if not arguments.depfile and not arguments.capture:
        die("compiler evidence requires --depfile or --capture")
    manifest = json.loads(Path(arguments.manifest).read_text(encoding="utf-8"))
    roots = load_roots(Path(arguments.roots))
    if manifest.get("source_roots") != [public_root(root) for root in roots]:
        die("manifest source-root metadata differs from declarations")
    actual_files = manifest.get("files", [])
    actual_keys = {(item.get("source_root"), item.get("path")) for item in actual_files}
    consumed_keys = set()
    for path in consumed_paths(arguments):
        root, relative, _ = locate(path, roots)
        consumed_keys.add((root["name"], relative.as_posix()))
    if consumed_keys != actual_keys:
        die(
            "evidence and manifest differ; "
            f"unmanifested={sorted(consumed_keys - actual_keys)}, stale={sorted(actual_keys - consumed_keys)}"
        )
    expected = closure_entries(arguments, roots)
    expected_by_key = {(item["source_root"], item["path"]): item for item in expected}
    for actual in actual_files:
        key = (actual["source_root"], actual["path"])
        wanted = expected_by_key[key]
        for field in ("sha256", "license", "role", "origin"):
            if actual.get(field) != wanted[field]:
                die(f"{field} mismatch: {key[0]}/{key[1]}")
    if actual_files != expected:
        die("manifest file ordering is not canonical")
    print(f"source-closure: verified {len(expected)} files")


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    def add_common(command: argparse.ArgumentParser) -> None:
        command.add_argument("--roots", required=True)
        command.add_argument("--cwd", required=True, help="initial cwd inherited by the first traced PID")
        command.add_argument("--strace", action="append", required=True)
        command.add_argument("--depfile", action="append", default=[])
        command.add_argument("--capture", action="append", default=[])

    generate_parser = commands.add_parser("generate")
    add_common(generate_parser)
    generate_parser.add_argument("--output", required=True)
    generate_parser.add_argument("--sbom", required=True)
    generate_parser.add_argument("--evidence")
    generate_parser.add_argument("--map", action="append", default=[])
    generate_parser.add_argument("--object", action="append", default=[])
    verify_parser = commands.add_parser("verify")
    add_common(verify_parser)
    verify_parser.add_argument("--manifest", required=True)
    return parser


def main() -> None:
    arguments = make_parser().parse_args()
    if arguments.command == "generate":
        generate(arguments)
    else:
        verify(arguments)


if __name__ == "__main__":
    main()
