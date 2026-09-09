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


ALLOWED_LICENSES = {
    "Apache-2.0", "BSD-2-Clause", "BSD-2-Clause-FreeBSD", "BSD-3-Clause", "MIT",
    "TwistedSNMP",
}
REVIEWED_LICENSE_OVERRIDES = {
    ("nuttx", "include/search.h"): "LicenseRef-NuttX-PublicDomain",
    ("nuttx-apps", "graphics/nxwidgets/Make.defs"): "Apache-2.0",
    ("nuttx-apps", "graphics/twm4nx/Make.defs"): "Apache-2.0",
    ("nuttx-apps", "graphics/nxwm/Make.defs"): "Apache-2.0",
    ("nuttx", "libs/libc/search/hash_func.c"): "BSD-3-Clause-UC",
    ("nuttx", "libs/libc/stdlib/lib_wctomb.c"): "BSD-3-Clause-UC",
    ("nuttx", "libs/libc/string/lib_timingsafe_bcmp.c"): "ISC",
}
EXTRACTED_LICENSES = {
    "LicenseRef-NuttX-PublicDomain": {
        "name": "NuttX search.h public-domain dedication",
        "extractedText": "Written by J.T. Conklin <jtc@netbsd.org>\nPublic domain.",
    },
}
REVIEWED_LICENSE_NOTICES = {
    ("nuttx", "include/search.h"): (
        b"Written by J.T. Conklin <jtc@netbsd.org>\n * Public domain."
    ),
    ("nuttx-apps", "graphics/nxwidgets/Make.defs"): b"SPDX-License-Identifier: Apache-2.0",
    ("nuttx-apps", "graphics/twm4nx/Make.defs"): b"SPDX-License-Identifier: Apache-2.0",
    ("nuttx-apps", "graphics/nxwm/Make.defs"): b"SPDX-License-Identifier: Apache-2.0",
    ("nuttx", "libs/libc/search/hash_func.c"): b"Neither the name of the University nor the names of its contributors",
    ("nuttx", "libs/libc/stdlib/lib_wctomb.c"): b"Neither the name of the University nor the names of its contributors",
    ("nuttx", "libs/libc/string/lib_timingsafe_bcmp.c"): b"Permission to use, copy, modify, and distribute this software for any",
}
REVIEWED_LICENSE_HASHES = {
    ("nuttx", "libs/libc/search/hash_func.c"): "6826243ed593eabc859b30aecdd7ed737efddf89ea192a7a66c30daddbb2fc40",
    ("nuttx", "libs/libc/stdlib/lib_wctomb.c"): "a4d072c6993f70ecbb7089f2da4d6e967443be3f873f9c83e9a570d408af8bab",
    ("nuttx", "libs/libc/string/lib_timingsafe_bcmp.c"): "2bec5a443025b82ac87150ab7de6ba545ec4fda398c7857d61e2fe64c50877a9",
}
REVIEWED_NESTED_BOUNDARIES = {
    ("nuttx-apps", "graphics/nxwidgets/Make.defs"): {
        "boundary_path": "graphics/nxwidgets/COPYING",
        "boundary_sha256": "894d7166375b77cfd3d052d44ca90ebb7d0f3c5a4f7c57363af9d842bbaaad81",
        "markers": [b"Portions of this package derive from Woopsi", b"Copyright (c) 2007-2011, Antony Dzeryn", b"Neither the names \"Woopsi\", \"Simian Zombie\""],
        "future_consumed_files_require": "Apache-2.0 AND BSD-3-Clause",
    },
    ("nuttx-apps", "graphics/twm4nx/Make.defs"): {
        "boundary_path": "graphics/twm4nx/COPYING",
        "boundary_sha256": "f1f9cb0ed8a020522b4de0a5b84a2745d4de9609cf58f3b892abb689f6c8cb45",
        "markers": [b"Copyright 1989, 1994, 1998  The Open Group", b"Copyright 1988 by Evans & Sutherland Computer Corporation", b"Permission to use, copy, modify, distribute, and sell this software"],
        "future_consumed_files_require": "separate Twm4Nx source license review",
    },
    ("nuttx-apps", "graphics/nxwm/Make.defs"): {
        "boundary_path":"graphics/nxwm/COPYING", "boundary_sha256":"56180fed6813b73bb0728c24e7763a20c13234dceff4def8a823a4b6951bbc22",
        "markers":[b"copy of the BSD-style licensing",b"Licensed to the Apache Software Foundation (ASF)",b"Apache License, Version 2.0"],
        "future_consumed_files_require":"separate NxWM source license review",
        "note":"COPYING calls its terms BSD-style, but the included operative grant is Apache-2.0; no BSD license is inferred.",
    },
}
REVIEWED_BOUNDARY_LICENSE_SELECTIONS = {
    ("mbedtls", "framework/CMakeLists.txt"): {
        "source_sha256":"bdcf4a6aa867ba4855d26043ec869961fa5ac8a6b2fa6856689d0ae4d6aac5b6",
        "boundary_path":"framework/LICENSE", "boundary_sha256":"11402351e38392230bb8934ba1095c0c0049a296c0f8821f76e4672dff54b490",
        "declared":"Apache-2.0 OR GPL-2.0-or-later", "concluded":"Apache-2.0",
        "markers":[b"dual [Apache-2.0]",b"OR [GPL-2.0-or-later]",b"users may choose which of these licenses"],
    },
}
REVIEWED_SPDX_ANOMALIES = {
    ("nuttx", "fs/mnemofs/Make.defs"): {
        "sha256": "020f7d73c2e8647520012db2c76d9702657c0368f601cd7415207067bfd5c3d3",
        "raw_tags": ["Apache-2.0 or BSD-3-Clause", "BSD-3-Clause"],
        "concluded": "BSD-3-Clause",
        "markers": [b"Alternatively, the contents of this file may be used under the terms of", b"Redistribution and use in source and binary forms"],
    },
}
FORBIDDEN_LICENSE = re.compile(
    r"(?:^|[^A-Za-z])(?:A?GPL|LGPL|CC-BY-NC|NONCOMMERCIAL)", re.IGNORECASE
)
PID_PREFIX = re.compile(r"^\s*(?:(?:\[pid\s+(\d+)\]|(\d+))\s+)?(.*)$")
SYSCALL_RESULT = re.compile(r"^(\w+)\((.*)\)\s+=\s+(-?\d+)")
SPDX_COMMENT = re.compile(
    rb"^\s*(?:/\*+|\*|//+|#+|--+)\s*SPDX-License-Identifier:\s*([^\r\n*]+)"
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

def relocation(arguments: argparse.Namespace) -> tuple[Path,Path] | None:
    raw=getattr(arguments,"captured_repository_root",None)
    if raw is None: return None
    old=Path(raw)
    if not old.is_absolute() or old==Path("/"): die("captured repository root must be an absolute non-root path")
    old=Path(os.path.abspath(old)); new=Path(arguments.repository).resolve()
    if old==new or old in new.parents or new in old.parents: die("captured and replay repository roots overlap")
    return old,new

def replay_path(path: Path, arguments: argparse.Namespace) -> Path:
    mapping=relocation(arguments)
    if mapping is None or not path.is_absolute(): return path
    old,new=mapping
    try: relative=path.relative_to(old)
    except ValueError: return path
    return new/relative

def recorded_path(value: str | Path, cwd: Path, arguments: argparse.Namespace) -> Path:
    path=Path(value)
    return replay_path(path,arguments) if path.is_absolute() else cwd/path


def run_git(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(root), *arguments], capture_output=True, check=False
    )


