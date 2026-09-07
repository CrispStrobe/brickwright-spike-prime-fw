#!/usr/bin/env python3
"""Validate the immutable Zephyr Bluetooth host selection."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "third_party" / "zephyr-host" / "manifest.json"
ALLOWED = {"MIT", "Apache-2.0"}


def main() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    upstream = data["upstream"]
    assert upstream["tag"] == "v4.4.1"
    assert upstream["commit"] == "1f6485eca25431b5ff27ce9a754218c9e559bbbb"
    assert upstream["license"] in ALLOWED
    patches = data.get("local_patches", [])
    assert patches
    for patch in patches:
        assert patch["license"] in ALLOWED
        patch_path = ROOT / "third_party" / "zephyr-host" / patch["path"]
        assert patch_path.is_file()
        assert b"SPDX-License-Identifier: Apache-2.0" in patch_path.read_bytes()
    crypto = data["crypto_provider"]
    assert crypto["license"] in ALLOWED
    assert crypto["status"] == "pinned-not-yet-imported"
    assert crypto["version"] == "3.6.2"
    assert crypto["commit"] == "107ea89daaefb9867ea9121002fbbdf926780e98"
    assert crypto["archive_sha256"] == (
        "a3c959773bc5d5b22353bc605e96d92fae2eac486dcaf46990412b84a1a0fb5f"
    )
    assert crypto["framework_commit"] == "df3307f2b4fe512def60886024f7be8fd1523ccd"
    assert crypto["framework_archive_sha256"] == (
        "641fbb913f3ea6748cecbacb30af698d96de585f33d627f12b3ef9275b79726a"
    )

    paths = []
    for group in data["source_groups"].values():
        paths.extend(group)
    paths.extend(data["required_public_headers"])
    paths.extend(data["required_internal_headers"])
    assert len(paths) == len(set(paths)), "manifest contains duplicate paths"
    assert all(not Path(path).is_absolute() and ".." not in Path(path).parts for path in paths)
    assert "drivers/bluetooth/hci/h4.c" in paths
    assert "subsys/bluetooth/host/classic/rfcomm.c" in paths
    assert "subsys/bluetooth/host/classic/sdp.c" in paths
    assert "subsys/bluetooth/host/gatt.c" in paths
    assert "subsys/bluetooth/host/smp.c" in paths
    assert not any("btstack" in path.lower() or "cc256" in path.lower() for path in paths)

    upstream = ROOT / "third_party" / "zephyr-host" / "upstream"
    lock_path = ROOT / "third_party" / "zephyr-host" / "files.sha256"
    if upstream.exists() or lock_path.exists():
        expected_paths = sorted(paths + ["LICENSE"])
        actual_paths = sorted(
            str(path.relative_to(upstream)) for path in upstream.rglob("*") if path.is_file()
        )
        assert actual_paths == expected_paths, "vendored Zephyr files differ from manifest"
        expected_lock = []
        for relative in expected_paths:
            content = (upstream / relative).read_bytes()
            if relative != "LICENSE":
                assert b"SPDX-License-Identifier: Apache-2.0" in content
            expected_lock.append(
                f"{__import__('hashlib').sha256(content).hexdigest()}  upstream/{relative}"
            )
        assert lock_path.read_text(encoding="utf-8") == "\n".join(expected_lock) + "\n"


if __name__ == "__main__":
    main()
