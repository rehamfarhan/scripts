
from pathlib import Path
import py_compile
import textwrap

script = r'''#!/usr/bin/env python3
"""
modfetch - a verbose Modrinth CLI for Minecraft mods.

Examples:
    modfetch sodium
    modfetch install sodium lithium "Entity Culling"
    modfetch -r 26.1.2 sodium
    modfetch install --mod-version 0.6.0 sodium
    modfetch url https://modrinth.com/mod/sodium
    modfetch list
    modfetch delete sodium
    modfetch update -r 26.1.2
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen


API_BASE = "https://api.modrinth.com/v2"
DEFAULT_MODS_DIR = Path.home() / ".minecraft" / "mods"
LOADER = "fabric"
USER_AGENT = "modfetch/0.1.0 (+https://modrinth.com/)"

# ANSI styling. --no-color disables it.
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"


class ModfetchError(RuntimeError):
    """Expected user-facing application error."""


def styled(text: str, *styles: str, enabled: bool = True) -> str:
    if not enabled:
        return text
    return "".join(styles) + text + RESET


def info(message: str, color: str = CYAN, *, color_enabled: bool = True) -> None:
    print(styled("==> ", BOLD, color, enabled=color_enabled) + message)


def success(message: str, *, color_enabled: bool = True) -> None:
    print(styled("✓ ", BOLD, GREEN, enabled=color_enabled) + message)


def warn(message: str, *, color_enabled: bool = True) -> None:
    print(styled("⚠ ", BOLD, YELLOW, enabled=color_enabled) + message)


def error(message: str, *, color_enabled: bool = True) -> None:
    print(styled("✗ ", BOLD, RED, enabled=color_enabled) + message, file=sys.stderr)


def human_size(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB")
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{value} B"


def http_json(
    path: str,
    *,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> Any:
    url = f"{API_BASE}{path}"
    if params:
        encoded = urlencode(
            {key: json.dumps(value, separators=(",", ":")) if isinstance(value, list) else value
             for key, value in params.items()}
        )
        url += "?" + encoded

    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(url, data=data, headers=headers, method=method)

    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read()
    except HTTPError as exc:
        try:
            payload = exc.read().decode("utf-8", errors="replace")
            details = json.loads(payload)
            detail = details.get("description") or details.get("error") or payload
        except Exception:
            detail = str(exc)
        raise ModfetchError(f"Modrinth API returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise ModfetchError(f"Could not reach Modrinth API: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ModfetchError("The Modrinth API request timed out.") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ModfetchError("Modrinth returned invalid JSON.") from exc


def download_file(url: str, destination: Path, *, expected_sha1: str | None = None) -> None:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    destination.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_name = tempfile.mkstemp(prefix=".modfetch-", dir=str(destination.parent))
    os.close(fd)
    temp_path = Path(temp_name)

    try:
        with urlopen(request, timeout=60) as response, temp_path.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                handle.write(chunk)

        if expected_sha1:
            actual = sha1_file(temp_path)
            if actual.lower() != expected_sha1.lower():
                raise ModfetchError(
                    f"SHA-1 verification failed for {destination.name}: "
                    f"expected {expected_sha1}, got {actual}"
                )

        temp_path.replace(destination)
    except HTTPError as exc:
        raise ModfetchError(
            f"Download failed with HTTP {exc.code} for {url}"
        ) from exc
    except URLError as exc:
        raise ModfetchError(f"Download failed: {exc.reason}") from exc
    finally:
        temp_path.unlink(missing_ok=True)


def sha1_file(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_modrinth_project(query: str, *, color_enabled: bool) -> dict[str, Any]:
    # A direct project slug/ID is accepted without a search.
    if re.fullmatch(r"[A-Za-z0-9]{8}", query):
        try:
            return http_json(f"/project/{quote(query, safe='')}")
        except ModfetchError:
            pass

    results = http_json(
        "/search",
        params={
            "query": query,
            "limit": 20,
            "index": "relevance",
        },
    ).get("hits", [])

    mods = [item for item in results if item.get("project_type") == "mod"]
    if not mods:
        raise ModfetchError(f"No Modrinth mods found for '{query}'.")

    # Show a numbered menu instead of silently picking a fuzzy match.
    print()
    info(f"Search results for {query!r}:", MAGENTA, color_enabled=color_enabled)
    for index, item in enumerate(mods[:10], 1):
        title = item.get("title") or item.get("slug") or item.get("project_id")
        slug = item.get("slug") or ""
        description = (item.get("description") or "").strip().replace("\n", " ")
        if len(description) > 84:
            description = description[:81] + "..."
        print(f"  {index:>2}) {BOLD if color_enabled else ''}{title}{RESET if color_enabled else ''}")
        print(f"      {DIM if color_enabled else ''}{slug}{RESET if color_enabled else ''}")
        if description:
            print(f"      {description}")

    if len(mods) == 1:
        return mods[0]

    while True:
        answer = input("\nSelect a project [1-{}] (q to cancel): ".format(min(10, len(mods)))).strip()
        if answer.lower() in {"q", "quit", "cancel"}:
            raise ModfetchError("Selection cancelled.")
        if answer.isdigit() and 1 <= int(answer) <= min(10, len(mods)):
            return mods[int(answer) - 1]
        warn("Please enter one of the displayed numbers or q.", color_enabled=color_enabled)


def parse_modrinth_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {
        "modrinth.com",
        "www.modrinth.com",
    }:
        raise ModfetchError("That is not a supported Modrinth URL.")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "mod":
        return parts[1]
    if len(parts) >= 2 and parts[0] == "project":
        return parts[1]
    raise ModfetchError(
        "Expected a Modrinth mod page such as https://modrinth.com/mod/sodium"
    )


def parse_modrinth_url_or_query(value: str, *, color_enabled: bool) -> dict[str, Any]:
    if value.startswith(("https://", "http://")):
        slug = parse_modrinth_url(value)
        return http_json(f"/project/{quote(slug, safe='')}")
    return load_modrinth_project(value, color_enabled=color_enabled)


def version_files(version: dict[str, Any]) -> list[dict[str, Any]]:
    files = version.get("files") or []
    if not files:
        raise ModfetchError(
            f"Modrinth version {version.get('version_number', '?')} has no downloadable files."
        )
    primaries = [item for item in files if item.get("primary")]
    return primaries[:1] or files[:1]


def primary_file(version: dict[str, Any]) -> dict[str, Any]:
    return version_files(version)[0]


def resolve_version(
    project: dict[str, Any],
    *,
    minecraft_version: str | None,
    mod_version: str | None,
    color_enabled: bool,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "loaders": [LOADER],
        "include_changelog": False,
    }
    if minecraft_version:
        params["game_versions"] = [minecraft_version]

    versions = http_json(
        f"/project/{quote(project['id'], safe='')}/version",
        params=params,
    )

    versions = [
        version for version in versions
        if version.get("version_type") == "release"
        and LOADER in version.get("loaders", [])
    ]

    if minecraft_version:
        versions = [
            version for version in versions
            if minecraft_version in version.get("game_versions", [])
        ]

    if mod_version:
        versions = [
            version for version in versions
            if version.get("version_number") == mod_version
        ]

    if not versions:
        target = minecraft_version or "any supported Minecraft version"
        if mod_version:
            raise ModfetchError(
                f"No release of {project.get('title', project.get('slug', 'this mod'))} "
                f"matches mod version {mod_version!r} for {target} with Fabric."
            )
        raise ModfetchError(
            f"No release of {project.get('title', project.get('slug', 'this mod'))} "
            f"supports {target} with Fabric."
        )

    # Modrinth normally returns newest first, but sorting explicitly keeps behavior stable.
    versions.sort(key=lambda item: item.get("date_published", ""), reverse=True)

    if color_enabled:
        info(
            f"Resolved {project.get('title', project.get('slug', 'mod'))} "
            f"→ {versions[0].get('version_number')} "
            f"(Minecraft {', '.join(versions[0].get('game_versions', [])[:3])})",
            color=CYAN,
            color_enabled=color_enabled,
        )

    return versions[0]


def local_sha1s(directory: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    if not directory.exists():
        return result
    for path in directory.iterdir():
        if path.is_file() and path.suffix.lower() == ".jar":
            try:
                result[sha1_file(path)] = path
            except OSError:
                pass
    return result


def dependency_project_and_version(
    dependency: dict[str, Any],
    *,
    minecraft_version: str | None,
    color_enabled: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    project_id = dependency.get("project_id")
    version_id = dependency.get("version_id")

    if version_id:
        version = http_json(f"/version/{quote(version_id, safe='')}")
        project = http_json(f"/project/{quote(version['project_id'], safe='')}")
        return project, version

    if not project_id:
        raise ModfetchError(
            "A required dependency has no project/version information; "
            "Modrinth did not provide enough metadata to install it automatically."
        )

    project = http_json(f"/project/{quote(project_id, safe='')}")
    version = resolve_version(
        project,
        minecraft_version=minecraft_version,
        mod_version=None,
        color_enabled=color_enabled,
    )
    return project, version


def dependency_is_present(
    version: dict[str, Any],
    *,
    directory: Path,
    sha1_index: dict[str, Path],
) -> Path | None:
    files = version_files(version)
    for file_info in files:
        filename = file_info.get("filename")
        if filename:
            candidate = directory / filename
            if candidate.is_file():
                return candidate
        expected_hash = (file_info.get("hashes") or {}).get("sha1")
        if expected_hash and expected_hash in sha1_index:
            return sha1_index[expected_hash]
    return None


def install_version(
    project: dict[str, Any],
    version: dict[str, Any],
    *,
    directory: Path,
    force: bool,
    yes: bool,
    minecraft_version: str | None,
    color_enabled: bool,
    install_stack: set[str],
) -> None:
    project_id = project["id"]
    if project_id in install_stack:
        raise ModfetchError(
            f"Dependency cycle detected while installing {project.get('title', project_id)}."
        )

    install_stack.add(project_id)
    try:
        # Resolve required dependencies first.
        dependencies = [
            dep for dep in version.get("dependencies", [])
            if dep.get("dependency_type") == "required"
        ]

        if dependencies:
            print()
            info(
                f"{project.get('title', project_id)} has {len(dependencies)} required "
                f"dependency/dependencies.",
                MAGENTA,
                color_enabled=color_enabled,
            )
            sha1_index = local_sha1s(directory)

            for dependency in dependencies:
                dep_project, dep_version = dependency_project_and_version(
                    dependency,
                    minecraft_version=minecraft_version,
                    color_enabled=color_enabled,
                )
                dep_name = dep_project.get("title") or dep_project.get("slug") or dep_project["id"]
                present = dependency_is_present(
                    dep_version,
                    directory=directory,
                    sha1_index=sha1_index,
                )
                if present:
                    success(
                        f"Dependency already present: {dep_name} "
                        f"→ {present.name}",
                        color_enabled=color_enabled,
                    )
                    continue

                if not yes:
                    answer = input(
                        f"  Install required dependency {dep_name} "
                        f"({dep_version.get('version_number')})? [Y/n]: "
                    ).strip().lower()
                    if answer not in {"", "y", "yes"}:
                        raise ModfetchError(
                            f"Required dependency {dep_name} was declined; "
                            "installation cannot continue."
                        )

                install_version(
                    dep_project,
                    dep_version,
                    directory=directory,
                    force=force,
                    yes=yes,
                    minecraft_version=minecraft_version,
                    color_enabled=color_enabled,
                    install_stack=install_stack,
                )
                sha1_index = local_sha1s(directory)

        file_info = primary_file(version)
        filename = file_info["filename"]
        destination = directory / filename
        expected_sha1 = (file_info.get("hashes") or {}).get("sha1")

        if destination.is_file() and not force:
            if expected_sha1:
                try:
                    if sha1_file(destination).lower() == expected_sha1.lower():
                        success(f"Already present: {filename}", color_enabled=color_enabled)
                        return
                except OSError:
                    pass
            else:
                success(f"Already present: {filename}", color_enabled=color_enabled)
                return

        directory.mkdir(parents=True, exist_ok=True)

        info(
            f"Downloading {filename} ({human_size(int(file_info.get('size', 0)))})…",
            color_enabled=color_enabled,
        )
        download_file(
            file_info["url"],
            destination,
            expected_sha1=expected_sha1,
        )
        success(
            f"Installed {project.get('title', project_id)} "
            f"{version.get('version_number')} → {destination}",
            color_enabled=color_enabled,
        )
    finally:
        install_stack.discard(project_id)


def cmd_install(args: argparse.Namespace) -> int:
    directory = args.directory
    directory.mkdir(parents=True, exist_ok=True)

    if args.mod_version and not args.mods:
        raise ModfetchError("--mod-version requires at least one mod.")

    for mod_query in args.mods:
        print()
        info(f"Looking up {mod_query!r}…", color_enabled=args.color)
        project = parse_modrinth_url_or_query(mod_query, color_enabled=args.color)
        version = resolve_version(
            project,
            minecraft_version=args.mc_version,
            mod_version=args.mod_version,
            color_enabled=args.color,
        )
        install_version(
            project,
            version,
            directory=directory,
            force=args.force,
            yes=args.yes,
            minecraft_version=args.mc_version,
            color_enabled=args.color,
            install_stack=set(),
        )

    print()
    success(f"Finished. Mods directory: {directory}", color_enabled=args.color)
    return 0


def cmd_url(args: argparse.Namespace) -> int:
    # Kept separate from install so the CLI makes the source explicit.
    args.mods = args.urls
    return cmd_install(args)


def cmd_list(args: argparse.Namespace) -> int:
    directory = args.directory
    if not directory.exists():
        print(f"{directory} does not exist.")
        return 0

    mods = sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() == ".jar"
    )

    print()
    info(f"Installed mods in {directory}", MAGENTA, color_enabled=args.color)
    if not mods:
        print("  (no .jar files found)")
        return 0

    for index, path in enumerate(mods, 1):
        try:
            size = human_size(path.stat().st_size)
        except OSError:
            size = "?"
        print(f"  {index:>3}. {path.name}  {DIM if args.color else ''}({size}){RESET if args.color else ''}")

    print()
    print(f"  Total: {len(mods)} mod JAR(s)")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    directory = args.directory
    mods = sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() == ".jar"
    ) if directory.exists() else []

    if not mods:
        raise ModfetchError(f"No .jar files found in {directory}.")

    query = " ".join(args.query).strip()
    names = [path.name for path in mods]

    scored: list[tuple[float, Path]] = []
    query_lower = query.lower()
    for path in mods:
        name = path.stem.lower()
        ratio = difflib.SequenceMatcher(None, query_lower, name).ratio()
        if query_lower in name:
            ratio += 1.0
        scored.append((ratio, path))

    scored.sort(key=lambda item: item[0], reverse=True)
    matches = [path for _, path in scored[:10]]

    print()
    info(f"Delete search: {query!r}", MAGENTA, color_enabled=args.color)
    for index, path in enumerate(matches, 1):
        print(f"  {index:>2}) {path.name}")

    while True:
        answer = input(
            "\nSelect a file [1-{}] (q to cancel): ".format(len(matches))
        ).strip()
        if answer.lower() in {"q", "quit", "cancel"}:
            raise ModfetchError("Deletion cancelled.")
        if answer.isdigit() and 1 <= int(answer) <= len(matches):
            selected = matches[int(answer) - 1]
            break
        warn("Please enter a valid number or q.", color_enabled=args.color)

    confirm = input(f"Delete {selected.name}? [y/N]: ").strip().lower()
    if confirm not in {"y", "yes"}:
        print("Nothing deleted.")
        return 0

    try:
        selected.unlink()
    except OSError as exc:
        raise ModfetchError(f"Could not delete {selected}: {exc}") from exc

    success(f"Deleted {selected.name}", color_enabled=args.color)
    return 0


def latest_minecraft_release(*, color_enabled: bool) -> str:
    versions = http_json("/tag/game_version")
    releases = [
        version for version in versions
        if version.get("version_type") == "release"
    ]
    if not releases:
        raise ModfetchError("Could not determine the latest Minecraft release from Modrinth.")
    releases.sort(key=lambda item: item.get("date", ""), reverse=True)
    latest = releases[0]["version"]
    info(
        f"No Minecraft version supplied; using latest release {latest}.",
        color_enabled=color_enabled,
    )
    return latest


def cmd_update(args: argparse.Namespace) -> int:
    directory = args.directory
    if not directory.exists():
        raise ModfetchError(f"Mods directory does not exist: {directory}")

    jars = sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() == ".jar"
    )
    if not jars:
        print(f"No .jar files found in {directory}.")
        return 0

    target_mc = args.mc_version or latest_minecraft_release(color_enabled=args.color)
    info(
        f"Updating Fabric mods in {directory} for Minecraft {target_mc}…",
        MAGENTA,
        color_enabled=args.color,
    )

    hashes: list[str] = []
    hash_to_path: dict[str, Path] = {}
    for path in jars:
        try:
            digest = sha1_file(path)
        except OSError as exc:
            warn(f"Could not hash {path.name}: {exc}", color_enabled=args.color)
            continue
        hashes.append(digest)
        hash_to_path[digest] = path

    if not hashes:
        return 0

    body = {
        "hashes": hashes,
        "algorithm": "sha1",
        "loaders": [LOADER],
        "game_versions": [target_mc],
        "version_types": ["release"],
    }

    try:
        updates = http_json("/version_files/update", method="POST", body=body)
    except ModfetchError as exc:
        raise ModfetchError(f"Bulk update lookup failed: {exc}") from exc

    changed = 0
    skipped = 0

    for digest, old_path in hash_to_path.items():
        version = updates.get(digest)
        if not version:
            warn(
                f"{old_path.name}: no Fabric release found for Minecraft {target_mc}; skipped.",
                color_enabled=args.color,
            )
            skipped += 1
            continue

        file_info = primary_file(version)
        new_hash = (file_info.get("hashes") or {}).get("sha1")
        new_path = directory / file_info["filename"]

        if new_hash and new_hash.lower() == digest.lower() and not args.force:
            success(
                f"{old_path.name}: already current ({version.get('version_number')}).",
                color_enabled=args.color,
            )
            skipped += 1
            continue

        if new_path != old_path and new_path.exists() and not args.force:
            warn(
                f"{old_path.name}: target file {new_path.name} already exists; "
                "use --force to replace it.",
                color_enabled=args.color,
            )
            skipped += 1
            continue

        info(
            f"{old_path.name} → {new_path.name} ({version.get('version_number')})",
            color_enabled=args.color,
        )
        download_file(
            file_info["url"],
            new_path,
            expected_sha1=new_hash,
        )

        try:
            if old_path != new_path and old_path.exists():
                old_path.unlink()
        except OSError as exc:
            warn(
                f"Downloaded new version, but could not remove {old_path.name}: {exc}",
                color_enabled=args.color,
            )
        success(f"Updated to {version.get('version_number')}.", color_enabled=args.color)
        changed += 1

    print()
    success(
        f"Update complete: {changed} changed, {skipped} skipped.",
        color_enabled=args.color,
    )
    return 0


def add_common_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-d",
        "--directory",
        type=Path,
        default=DEFAULT_MODS_DIR,
        help=f"mods directory (default: {DEFAULT_MODS_DIR})",
    )
    parser.add_argument(
        "-r",
        "--mc-version",
        dest="mc_version",
        help="Minecraft game version to target (e.g. 26.1.2)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-download/replace files that are already present",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="automatically accept required dependency installation",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="modfetch",
        description="A verbose Modrinth mod installer for Fabric.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  modfetch sodium\n"
            "  modfetch install sodium lithium \"Entity Culling\"\n"
            "  modfetch -r 26.1.2 sodium\n"
            "  modfetch install --mod-version 0.6.0 sodium\n"
            "  modfetch url https://modrinth.com/mod/sodium\n"
            "  modfetch list\n"
            "  modfetch delete sodium\n"
            "  modfetch update -r 26.1.2\n"
        ),
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="disable ANSI colors",
    )
    subparsers = parser.add_subparsers(dest="command")

    install = subparsers.add_parser("install", help="search, resolve, and install mods")
    add_common_flags(install)
    install.add_argument(
        "--mod-version",
        help="select an exact Modrinth mod version (separate from Minecraft -r)",
    )
    install.add_argument("mods", nargs="+", help="mod names, slugs, or Modrinth URLs")
    install.set_defaults(func=cmd_install)

    url = subparsers.add_parser("url", help="install from one or more Modrinth project URLs")
    add_common_flags(url)
    url.add_argument("urls", nargs="+", help="Modrinth project URLs")
    url.set_defaults(func=cmd_url)

    listing = subparsers.add_parser("list", help="list installed .jar files")
    add_common_flags(listing)
    listing.set_defaults(func=cmd_list)

    delete = subparsers.add_parser("delete", help="fuzzy-search and delete a mod")
    add_common_flags(delete)
    delete.add_argument("query", nargs="+", help="fuzzy filename/project search")
    delete.set_defaults(func=cmd_delete)

    update = subparsers.add_parser("update", help="update all recognized Modrinth Fabric mods")
    add_common_flags(update)
    update.set_defaults(func=cmd_update)

    return parser


def normalize_argv(argv: list[str]) -> list[str]:
    """
    Permit the original ergonomic form:

        modfetch sodium
        modfetch -r 26.1.2 sodium

    by treating a non-command first positional argument as `install`.
    """
    commands = {"install", "url", "list", "delete", "update", "-h", "--help"}
    for index, value in enumerate(argv):
        if value in commands:
            return argv
        if not value.startswith("-"):
            return argv[:index] + ["install"] + argv[index:]
    return argv


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    raw = list(sys.argv[1:] if argv is None else argv)
    raw = normalize_argv(raw)

    args = parser.parse_args(raw)
    args.color = not args.no_color and sys.stdout.isatty()

    if not args.command:
        parser.print_help()
        return 0

    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        error("Interrupted.", color_enabled=args.color)
        return 130
    except ModfetchError as exc:
        error(str(exc), color_enabled=args.color)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
'''

path = Path("/mnt/data/modfetch")
path.write_text(script, encoding="utf-8")
path.chmod(0o755)

# Syntax validation and a couple of basic offline CLI checks.
py_compile.compile(str(path), doraise=True)

import subprocess, textwrap
help_result = subprocess.run(
    [str(path), "--help"],
    text=True,
    capture_output=True,
    timeout=10,
)
list_result = subprocess.run(
    [str(path), "list", "--no-color", "-d", "/tmp/modfetch-empty-test"],
    text=True,
    capture_output=True,
    timeout=10,
)

print(f"Created: {path}")
print(f"Executable: yes")
print("Syntax check: PASS")
print(f"--help smoke test: {'PASS' if help_result.returncode == 0 else 'FAIL'}")
print(f"list smoke test: {'PASS' if list_result.returncode == 0 else 'FAIL'}")