def check_license(expression: str, context: str | None = None) -> None:
    if FORBIDDEN_LICENSE.search(expression) or expression not in ALLOWED_LICENSES:
        suffix = f" at {context}" if context else ""
        die(f"unknown, compound, or forbidden license expression: {expression}{suffix}")

def validate_boundary_selection(path: Path, root_path: Path, selection: dict, label: str) -> tuple[str,str,dict]:
    boundary=root_path/selection["boundary_path"]
    if sha256(path)!=selection["source_sha256"]: die(f"reviewed boundary-selected source drift: {label}")
    if boundary.is_symlink() or not boundary.is_file() or not boundary.resolve().is_relative_to(root_path.resolve()) or sha256(boundary)!=selection["boundary_sha256"] or any(x not in boundary.read_bytes() for x in selection["markers"]): die(f"reviewed boundary license drift: {label}")
    return selection["concluded"],selection["declared"],{"kind":"reviewed-boundary-license-selection","license_source":selection["boundary_path"],"license_sha256":selection["boundary_sha256"],"selected":selection["concluded"]}


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
            override["path"] = relative.as_posix().rstrip("/")
            override["require_spdx"] = bool(override.get("require_spdx", False))
            reviewed = REVIEWED_LICENSE_OVERRIDES.get((root["name"], override["path"]))
            if override["license"] != reviewed:
                check_license(override["license"])
            elif not override["require_spdx"] and (root["name"],override["path"]) not in REVIEWED_BOUNDARY_LICENSE_SELECTIONS:
                die(f"reviewed license override requires SPDX: {root['name']}/{relative}")
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
    if dirfd is None or re.match(r"^AT_FDCWD(?:<.*>)?$", dirfd):
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


def trace_descriptor(value: str, pid: str, syscall: str) -> int:
    match = re.match(r"^(\d+)(?:<.*>)?$", value)
    if not match:
        die(f"successful {syscall} has unparseable fd for pid {pid}: {value}")
    return int(match.group(1))


def trace_lines(path: Path):
    """Yield trace lines while guaranteeing closure on parser failure."""
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        yield from stream


