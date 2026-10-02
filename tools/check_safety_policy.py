#!/usr/bin/env python3
"""Keep the pre-hardware-validation repository simulation-only."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    safety = (ROOT / "SAFETY.md").read_text(encoding="utf-8").lower()
    required = ("simulation-only", "do not flash", "real silicon")
    for phrase in required:
        if phrase not in readme and phrase not in safety:
            raise SystemExit(f"safety-policy: missing warning phrase: {phrase}")

    workflows = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    )
    forbidden = ("actions/upload-artifact", "softprops/action-gh-release")
    for marker in forbidden:
        if marker in workflows:
            raise SystemExit(
                f"safety-policy: firmware publication action is forbidden: {marker}"
            )

    documentation = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
    for path in documentation:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "dfu-util" in line and " -D " in line:
                relative = path.relative_to(ROOT)
                raise SystemExit(
                    f"safety-policy: physical flashing command at {relative}:{number}"
                )

    print("safety-policy: simulation-only warning and no-artifact CI enforced")


if __name__ == "__main__":
    main()