def trace_paths(path: Path, initial_cwd: Path, with_generated: bool = False):
    found: set[Path] = set()
    strong_content: set[Path] = set()
    generated: set[Path] = set()
    directories: set[Path] = set()
    deferred_generated: dict[str, list[tuple[Path, str | None, str]]] = {}
    unfinished: dict[str, str] = {}
    state: dict[str, dict] = {}
    initial_pid: str | None = None

    def resolve_deferred(pid: str) -> None:
        for candidate, dirfd, context in deferred_generated.pop(pid, []):
            generated.add(resolve_trace_path(candidate, pid, state, dirfd, context))

    def ensure_state(pid: str) -> None:
        if pid in state:
            resolve_deferred(pid)
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
        resolve_deferred(pid)

    for raw_line in trace_lines(path):
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
            # Under parallel fork/vfork tracing a child can create its redirected
            # output before strace reports which pending parent returned that PID.
            # Its relative name cannot be resolved yet, but it is write-created
            # and therefore cannot be source input. Ignore only this narrow case;
            # a later relative read still fails unless the parent mapping arrived.
            creating = syscall in {"open", "openat", "openat2"} and any(
                flag in argument_text for flag in ("O_CREAT", "O_TRUNC", "O_EXCL")
            )
            if creating and path_index is not None and not candidate.is_absolute():
                dirfd = arguments[0] if path_index == 1 else None
                deferred_generated.setdefault(pid, []).append((candidate, dirfd, line))
                continue
            ensure_state(pid)
        if syscall in {"clone", "clone3", "fork", "vfork"}:
            if pid not in state:
                die(f"successful {syscall} from pid {pid} without cwd state")
            shared_cwd = syscall.startswith("clone") and "CLONE_FS" in argument_text
            child_cwd = state[pid]["cwd"] if shared_cwd else [state[pid]["cwd"][0]]
            state.setdefault(
                str(result), {"cwd": child_cwd, "fds": dict(state[pid]["fds"])}
            )
            resolve_deferred(str(result))
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
                state[pid]["fds"].pop(trace_descriptor(arguments[0], pid, syscall), None)
            continue
        if syscall == "fcntl":
            old_descriptor = trace_descriptor(arguments[0], pid, syscall)
            duplicates = len(arguments) > 1 and arguments[1] in {
                "F_DUPFD", "F_DUPFD_CLOEXEC"
            }
            if duplicates and pid in state and old_descriptor in state[pid]["fds"]:
                state[pid]["fds"][result] = state[pid]["fds"][old_descriptor]
            continue
        if syscall in {"dup", "dup2", "dup3"}:
            old_descriptor = trace_descriptor(arguments[0], pid, syscall)
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
                # Metadata-only traversal of directories and symlinks is not
                # file-content consumption. The same applies to regular-file
                # stat/access checks: this trace did not capture read(2), so
                # only an open content candidate, exec, or successful readlink
                # can prove content use outside compiler/linker evidence.
                if "st_mode=S_IFDIR" in argument_text:
                    directories.add(resolved)
                elif syscall in {"execve", "readlink", "readlinkat"}:
                    found.add(resolved)
                    strong_content.add(resolved)
    if unfinished:
        die(f"unterminated syscalls in {path}: pids {sorted(unfinished)}")
    if deferred_generated:
        die(f"generated paths lack unambiguous inherited cwd state: pids {sorted(deferred_generated)}")
    # Build-created intermediates are linkage evidence, not vendored source.
    # Existing directories are traversal metadata, not source files. Missing
    # paths remain so locate() fails closed unless the trace proved creation.
    aliases = {path for path in found if DESCRIPTOR_ALIAS.match(path.as_posix())}
    # A configure/build traversal may first read a symlink and later stat the
    # same lexical name after following it to a directory.  The successful
    # readlink is content evidence and must dominate that directory metadata.
    consumed = (found - generated - aliases) - (directories - strong_content)
    return (consumed, generated) if with_generated else consumed


def cached_trace_paths(arguments: argparse.Namespace, path: Path, initial_cwd: Path):
    """Parse one immutable trace once per command invocation."""
    resolved = path.resolve()
    status = resolved.stat()
    key = (
        resolved, initial_cwd.resolve(), status.st_dev, status.st_ino,
        status.st_size, status.st_mtime_ns, status.st_ctime_ns,
    )
    cache = getattr(arguments, "_trace_paths_cache", None)
    if cache is None:
        cache = {}
        setattr(arguments, "_trace_paths_cache", cache)
    if key not in cache:
        consumed, generated = trace_paths(resolved, initial_cwd, True)
        cache[key] = (frozenset(consumed), frozenset(generated))
    consumed, generated = cache[key]
    return set(consumed), set(generated)


def consumed_paths(arguments: argparse.Namespace) -> set[Path]:
    paths: set[Path] = set()
    generated: set[Path] = set()
    for trace in arguments.strace:
        consumed, trace_generated = cached_trace_paths(arguments, Path(trace), Path(arguments.cwd))
        consumed={replay_path(path,arguments) for path in consumed}; trace_generated={replay_path(path,arguments) for path in trace_generated}
        paths.update(consumed); generated.update(trace_generated)
    repository = Path(arguments.repository).resolve()
    for trace in getattr(arguments, "repository_trace", []):
        consumed, trace_generated = cached_trace_paths(arguments, Path(trace), Path(arguments.cwd))
        consumed={replay_path(path,arguments) for path in consumed}; trace_generated={replay_path(path,arguments) for path in trace_generated}
        paths.update(path for path in consumed if path.is_relative_to(repository))
        generated.update(trace_generated)
    for trace in getattr(arguments, "flow_trace", []):
        _, trace_generated = cached_trace_paths(arguments, Path(trace), Path(arguments.cwd))
        trace_generated={replay_path(path,arguments) for path in trace_generated}
        generated.update(trace_generated)
    for depfile in arguments.depfile:
        paths.update(replay_path(path,arguments) for path in dep_record(Path(depfile))[1])
    reachable_records = reachable_capture_records(arguments)
    generated.update(linked_archive_producer_outputs(arguments))
    for record_path in reachable_records:
        record = json.loads(record_path.read_text(encoding="utf-8"))
        depfile = record.get("depfile")
        if not depfile:
            continue
        record_cwd = replay_path(Path(record["cwd"]),arguments)
        _, prerequisites = dep_record(Path(depfile))
        paths.update(replay_path(path,arguments) if path.is_absolute() else record_cwd / path for path in prerequisites)
    for directory in getattr(arguments, "capture", []):
        for record_path in Path(directory).glob("compiles/*.json"):
            record = json.loads(record_path.read_text(encoding="utf-8"))
            output = record.get("output")
            if output and record.get("output_sha256"):
                path = recorded_path(output,replay_path(Path(record["cwd"]),arguments),arguments).resolve()
                if path.is_file() and sha256(path) == record["output_sha256"]:
                    generated.add(path)
        for record_path in Path(directory).glob("links/*.json"):
            record=json.loads(record_path.read_text()); cwd=replay_path(Path(record["cwd"]),arguments)
            argv=record.get("argv",[])
            for index,value in enumerate(argv):
                raw = argv[index+1] if value == "-T" and index+1 < len(argv) else value[2:] if value.startswith("-T") else None
                if raw:
                    paths.add(recorded_path(raw,cwd,arguments))
    cwd = Path(arguments.cwd).resolve()
    lexical = {
        Path(os.path.abspath(path if path.is_absolute() else cwd / path))
        for path in paths
    }
    declared, generated_rows = declared_generated(arguments)
    symlinks, symlink_rows = declared_symlinks(arguments)
    if {item["path"] for item in generated_rows} & {item["path"] for item in symlink_rows}:
        die("generated file and symlink paths collide")
    observed_symlinks={path for path in lexical if path.is_symlink()}
    if symlinks != observed_symlinks:
        die("consumed and declared generated symlink sets differ")
    lexical = {path for path in lexical if path not in symlinks and not (path.is_dir() and not path.is_symlink() and path.name != ".git")}
    normalized = {path.resolve() for path in lexical}
    # A file symlink is topology plus a byte-bearing target.  Directory links
    # need only topology here; their consumed descendants enter independently.
    normalized.update(
        (repository / item["target"]).resolve()
        for item in symlink_rows if item["target_type"] == "file"
    )
    return (normalized - generated) | (normalized & declared)


def declared_generated(arguments: argparse.Namespace) -> tuple[set[Path], list[dict]]:
    result, rows = set(), []
    repository = Path(arguments.repository).resolve()
    captured = {}
    for directory in getattr(arguments, "capture", []):
        capture = Path(directory)
        for record_path in capture.glob("links/*.json"):
            record = json.loads(record_path.read_text(encoding="utf-8"))
            cwd = replay_path(Path(record["cwd"]),arguments)
            for item in record.get("link_inputs", []):
                logical = recorded_path(item["argument"],cwd,arguments).resolve()
                preserved = capture / item["path"]
                if not preserved.is_file() or sha256(preserved) != item.get("sha256"):
                    die(f"captured generated input is missing or changed: {logical}")
                if logical in captured and captured[logical] != item["sha256"]:
                    die(f"ambiguous captured generated input: {logical}")
                captured[logical] = item["sha256"]
    for declaration in getattr(arguments, "generated", []):
        declaration_path = Path(declaration)
        if declaration_path.is_absolute() or ".." in declaration_path.parts:
            die("generated-input declaration must be repository-relative")
        document = json.loads((repository / declaration_path).read_text(encoding="utf-8"))
        if document.get("schema") != "brickwright/generated-build-inputs/v1":
            die("invalid generated-input declaration")
        for item in document.get("files", []):
            relative = PurePosixPath(item.get("path", ""))
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                die("generated-input path escapes repository")
            path = (repository / relative.as_posix()).resolve()
            try: path.relative_to(repository)
            except ValueError: die("generated-input symlink escapes repository")
            actual_hash = sha256(path) if path.is_file() else captured.get(path)
            if actual_hash is None: die(f"declared generated input is missing: {relative}")
            if actual_hash != item.get("sha256"):
                die(f"declared generated input hash mismatch: {relative}")
            if not isinstance(item.get("generator_argv"), list) or not item["generator_argv"]:
                die(f"declared generated input lacks generator: {relative}")
            result.add(path.resolve())
            rows.append({"path":relative.as_posix(), "sha256":item["sha256"],
                         "generator_argv":item["generator_argv"], "evidence":item.get("evidence"),
                         **({"license_boundary":item["license_boundary"]} if "license_boundary" in item else {})})
    return result, sorted(rows, key=lambda x:x["path"])


def declared_symlinks(arguments: argparse.Namespace) -> tuple[set[Path], list[dict]]:
    repository = Path(arguments.repository).resolve(); paths=set(); rows=[]
    for declaration in getattr(arguments, "generated", []):
        declaration_path=Path(declaration)
        if declaration_path.is_absolute() or ".." in declaration_path.parts:
            die("generated-input declaration must be repository-relative")
        document=json.loads((repository/declaration_path).read_text())
        items=document.get("symlinks", [])
        if not isinstance(items,list): die("invalid generated symlink declaration")
        for item in items:
            if not isinstance(item,dict): die("invalid generated symlink")
            logical=PurePosixPath(item.get("path","")); target=PurePosixPath(item.get("target",""))
            if any(p.is_absolute() or not p.parts or ".." in p.parts for p in (logical,target)):
                die("generated symlink path or target escapes repository")
            link=repository/logical.as_posix(); target_path=repository/target.as_posix()
            current=repository
            for part in logical.parts[:-1]:
                current/=part
                if current.is_symlink(): die("generated symlink parent contains symlink")
            current=repository
            for part in target.parts:
                current/=part
                if current.is_symlink(): die("generated symlink target contains symlink")
            expected=target_path.resolve()
            if not link.is_symlink(): die(f"declared generated symlink is missing: {logical}")
            try: expected.relative_to(repository)
            except ValueError: die("generated symlink target escapes repository")
            try: actual=link.resolve(strict=True)
            except (OSError, RuntimeError): die("generated symlink is dangling or loops")
            if actual!=expected: die("generated symlink target differs")
            kind=item.get("target_type")
            if kind not in {"file","directory"} or (kind=="file")!=actual.is_file() or (kind=="directory")!=actual.is_dir():
                die("generated symlink target type differs")
            if link in paths: die("duplicate generated symlink")
            paths.add(link); rows.append({"path":logical.as_posix(),"target":target.as_posix(),"target_type":kind,"evidence":item.get("evidence")})
    return paths, sorted(rows,key=lambda x:x["path"])


def declared_external(arguments: argparse.Namespace) -> tuple[set[Path], list[dict]]:
    paths, rows = set(), []
    allowed = {"arm-toolchain", "host-tool"}
    repository = Path(arguments.repository).resolve()
    external_roots = {}
    for value in getattr(arguments, "external_root", []):
        if "=" not in value: die("external root must be BOUNDARY=PATH")
        name, raw = value.split("=", 1)
        if name in external_roots or name not in allowed: die("invalid external root boundary")
        external_roots[name] = Path(raw).resolve()
    for declaration in getattr(arguments, "external", []):
        declaration_path = Path(declaration)
        if declaration_path.is_absolute() or ".." in declaration_path.parts:
            die("external-input declaration must be repository-relative")
        document = json.loads((repository / declaration_path).read_text(encoding="utf-8"))
        if document.get("schema") != "brickwright/external-build-inputs/v1":
            die("invalid external-input declaration")
        boundary = document.get("boundary")
        root = external_roots.get(boundary)
        lock = document.get("lock", {})
        if boundary not in allowed or root is None or not isinstance(lock, dict):
            die("external-input boundary is incomplete")
        lock_relative = PurePosixPath(lock.get("path", ""))
        if lock_relative.is_absolute() or ".." in lock_relative.parts or not lock_relative.parts:
            die("external-input lock escapes repository")
        lock_path = (repository / lock_relative.as_posix()).resolve()
        if not lock_path.is_file() or sha256(lock_path) != lock.get("sha256"):
            die("external-input lock is missing or hash differs")
        for item in document.get("files", []):
            relative = PurePosixPath(item.get("path", ""))
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                die("external-input path escapes its boundary")
            path = (root / relative.as_posix()).resolve()
            try: path.relative_to(root.resolve())
            except ValueError: die("external-input symlink escapes its boundary")
            if not path.is_file() or sha256(path) != item.get("sha256"):
                die(f"external-input hash mismatch: {boundary}/{relative}")
            paths.add(path); rows.append({"boundary":boundary, "lock":lock,
                                          "path":relative.as_posix(), "sha256":item["sha256"]})
    return paths, sorted(rows, key=lambda x:(x["boundary"],x["path"]))


def capture_records(arguments: argparse.Namespace) -> list[Path]:
    result = []
    for directory in getattr(arguments, "capture", []):
        result.extend(Path(directory).glob("compiles/*.json"))
    return sorted(result)


def reachable_capture_records(arguments: argparse.Namespace) -> list[Path]:
    records = capture_records(arguments)
    if not getattr(arguments, "map", []):
        return records
    cwd = Path(arguments.cwd).resolve()
    identities = map_identities(arguments.map, cwd, arguments)
    direct = {value for value in identities if "(" not in value}
    archive_members: dict[str, set[str]] = {}
    for value in identities:
        if "(" in value:
            archive, member = value.rsplit("(", 1)
            archive_members.setdefault(archive, set()).add(member[:-1])
    by_basename: dict[str, list[tuple[Path, str]]] = {}
    by_digest: dict[str, list[Path]] = {}
    selected = set()
    for record_path in records:
        record = json.loads(record_path.read_text(encoding="utf-8"))
        output = record.get("output")
        if not output: continue
        identity = normalized_build_path(recorded_path(output,replay_path(Path(record["cwd"]),arguments),arguments), cwd)
        if identity in direct: selected.add(record_path)
        by_basename.setdefault(Path(output).name, []).append((record_path, identity))
        if record.get("output_sha256"):
            by_digest.setdefault(record["output_sha256"], []).append(record_path)
    archive_records = []
    for directory in getattr(arguments, "capture", []):
        archive_records.extend(Path(directory).glob("archives/*.json"))
    archives_by_output: dict[Path, list[dict]] = {}
    for record_path in sorted(archive_records):
        record = json.loads(record_path.read_text())
        argv = record.get("argv", [])
        output = record.get("output") or (argv[1] if len(argv) > 1 else None)
        if not output or not record.get("output_sha256"):
            continue
        path = Path(output)
        absolute = recorded_path(path,replay_path(Path(record["cwd"]),arguments),arguments).resolve()
        archives_by_output.setdefault(absolute, []).append(record)
    for archive_identity, members in archive_members.items():
        archive_path = cwd / archive_identity
        if not archive_path.is_file(): continue
        archive_digest = sha256(archive_path)
        exact_matches = archives_by_output.get(archive_path.resolve(), [])
        candidate_groups = [
            records for records in archives_by_output.values()
            if any(record.get("output_sha256") == archive_digest for record in records)
        ]
        # NuttX copies most completed archives into staging before linking. An
        # exact captured producer wins; otherwise immutable byte identity must
        # identify exactly one captured archive-update sequence.
        matches = (exact_matches if any(
            record.get("output_sha256") == archive_digest for record in exact_matches
        ) else candidate_groups[0] if len(candidate_groups) == 1 else [])
        if not matches:
            external_roots = [Path(value.split("=",1)[1]).resolve()
                              for value in getattr(arguments,"external_root",[]) if "=" in value]
            if any(archive_path.resolve().is_relative_to(root) for root in external_roots):
                continue
            try: archive_path.resolve().relative_to(Path(getattr(arguments, "repository", ".")).resolve())
            except ValueError: continue  # separately declared immutable external runtime
            die(f"mapped archive has no unique recorded final producer: {archive_identity}")
        # NuttX Apps updates libapps.a incrementally from multiple directories.
        # A final-hash record proves this archive generation reached the mapped
        # bytes; every selected member must still have exactly one input across
        # all captured updates to that same absolute archive path.
        inputs=[]
        for record in matches:
            for value in record["argv"][2:]:
                if value.startswith("-"): continue
                path=Path(value)
                inputs.append(recorded_path(path,replay_path(Path(record["cwd"]),arguments),arguments).resolve())
        for member in members:
            producers=[p for p in inputs if p.name==member]
            if len(producers)!=1: die(f"archive member has no unique recorded input: {archive_identity}({member})")
            exact=normalized_build_path(producers[0],cwd)
            candidates=[path for path,identity in by_basename.get(member,[]) if identity==exact]
            # NuttX Apps disambiguates colliding object names by copying an
            # object to a suffixed name before archiving it. Exact identity is
            # preferred; otherwise require one compiler output with the same
            # immutable bytes as the captured archive input.
            if not candidates and producers[0].is_file():
                candidates = by_digest.get(sha256(producers[0]), [])
            if len(candidates)!=1: die(f"archive input has no unique compiler producer: {exact}")
            selected.add(candidates[0])
    return sorted(selected)


def linked_archive_producer_outputs(arguments: argparse.Namespace) -> set[Path]:
    """Return current captured archive outputs whose bytes feed a mapped archive."""
    cwd = Path(arguments.cwd).resolve()
    mapped = {
        value.rsplit("(", 1)[0] for value in map_identities(getattr(arguments, "map", []), cwd, arguments)
        if "(" in value
    }
    records = []
    for directory in getattr(arguments, "capture", []):
        for record_path in Path(directory).glob("archives/*.json"):
            record = json.loads(record_path.read_text())
            output = record.get("output")
            if output and record.get("output_sha256"):
                item = Path(output)
                records.append((record, recorded_path(item,replay_path(Path(record["cwd"]),arguments),arguments).resolve()))
    result = set()
    for identity in mapped:
        mapped_path = (cwd / identity).resolve()
        if not mapped_path.is_file():
            continue
        mapped_digest = sha256(mapped_path)
        candidates = [(record, output) for record, output in records
                      if record["output_sha256"] == mapped_digest]
        groups = {output for _, output in candidates}
        if len(groups) != 1:
            continue  # reachable_capture_records reports the authoritative error
        output = next(iter(groups))
        if not output.is_file() or sha256(output) != mapped_digest:
            die(f"captured linked archive producer is missing or stale: {identity}")
        result.add(output)
    return result


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
            relative = None
        try: resolved_relative = resolved.relative_to(base.resolve())
        except ValueError: resolved_relative = None
        if resolved_relative is not None:
            matches.append((len(base.parts), root, resolved_relative))
        elif relative is not None and lexical == resolved:
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


def file_license(path: Path, root: dict, relative: Path) -> tuple[str, str, dict | None]:
    expressions = set()
    for line in path.read_bytes().splitlines():
        match = SPDX_COMMENT.match(line)
        if match:
            expressions.add(match.group(1).decode("ascii", "replace").strip())
    key=(root["name"], relative.as_posix())
    selection=REVIEWED_BOUNDARY_LICENSE_SELECTIONS.get(key)
    if selection is not None:
        if expressions or sha256(path)!=selection["source_sha256"]:
            die(f"reviewed boundary-selected source drift: {root['name']}/{relative}")
        return validate_boundary_selection(path,Path(root["path"]),selection,f"{root['name']}/{relative}")
    anomaly = REVIEWED_SPDX_ANOMALIES.get(key)
    if anomaly is not None:
        raw = path.read_bytes()
        if (sha256(path) != anomaly["sha256"] or sorted(expressions) != sorted(anomaly["raw_tags"])
                or any(marker not in raw for marker in anomaly["markers"])):
            die(f"reviewed SPDX anomaly drift: {root['name']}/{relative}")
        return anomaly["concluded"], anomaly["concluded"], {
            "kind": "reviewed-multiple-spdx-anomaly", "raw_tags": anomaly["raw_tags"]
        }
    if len(expressions) > 1:
        die(f"multiple SPDX expressions in {path}: {sorted(expressions)}")
    declared, require_spdx = license_rule(root, relative)
    if require_spdx and not expressions:
        die(f"SPDX identifier required by override: {root['name']}/{relative}")
    expression = next(iter(expressions), declared)
    reviewed = REVIEWED_LICENSE_OVERRIDES.get((root["name"], relative.as_posix()))
    if expression == reviewed and declared == reviewed and require_spdx:
        notice = REVIEWED_LICENSE_NOTICES[(root["name"], relative.as_posix())]
        if notice not in path.read_bytes():
            die(f"reviewed license notice mismatch: {root['name']}/{relative}")
        expected_hash=REVIEWED_LICENSE_HASHES.get((root["name"],relative.as_posix()))
        if expected_hash and sha256(path)!=expected_hash:
            die(f"reviewed license file drift: {root['name']}/{relative}")
        boundary = REVIEWED_NESTED_BOUNDARIES.get((root["name"], relative.as_posix()))
        if boundary is not None:
            boundary_path = Path(root["path"]) / boundary["boundary_path"]
            if (boundary_path.is_symlink() or not boundary_path.is_file()
                    or not boundary_path.resolve().is_relative_to(Path(root["path"]).resolve())
                    or sha256(boundary_path) != boundary["boundary_sha256"]
                    or any(marker not in boundary_path.read_bytes() for marker in boundary["markers"])):
                die(f"reviewed nested license boundary drift: {root['name']}/{relative}")
            audit = {
                "kind": "reviewed-build-discovery-boundary",
                "boundary_path": boundary["boundary_path"],
                "boundary_sha256": boundary["boundary_sha256"],
                "future_consumed_files_require": boundary["future_consumed_files_require"],
            }
            if "note" in boundary: audit["note"]=boundary["note"]
            return expression, expression, audit
        return expression, expression, None
    if expression in ALLOWED_LICENSES:
        return expression, expression, None
    alternatives = expression.split(" OR ")
    if len(alternatives) > 1 and all(
        re.fullmatch(r"[A-Za-z0-9.-]+", item) for item in alternatives
    ):
        allowed = [item for item in alternatives if item in ALLOWED_LICENSES]
        concluded = declared if declared in allowed else allowed[0] if len(allowed) == 1 else None
        if concluded is not None:
            return concluded, expression, None
    check_license(expression, f"{root['name']}/{relative.as_posix()}")
    raise AssertionError("unreachable")


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
    external, _ = declared_external(arguments)
    generated, _ = declared_generated(arguments)
    consumed = consumed_paths(arguments)
    consumed -= vcs_administration(consumed, roots)[0]
    unmatched_generated = generated - consumed
    if unmatched_generated: die("generated declaration contains unconsumed files")
    for path in consumed - external - generated:
        root, relative, resolved = locate(path, roots)
        key = (root["name"], relative.as_posix())
        concluded_license, declared_license, license_audit = file_license(resolved, root, relative)
        entries[key] = {
            "source_root": root["name"],
            "path": relative.as_posix(),
            "sha256": sha256(resolved),
            "license": concluded_license,
            "declared_license": declared_license,
            "role": root["role"],
            "origin": origin_for(root, relative, resolved),
        }
        if license_audit is not None:
            entries[key]["license_audit"] = license_audit
    return [entries[key] for key in sorted(entries)]

def vcs_administration(consumed: set[Path], roots: list[dict]) -> tuple[set[Path],list[dict]]:
    excluded=set(); rows=[]
    for root in roots:
        path=Path(root["path"])/".git"
        if path.is_symlink(): continue
        kind="directory" if path.is_dir() else "file" if path.is_file() else None
        if kind is None: continue
        affected={item for item in consumed if item==path or (kind=="directory" and path in item.parents)}
        if not affected: continue
        excluded.update(affected); rows.append({"source_root":root["name"],"path":".git","kind":kind,"count":len(affected),"reason":"VCS administration; source identity is pinned separately"})
    return excluded,sorted(rows,key=lambda x:x["source_root"])


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
            "licenseInfoInFiles": [entry["declared_license"]],
            "copyrightText": (
                EXTRACTED_LICENSES[entry["license"]]["extractedText"]
                if entry["license"] in EXTRACTED_LICENSES else "NOASSERTION"
            ),
            **({"comment": json.dumps(entry["license_audit"], sort_keys=True)}
               if "license_audit" in entry else {}),
        })
    offset = len(files)
    for index, entry in enumerate(manifest.get("generated_inputs", []), offset + 1):
        files.append({
            "SPDXID": f"SPDXRef-File-{index}", "fileName": "generated/" + entry["path"],
            "checksums": [{"algorithm":"SHA256", "checksumValue":entry["sha256"]}],
            "licenseConcluded":"NOASSERTION", "licenseInfoInFiles":["NOASSERTION"],
            "copyrightText":"NOASSERTION", "comment":json.dumps(entry.get("license_boundary", {"generated_by":entry["generator_argv"]}), sort_keys=True),
        })
    document = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "brickwright-source-closure",
        "documentNamespace": "https://brickwright.example/spdx/source-closure/" + hashlib.sha256(serialized).hexdigest(),
        "creationInfo": {"created": "1970-01-01T00:00:00Z", "creators": ["Tool: source_closure.py"]},
        "files": files,
    }
    used_refs = sorted({entry["license"] for entry in manifest["files"]
                        if entry["license"] in EXTRACTED_LICENSES})
    if used_refs:
        document["hasExtractedLicensingInfos"] = [
            {"licenseId": license_id, **EXTRACTED_LICENSES[license_id]}
            for license_id in used_refs
        ]
    return document


def normalized_build_path(path: Path, cwd: Path) -> str:
    absolute = path if path.is_absolute() else cwd / path
    normalized = Path(os.path.abspath(absolute))
    try:
        return normalized.relative_to(cwd).as_posix()
    except ValueError:
        return normalized.as_posix()


def map_identities(map_paths: list[str], cwd: Path, arguments: argparse.Namespace | None = None) -> set[str]:
    identities = set()
    for map_path in map_paths:
        for token in MAP_OBJECT.findall(Path(map_path).read_text(encoding="utf-8", errors="replace")):
            archive = re.fullmatch(r"(.+\.a)\((.+\.o)\)", token)
            if archive:
                value=Path(archive.group(1)); value=replay_path(value,arguments) if arguments else value
                identities.add(normalized_build_path(value, cwd) + f"({archive.group(2)})")
            else:
                value=Path(token); value=replay_path(value,arguments) if arguments else value
                identities.add(normalized_build_path(value, cwd))
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
        target_id = normalized_build_path(recorded_path(target,cwd,arguments), cwd)
        sources = set()
        for path in paths:
            root, relative, _ = locate(recorded_path(path,cwd,arguments), roots)
            source_id = f"{root['name']}/{relative.as_posix()}"
            sources.add(source_id)
            all_sources.add(source_id)
        if target_id in dependencies:
            die(f"ambiguous duplicate depfile target: {target_id}")
        dependencies[target_id] = sources
    for record_path in reachable_capture_records(arguments):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record_cwd = replay_path(Path(record["cwd"]),arguments)
        target, paths = dep_record(Path(record["depfile"]))
        target_id = normalized_build_path(recorded_path(target,record_cwd,arguments), cwd)
        sources = set()
        for path in paths:
            absolute = recorded_path(path,record_cwd,arguments).resolve()
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
    map_objects = map_identities(arguments.map, cwd, arguments)
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
    repository = Path(arguments.repository).resolve().as_posix()
    replacements = [(repository, ".")]
    for value in getattr(arguments, "external_root", []):
        name, raw = value.split("=", 1)
        replacements.append((Path(raw).resolve().as_posix(), f"${{{name}}}"))
    replacements.sort(key=lambda item: len(item[0]), reverse=True)
    repository_roots = [Path(arguments.repository).resolve()]
    mapping = relocation(arguments)
    if mapping is not None:
        repository_roots.append(mapping[0])
    encoded_roots = [root.as_posix().replace("/", ".") for root in repository_roots]
    def public_identity(identity: str) -> str:
        for prefix, replacement in replacements:
            if identity == prefix or identity.startswith(prefix + "/"):
                identity = replacement + identity[len(prefix):]
                break
        # NuttX archive staging can flatten an absolute producer path into an
        # archive member name.  Preserve raw identities for map matching, then
        # redact only an exact encoded repository-root token at publication.
        for encoded in encoded_roots:
            identity = re.sub(re.escape(encoded) + r"(?=$|[./()])", ".repository", identity)
        if any(root.as_posix() in identity for root in repository_roots) or any(
            encoded in identity for encoded in encoded_roots
        ):
            die("published build identity contains repository path material")
        return identity
    public_objects = []
    public_object_identities = set()
    for row in rows:
        identity = public_identity(row["path"])
        if identity in public_object_identities:
            die("distinct object inputs collapse to one published identity")
        public_object_identities.add(identity)
        public_objects.append(dict(row, path=identity))
    public_map_objects = sorted({public_identity(identity) for identity in map_objects})
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    result = {
        "schema": 1,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "map_files": [{"path": Path(item).name, "sha256": sha256(Path(item))} for item in sorted(arguments.map)],
        "map_objects": public_map_objects,
        "objects": public_objects,
        "depfile_prerequisites": sorted(all_sources),
    }
    serialized = json.dumps(result, sort_keys=True)
    if any(root.as_posix() in serialized for root in repository_roots) or any(
        encoded in serialized for encoded in encoded_roots
    ):
        die("published link evidence contains repository path material")
    return result


def generate(arguments: argparse.Namespace) -> None:
    mapping=relocation(arguments)
    if not arguments.strace and not arguments.repository_trace:
        die("file-consumption evidence requires --strace or --repository-trace")
    if not arguments.depfile and not arguments.capture:
        die("compiler evidence requires --depfile or --capture")
    roots = load_roots(Path(arguments.roots))
    manifest = {
        "schema": 1,
        "allowed_licenses": sorted(ALLOWED_LICENSES),
        "source_roots": [public_root(root) for root in roots],
        "files": closure_entries(arguments, roots),
        "external_inputs": declared_external(arguments)[1],
        "generated_inputs": declared_generated(arguments)[1],
        "generated_symlinks": declared_symlinks(arguments)[1],
        "vcs_administration": vcs_administration(consumed_paths(arguments), roots)[1],
        "capture_relocation": {"enabled":mapping is not None,"source_identity":"captured-repository-root" if mapping else None},
    }
    link_evidence = None
    if arguments.evidence:
        link_evidence = make_link_evidence(arguments, manifest, roots)
    write_json(arguments.output, manifest)
    write_json(arguments.sbom, make_sbom(manifest))
    if link_evidence is not None:
        write_json(arguments.evidence, link_evidence)


def verify(arguments: argparse.Namespace) -> None:
    mapping=relocation(arguments)
    if not arguments.strace and not arguments.repository_trace:
        die("file-consumption evidence requires --strace or --repository-trace")
    if not arguments.depfile and not arguments.capture:
        die("compiler evidence requires --depfile or --capture")
    manifest = json.loads(Path(arguments.manifest).read_text(encoding="utf-8"))
    if manifest.get("capture_relocation")!={"enabled":mapping is not None,"source_identity":"captured-repository-root" if mapping else None}: die("capture relocation audit differs")
    roots = load_roots(Path(arguments.roots))
    if manifest.get("source_roots") != [public_root(root) for root in roots]:
        die("manifest source-root metadata differs from declarations")
    consumed_all=consumed_paths(arguments); vcs_excluded,vcs_rows=vcs_administration(consumed_all,roots)
    if manifest.get("vcs_administration")!=vcs_rows: die("VCS administration audit differs")
    actual_files = manifest.get("files", [])
    actual_keys = {(item.get("source_root"), item.get("path")) for item in actual_files}
    consumed_keys = set()
    external, external_rows = declared_external(arguments)
    generated, generated_rows = declared_generated(arguments)
    if (manifest.get("external_inputs") != external_rows
            or manifest.get("generated_inputs") != generated_rows
            or manifest.get("generated_symlinks") != declared_symlinks(arguments)[1]):
        die("declared generated/external inputs differ from manifest")
    for path in consumed_all - vcs_excluded - external - generated:
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
        for field in ("sha256", "license", "declared_license", "license_audit", "role", "origin"):
            if actual.get(field) != wanted.get(field):
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
        command.add_argument("--strace", action="append", default=[])
        command.add_argument(
            "--repository-trace", action="append", default=[],
            help="full build trace whose source inputs are scoped to --repository",
        )
        command.add_argument("--flow-trace", action="append", default=[])
        command.add_argument("--depfile", action="append", default=[])
        command.add_argument("--capture", action="append", default=[])
        command.add_argument("--generated", action="append", default=[])
        command.add_argument("--external", action="append", default=[])
        command.add_argument("--external-root", action="append", default=[])
        command.add_argument("--repository", default=".")
        command.add_argument("--captured-repository-root")

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
    verify_parser.add_argument("--map", action="append", default=[])
    return parser


def main() -> None:
    arguments = make_parser().parse_args()
    if arguments.command == "generate":
        generate(arguments)
    else:
        verify(arguments)


if __name__ == "__main__":
    main()
