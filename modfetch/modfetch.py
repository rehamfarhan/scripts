#!/usr/bin/env python3
"""modfetch: a paru-style Modrinth CLI for Minecraft mods, modpacks, and resource packs.

Operation flow mirrors pacman/paru:
    modfetch                    update all installed mods  (same as -Syu)
    modfetch <target>           interactive search + install (paru <foo>)
    modfetch -S <target>        install mods/modpacks/resource packs (auto-detected)
    modfetch -Ss <query>        search Modrinth
    modfetch -Si <target>       show project info
    modfetch -Syu               update all mods (any number of -y accepted)
    modfetch -Qu                list available updates
    modfetch -Q                 list installed mods
    modfetch -Qs <query>        list installed mods matching query
    modfetch -R <target>        remove a mod (fuzzy match)
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

API = "https://api.modrinth.com/v2"
VERSION = "0.3.0"
UA = f"modfetch/{VERSION}"

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "modfetch"
CONFIG_FILE = CONFIG_DIR / "config.toml"
DEFAULT_MC_DIR = Path.home() / ".minecraft"
DEFAULT_MODS_DIR = DEFAULT_MC_DIR / "mods"
DEFAULT_RESOURCEPACKS_DIR = DEFAULT_MC_DIR / "resourcepacks"
DEFAULT_SHADERPACKS_DIR = DEFAULT_MC_DIR / "shaderpacks"
DEFAULT_CONFIG_DIR = DEFAULT_MC_DIR / "config"
DEFAULT_LOADER = "fabric"
SUPPORTED_LOADERS = ("fabric", "forge", "neoforge", "quilt")
VERSION_TYPES = ("release", "beta", "alpha")
PROJECT_TYPES = {"mod", "modpack", "resourcepack", "datapack", "shader", "plugin"}
LOADER_KEYS = ("fabric-loader", "quilt-loader", "forge", "neoforge")

# Options that consume a following value token (used by normalize_argv).
VALUE_OPTS = {"-g", "-r", "-l", "-d", "--game-version", "--mc-version",
              "--minecraft-version", "--loader", "--directory",
              "--confdir", "--shaderpacks-dir", "--mod-version"}
VALUED_SHORTS = frozenset("dglr")

# Operations (paru-style).
OP_SYNC = "sync"
OP_QUERY = "query"
OP_REMOVE = "remove"

# Legacy subcommands: word -> (operation, action, type preference).
LEGACY_SUBCOMMANDS = {
    "install":      (OP_SYNC,   "install",    None),
    "pack":         (OP_SYNC,   "install",    "modpack"),
    "resourcepack": (OP_SYNC,   "install",    "resourcepack"),
    "shaderpack":   (OP_SYNC,   "install",    "shaderpack"),
    "url":          (OP_SYNC,   "install",    "url"),
    "list":         (OP_QUERY,  "list",       None),
    "delete":       (OP_REMOVE, "remove",     None),
    "update":       (OP_SYNC,   "update",     None),
    "search":       (OP_SYNC,   "search",     None),
    "info":         (OP_SYNC,   "info",       None),
    "config":       ("config",  "config",     None),
}

CONFIG_TEMPLATE = """# modfetch configuration
# CLI arguments override these values for a single invocation.

mods_dir = \"~/.minecraft/mods\"
resourcepacks_dir = \"~/.minecraft/resourcepacks\"
# Directory for mod config files (from modpacks).
# config_dir = \"~/.minecraft/config\"
loader = \"fabric\"
# Set to \"latest\" to use the newest Minecraft release supported by the mod.
minecraft_version = \"latest\"
"""

# Terminal styling — disabled automatically when output is not a TTY,
# when --no-color is given, or when NO_COLOR is set.
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"


class ModfetchError(RuntimeError):
    """A recoverable top-level failure (bad config, API error, …)."""


class ModfetchCancelled(ModfetchError):
    """The user declined or interrupted a particular operation (not Ctrl-C)."""


def c(text, *styles, enabled=True):
    return "".join(styles) + text + RESET if enabled and styles else text


def celebrate(prefix, styles, msg, color, stream=None):
    text = msg
    if color:
        text = "".join(styles) + prefix + RESET + msg
    else:
        text = prefix + msg
    print(text, file=stream or sys.stdout)


def info(msg, color, quiet=False):
    if quiet:
        return
    celebrate("==> ", (BOLD, CYAN), msg, color)


def ok(msg, color, quiet=False):
    if quiet:
        return
    celebrate("✓ ", (BOLD, GREEN), msg, color)


def warn(msg, color, quiet=False):
    if quiet:
        return
    celebrate("⚠ ", (BOLD, YELLOW), msg, color)


def fail(msg, color):
    celebrate("✗ ", (BOLD, RED), msg, color, stream=sys.stderr)


def expand_path(value):
    return Path(os.path.expandvars(os.path.expanduser(str(value))).strip())


def default_config():
    return {
        "mods_dir": str(DEFAULT_MODS_DIR),
        "resourcepacks_dir": str(DEFAULT_RESOURCEPACKS_DIR),
        "shaderpacks_dir": str(DEFAULT_SHADERPACKS_DIR),
        "config_dir": str(DEFAULT_CONFIG_DIR),
        "loader": DEFAULT_LOADER,
        "minecraft_version": "latest",
    }


def validate_config(config):
    result = default_config()
    for key in result:
        if key in config:
            value = config[key]
            if not isinstance(value, str) or not value.strip():
                raise ModfetchError(f"Invalid config value for {key!r}: expected a non-empty string.")
            result[key] = value.strip()
    if result["loader"] not in SUPPORTED_LOADERS:
        raise ModfetchError(
            f"Unsupported loader {result['loader']!r} in {CONFIG_FILE}. "
            f"Choose one of: {', '.join(sorted(SUPPORTED_LOADERS))}."
        )
    return result


def load_config():
    if not CONFIG_FILE.exists():
        return default_config()
    try:
        with CONFIG_FILE.open("rb") as handle:
            raw = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ModfetchError(f"Invalid TOML in {CONFIG_FILE}: {exc}") from exc
    except OSError as exc:
        raise ModfetchError(f"Could not read {CONFIG_FILE}: {exc}") from exc
    return validate_config(raw)


def ensure_config():
    if CONFIG_FILE.exists():
        return
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(CONFIG_TEMPLATE, encoding="utf-8")
    except OSError as exc:
        raise ModfetchError(f"Could not create {CONFIG_FILE}: {exc}") from exc


def write_config(config):
    validate_config(config)
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            "# modfetch configuration\n"
            "# CLI arguments override these values for a single invocation.\n\n"
            f"mods_dir = {json.dumps(config['mods_dir'])}\n"
            f"resourcepacks_dir = {json.dumps(config['resourcepacks_dir'])}\n"
            f"shaderpacks_dir = {json.dumps(config['shaderpacks_dir'])}\n"
            f"config_dir = {json.dumps(config['config_dir'])}\n"
            f"loader = {json.dumps(config['loader'])}\n"
            f"minecraft_version = {json.dumps(config['minecraft_version'])}\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise ModfetchError(f"Could not write {CONFIG_FILE}: {exc}") from exc


def effective_config(args):
    """Layer config file defaults under CLI overrides.

    Args are parsed with default=SUPPRESS for the directory/loader/game-version
    options, so `hasattr` reliably tells us which ones the user supplied.
    """
    config = load_config()
    if hasattr(args, "directory"):
        directory = str(args.directory)
        config["mods_dir"] = directory
        config["resourcepacks_dir"] = directory
        config["shaderpacks_dir"] = directory
    if hasattr(args, "shaderpacks_dir"):
        config["shaderpacks_dir"] = str(args.shaderpacks_dir)
    if args.config_dir is not None:
        config["config_dir"] = str(args.config_dir)
    if hasattr(args, "loader"):
        config["loader"] = args.loader
    if hasattr(args, "mc_version"):
        config["minecraft_version"] = args.mc_version
    return validate_config(config)


def print_config(config, color):
    print()
    info(f"Configuration: {CONFIG_FILE}", color)
    print(f"  mods_dir           = {config['mods_dir']}")
    print(f"  resourcepacks_dir  = {config['resourcepacks_dir']}")
    print(f"  shaderpacks_dir    = {config['shaderpacks_dir']}")
    print(f"  config_dir         = {config['config_dir']}")
    print(f"  loader             = {config['loader']}")
    print(f"  minecraft_version  = {config['minecraft_version']}")


def human(n):
    x = float(n)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if x < 1024 or unit == "GiB":
            return f"{x:.1f} {unit}" if unit != "B" else f"{int(x)} B"
        x /= 1024


def count(n):
    return f"{int(n):,}"


def api(path, method="GET", params=None, body=None):
    url = API + path
    if params:
        query = {k: json.dumps(v, separators=(",", ":")) if isinstance(v, (list, bool)) else v
                 for k, v in params.items()}
        url += "?" + urlencode(query)
    headers = {"Accept": "application/json", "User-Agent": UA}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=25) as response:
            raw = response.read()
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode(errors="replace"))
            detail = payload.get("description") or payload.get("error") or str(payload)
        except Exception:
            detail = str(exc)
        raise ModfetchError(f"Modrinth API returned HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise ModfetchError(f"Could not reach Modrinth API: {getattr(exc, 'reason', exc)}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ModfetchError("Modrinth returned invalid JSON.") from exc


def sha1(path):
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url, dest, expected=None):
    request = Request(url, headers={"User-Agent": UA})
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".modfetch-", dir=dest.parent)
    os.close(fd)
    tmp = Path(tmp)
    try:
        with urlopen(request, timeout=90) as response, tmp.open("wb") as handle:
            while chunk := response.read(256 * 1024):
                handle.write(chunk)
        if expected and sha1(tmp).lower() != expected.lower():
            raise ModfetchError(f"SHA-1 verification failed for {dest.name}.")
        tmp.replace(dest)
    except HTTPError as exc:
        raise ModfetchError(f"Download failed with HTTP {exc.code}.") from exc
    except (URLError, TimeoutError) as exc:
        raise ModfetchError(f"Download failed: {getattr(exc, 'reason', exc)}") from exc
    finally:
        tmp.unlink(missing_ok=True)


def prompt(message, default=True):
    """Ask a yes/no question. Falls back to `default` on EOF/non-interactive input."""
    choices = " [Y/n]: " if default else " [y/N]: "
    try:
        answer = input(message + choices).strip().lower()
    except EOFError:
        return default
    if default:
        return answer in {"", "y", "yes"}
    return answer in {"y", "yes"}


def select_number(message, maximum, color):
    """Ask the user to pick a number from 1..maximum; q cancels."""
    while True:
        try:
            answer = input(f"{message} (q to cancel): ").strip().lower()
        except EOFError:
            raise ModfetchCancelled("Selection cancelled.")
        if answer in {"q", "quit", "cancel"}:
            raise ModfetchCancelled("Selection cancelled.")
        if answer.isdigit() and 1 <= int(answer) <= maximum:
            return int(answer)
        warn(f"Enter one of the numbers 1-{maximum}, or q.", color)


# ---------------------------------------------------------------------------
# Project / version resolution
# ---------------------------------------------------------------------------

def parse_url(value):
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {"modrinth.com", "www.modrinth.com"}:
        raise ModfetchError("Unsupported URL. Use a Modrinth project page URL.")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] in {"mod", "modpack", "resourcepack", "datapack", "shader", "plugin", "project"}:
        return parts[1]
    raise ModfetchError("Expected a Modrinth project URL.")


def normalize_project(project):
    """Normalize search hits (project_id) and project objects (id) to a common schema."""
    if "id" not in project and project.get("project_id"):
        project = dict(project)
        project["id"] = project["project_id"]
    if "id" not in project:
        raise ModfetchError("Modrinth returned a project without a project ID.")
    return project


def project_from(value, color, prompt_ok, quiet=False):
    if value.startswith(("http://", "https://")):
        return normalize_project(api(f"/project/{quote(parse_url(value), safe='')}"))
    return normalize_project(search_project(value, color, prompt_ok, quiet))


def search_project(query, color, prompt_ok, quiet=False):
    hits = api("/search", params={"query": query, "limit": 20, "index": "relevance"}).get("hits", [])
    projects = [h for h in hits if h.get("project_type") in PROJECT_TYPES]
    if not projects:
        raise ModfetchError(f"No supported Modrinth projects found for {query!r}.")

    normalized = query.strip().casefold()
    first = projects[0]
    if (first.get("slug") or "").casefold() == normalized or (first.get("title") or "").casefold() == normalized:
        return first
    if len(projects) == 1:
        return projects[0]
    if not prompt_ok:
        # Can't prompt (piped, --noconfirm, or EOF): take the relevance leader.
        warn(f"No exact match for {query!r}; selecting top result "
             f"{first.get('title') or first.get('slug') or first.get('project_id')}.", color)
        return first

    print()
    info(f"Search results for {query!r}:", color, quiet)
    for i, item in enumerate(projects[:10], 1):
        title = item.get("title") or item.get("slug") or item.get("project_id")
        kind = item.get("project_type", "project")
        description = (item.get("description") or "").replace("\n", " ").strip()
        description = description if len(description) <= 84 else description[:81] + "..."
        print(f"  {i:>2}) {c(title, BOLD, enabled=color)} {c(f'[{kind}]', DIM, enabled=color)}")
        print(f"      {c(item.get('slug', ''), DIM, enabled=color)}")
        if description:
            print(f"      {description}")
    choice = select_number(f"Select a project [1-{min(10, len(projects))}]", min(10, len(projects)), color)
    return projects[choice - 1]


def resolve_kind(project, type_pref):
    """Decide how to install a resolved project.

    type_pref is set by the legacy subcommands (pack/resourcepack/shaderpack/url);
    otherwise the project's own type decides.
    """
    if type_pref == "url" or type_pref is None:
        raw = project.get("project_type", "mod")
        if raw == "shader":
            return "shaderpack"
        return raw
    return type_pref


def primary(version):
    files = version.get("files") or []
    if not files:
        raise ModfetchError(f"Modrinth version {version.get('version_number', '?')} has no files.")
    return next((f for f in files if f.get("primary")), files[0])


def select_version(versions, *, mc=None, loader=None, mod_version=None):
    """Best version for the given filters, preferring stable channels and newer dates."""
    for version_type in VERSION_TYPES:
        matches = [v for v in versions
                   if v.get("version_type") == version_type
                   and (loader is None or loader in v.get("loaders", []))
                   and (not mc or mc in v.get("game_versions", []))
                   and (not mod_version or v.get("version_number") == mod_version)]
        if matches:
            matches.sort(key=lambda v: v.get("date_published", ""), reverse=True)
            return matches[0]
    return None


def version_channel_text(version):
    version_type = version.get("version_type", "release")
    return "" if version_type == "release" else f" ({version_type})"


def resolve(project, mc=None, mod_version=None, color=False, loader=DEFAULT_LOADER, quiet=False):
    params = {"loaders": [loader], "include_changelog": False}
    if mc:
        params["game_versions"] = [mc]
    versions = api(f"/project/{quote(project['id'], safe='')}/version", params=params)
    version = select_version(versions, mc=mc, loader=loader, mod_version=mod_version)
    if not version:
        target = mc or "any supported Minecraft version"
        extra = f" and version {mod_version!r}" if mod_version else ""
        raise ModfetchError(f"No {loader} version of {project.get('title', project['id'])} matches {target}{extra}.")
    info(f"Resolved {project.get('title', project['id'])} → {version['version_number']}"
         f"{version_channel_text(version)} for {loader} / Minecraft "
         f"{', '.join(version.get('game_versions', [])[:4])}", color, quiet)
    return version


def resolve_resourcepack(project, mc=None, mod_version=None, color=False, quiet=False):
    params = {"loaders": ["minecraft"], "include_changelog": False}
    if mc:
        params["game_versions"] = [mc]
    versions = api(f"/project/{quote(project['id'], safe='')}/version", params=params)
    version = select_version(versions, mc=mc, loader="minecraft", mod_version=mod_version)
    if not version:
        target = mc or "any supported Minecraft version"
        extra = f" and resource pack version {mod_version!r}" if mod_version else ""
        raise ModfetchError(f"No Minecraft resource pack version of {project.get('title', project['id'])} matches {target}{extra}.")
    info(f"Resolved resource pack {project.get('title', project['id'])} → {version['version_number']}"
         f"{version_channel_text(version)} / Minecraft {', '.join(version.get('game_versions', [])[:4])}",
         color, quiet)
    return version


def resolve_pack(project, mc=None, color=False, quiet=False):
    params = {"include_changelog": False}
    if mc:
        params["game_versions"] = [mc]
    versions = api(f"/project/{quote(project['id'], safe='')}/version", params=params)
    version = select_version(versions, mc=mc)
    if not version:
        target = mc or "any supported Minecraft version"
        raise ModfetchError(f"No modpack version of {project.get('title', project['id'])} matches {target}.")
    info(f"Resolved modpack {project.get('title', project['id'])} → {version['version_number']}"
         f"{version_channel_text(version)} / Minecraft {', '.join(version.get('game_versions', [])[:4])}",
         color, quiet)
    return version


def latest_release(color):
    versions = api("/tag/game_version")
    releases = [v for v in versions if v.get("version_type") == "release"]
    if not releases:
        raise ModfetchError("Could not determine the latest Minecraft release.")
    releases.sort(key=lambda x: x.get("date", ""), reverse=True)
    latest = releases[0]["version"]
    info(f"No Minecraft version supplied; using latest release {latest}.", color)
    return latest


# ---------------------------------------------------------------------------
# Local install / remove infrastructure
# ---------------------------------------------------------------------------

def local_index(directory):
    """Map sha1-digest -> jar path for every .jar under directory."""
    result = {}
    if not directory.exists():
        return result
    for path in directory.iterdir():
        if path.is_file() and path.suffix.lower() == ".jar":
            try:
                result[sha1(path)] = path
            except OSError:
                pass
    return result


def dep_version(dep, mc, loader):
    if dep.get("version_id"):
        version = api(f"/version/{quote(dep['version_id'], safe='')}")
        return api(f"/project/{quote(version['project_id'], safe='')}"), version
    if not dep.get("project_id"):
        raise ModfetchError("A required dependency lacks project/version metadata.")
    project = api(f"/project/{quote(dep['project_id'], safe='')}")
    return project, resolve(project, mc, None, False, loader)


def install_version(project, version, directory, force, noconfirm, mc, color, loader, stack=None):
    stack = set() if stack is None else stack
    pid = project["id"]
    if pid in stack:
        raise ModfetchError(f"Dependency cycle detected at {project.get('title', pid)}.")
    stack.add(pid)
    try:
        deps = [d for d in version.get("dependencies", [])
                if d.get("dependency_type") == "required" and (d.get("project_id") or d.get("version_id"))]
        if deps:
            print()
            info(f"{project.get('title', pid)} requires {len(deps)} dependency/dependencies.", color)
        index = local_index(directory)
        for dep in deps:
            dep_proj, dep_ver = dep_version(dep, mc, loader)
            file = primary(dep_ver)
            expected = (file.get("hashes") or {}).get("sha1")
            name = dep_proj.get("title") or dep_proj.get("slug") or dep_proj["id"]
            present = index.get(expected) if expected else (directory / file["filename"])
            if present and present.is_file():
                ok(f"Dependency already present: {name} → {present.name}", color)
                continue
            if not noconfirm:
                if not prompt(f"Install required dependency {name} ({dep_ver['version_number']})?", default=True):
                    raise ModfetchCancelled(f"Required dependency {name} was declined.")
            install_version(dep_proj, dep_ver, directory, force, noconfirm, mc, color, loader, stack)
            index = local_index(directory)  # dep may have dropped new files

        file = primary(version)
        dest = directory / file["filename"]
        expected = (file.get("hashes") or {}).get("sha1")
        if not force:
            index = local_index(directory)
            if dest.is_file():
                if not expected or sha1(dest).lower() == expected.lower():
                    ok(f"Already present: {dest.name}", color)
                    return
            elif expected and index.get(expected):
                ok(f"Already present as {index[expected].name}", color)
                return
        directory.mkdir(parents=True, exist_ok=True)
        info(f"Downloading {file['filename']} ({human(int(file.get('size', 0)))})…", color)
        download(file["url"], dest, expected)
        ok(f"Installed {project.get('title', pid)} {version['version_number']} → {dest}", color)
    finally:
        stack.remove(pid)


def install_resourcepack(project, version, directory, force, color, quiet=False):
    file = primary(version)
    dest = directory / file["filename"]
    expected = (file.get("hashes") or {}).get("sha1")
    if dest.is_file() and not force:
        if not expected or sha1(dest).lower() == expected.lower():
            ok(f"Already present: {dest.name}", color, quiet)
            return
    directory.mkdir(parents=True, exist_ok=True)
    info(f"Downloading resource pack {file['filename']} ({human(int(file.get('size', 0)))})…", color, quiet)
    download(file["url"], dest, expected)
    ok(f"Installed {project.get('title', project['id'])} {version['version_number']} → {dest}", color, quiet)


def resolve_shaderpack(project, mc=None, mod_version=None, color=False, quiet=False):
    params = {"include_changelog": False}
    if mc:
        params["game_versions"] = [mc]
    versions = api(f"/project/{quote(project['id'], safe='')}/version", params=params)
    version = select_version(versions, mc=mc, loader=None, mod_version=mod_version)
    if not version:
        target = mc or "any supported Minecraft version"
        extra = f" and version {mod_version!r}" if mod_version else ""
        raise ModfetchError(f"No shader pack version of {project.get('title', project['id'])} matches {target}{extra}.")
    info(f"Resolved shader pack {project.get('title', project['id'])} → {version['version_number']}"
         f"{version_channel_text(version)} / Minecraft {', '.join(version.get('game_versions', [])[:4])}",
         color, quiet)
    return version


def install_shaderpack(project, version, directory, force, color, quiet=False):
    file = primary(version)
    dest = directory / file["filename"]
    expected = (file.get("hashes") or {}).get("sha1")
    if dest.is_file() and not force:
        if not expected or sha1(dest).lower() == expected.lower():
            ok(f"Already present: {dest.name}", color, quiet)
            return
    directory.mkdir(parents=True, exist_ok=True)
    info(f"Downloading shader pack {file['filename']} ({human(int(file.get('size', 0)))})…", color, quiet)
    download(file["url"], dest, expected)
    ok(f"Installed {project.get('title', project['id'])} {version['version_number']} → {dest}", color, quiet)


# ---------------------------------------------------------------------------
# Modpack installation
# ---------------------------------------------------------------------------

def verify_sha512(path, expected):
    if not expected:
        return True
    digest = hashlib.sha512()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower() == expected.lower()


def download_pack_file(urls, dest, sha1_expected, sha512_expected):
    if not urls:
        raise ModfetchError(f"Modpack file has no download URL: {dest}")
    last_error = None
    for url in urls:
        if not url.startswith("https://"):
            continue
        try:
            request = Request(url, headers={"User-Agent": UA})
            dest.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".modfetch-", dir=dest.parent)
            os.close(fd)
            tmp = Path(tmp)
            try:
                with urlopen(request, timeout=90) as response, tmp.open("wb") as handle:
                    while chunk := response.read(256 * 1024):
                        handle.write(chunk)
                if sha1_expected and sha1(tmp).lower() != sha1_expected.lower():
                    raise ModfetchError(f"SHA-1 verification failed for {dest.name}.")
                if sha512_expected and not verify_sha512(tmp, sha512_expected):
                    raise ModfetchError(f"SHA-512 verification failed for {dest.name}.")
                tmp.replace(dest)
                return
            finally:
                tmp.unlink(missing_ok=True)
        except (HTTPError, URLError, TimeoutError, ModfetchError) as exc:
            last_error = exc
    raise ModfetchError(f"Could not download {dest.name}: {last_error or 'no HTTPS download URL available'}")


def install_pack(project, version, mods_dir, resourcepacks_dir, shaderpacks_dir, config_dir,
                  force, color, quiet, noconfirm):
    pack = primary(version)
    if not pack.get("url"):
        raise ModfetchError("Modpack version has no downloadable .mrpack file.")
    mods_dir = mods_dir.resolve()
    resourcepacks_dir = resourcepacks_dir.resolve()
    config_dir = config_dir.resolve()
    mods_dir.mkdir(parents=True, exist_ok=True)
    resourcepacks_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    info(f"Downloading {pack['filename']} ({human(int(pack.get('size', 0)))})…", color, quiet)
    fd, tmp = tempfile.mkstemp(prefix=".modfetch-pack-", suffix=".mrpack")
    os.close(fd)
    archive = Path(tmp)
    try:
        download(pack["url"], archive, (pack.get("hashes") or {}).get("sha1"))
        try:
            with zipfile.ZipFile(archive) as zf:
                try:
                    manifest = json.loads(zf.read("modrinth.index.json"))
                except KeyError as exc:
                    raise ModfetchError("Invalid modpack: missing modrinth.index.json.") from exc
                if manifest.get("formatVersion") != 1 or manifest.get("game") != "minecraft":
                    raise ModfetchError("Unsupported modpack format; expected Modrinth formatVersion 1 for Minecraft.")

                deps = manifest.get("dependencies") or {}
                mc = deps.get("minecraft")
                loader = next((k for k in LOADER_KEYS if k in deps), None)
                name = manifest.get("name") or project.get("title") or "modpack"
                summary = [f"Minecraft {mc}"] if mc else ["Minecraft (any version)"]
                if loader:
                    summary.append(f"{loader} {deps[loader]}")
                info(f"Installing {name}", color, quiet)
                info("  requisites: " + ", ".join(summary), color, quiet)
                info(f"  mods → {mods_dir}", color, quiet)
                info(f"  resourcepacks → {resourcepacks_dir}", color, quiet)
                info(f"  shaderpacks → {shaderpacks_dir}", color, quiet)
                info(f"  configs → {config_dir}", color, quiet)

                files = manifest.get("files") or []
                seen = set()
                items = []
                for item in files:
                    path = (item.get("path") or "").replace("\\", "/")
                    if not path:
                        warn("Skipping pack file without a path.", color, quiet)
                        continue
                    if path in seen:
                        warn(f"Skipping duplicate pack file: {path}", color, quiet)
                        continue
                    seen.add(path)
                    items.append(item)

                installed = skipped = optional = failed = 0
                for item in items:
                    env = item.get("env") or {}
                    if env.get("client", "required") == "unsupported":
                        skipped += 1
                        continue

                    path = item["path"]
                    hashes = item.get("hashes") or {}

                    # Route to the correct directory based on path prefix.
                    if path.startswith("mods/"):
                        dest = (mods_dir / path[len("mods/"):]).resolve()
                        root = mods_dir.resolve()
                        label = Path(path[len("mods/"):])
                    elif path.startswith("resourcepacks/"):
                        dest = (resourcepacks_dir / path[len("resourcepacks/"):]).resolve()
                        root = resourcepacks_dir.resolve()
                        label = Path(path[len("resourcepacks/"):])
                    elif path.startswith("shaderpacks/"):
                        dest = (shaderpacks_dir / path[len("shaderpacks/"):]).resolve()
                        root = shaderpacks_dir.resolve()
                        label = Path(path[len("shaderpacks/"):])
                    elif path.startswith("config/"):
                        dest = (config_dir / path[len("config/"):]).resolve()
                        root = config_dir.resolve()
                        label = Path(path[len("config/"):])
                    else:
                        skipped += 1
                        continue

                    # Path traversal guard.
                    if dest != root and root not in dest.parents:
                        warn(f"Skipping unsafe path: {path}", color, quiet)
                        skipped += 1
                        continue

                    if dest.is_file() and not force and hashes.get("sha1"):
                        try:
                            if sha1(dest).lower() == hashes["sha1"].lower():
                                ok(f"Already present: {label}", color, quiet)
                                installed += 1
                                continue
                        except OSError:
                            pass

                    try:
                        download_pack_file(item.get("downloads") or [], dest,
                                           hashes.get("sha1"), hashes.get("sha512"))
                    except ModfetchError as exc:
                        failed += 1
                        fail(f"{label}: {exc}", color)
                        continue

                    installed += 1
                    if env.get("client") == "optional":
                        optional += 1
                        warn(f"Installed optional file: {label}", color, quiet)
                    else:
                        ok(f"Installed: {label}", color, quiet)

                if any(n.startswith("server-overrides/") for n in zf.namelist()):
                    warn("Skipping server-overrides for client installation.", color, quiet)

                # Always apply config overrides (pack author's intended settings).
                for folder in ("overrides", "client-overrides"):
                    prefix = folder + "/"
                    members = [n for n in zf.namelist() if n.startswith(prefix) and not n.endswith("/")]
                    copied = 0
                    for member in members:
                        relative = member[len(prefix):]
                        # Route config overrides to config_dir
                        if relative.startswith("config/"):
                            inner = relative[len("config/"):]
                            # Flatten modpack_defaults/ to root config_dir
                            if inner.startswith("modpack_defaults/"):
                                inner = inner[len("modpack_defaults/"):]
                                # Strip nested config/ inside modpack_defaults too
                                if inner.startswith("config/"):
                                    inner = inner[len("config/"):]
                            dest = (config_dir / inner).resolve()
                            root = config_dir.resolve()
                        else:
                            # Skip non-config overrides (mods, resourcepacks already handled)
                            continue
                        # Path traversal guard
                        if dest != root and root not in dest.parents:
                            warn(f"Skipping unsafe path: {relative}", color, quiet)
                            continue
                        # Always overwrite configs — pack author's settings beat local ones.
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(member) as src, dest.open("wb") as out:
                            shutil.copyfileobj(src, out)
                        copied += 1
                    if copied:
                        info(f"Applied {folder}: {copied} config(s)", color, quiet)

                if failed:
                    raise ModfetchError(f"{name}: {failed} file(s) could not be downloaded.")

                ok(f"Modpack installed: {name} ({version['version_number']})", color, quiet)
                detail = f"{installed} installed/present, {optional} optional, {skipped} skipped"
                info(f"Files: {detail}", color, quiet)
        except zipfile.BadZipFile as exc:
            raise ModfetchError("Downloaded modpack is not a valid ZIP archive.") from exc
    finally:
        archive.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Top-level command implementations
# ---------------------------------------------------------------------------

def cmd_install(a, targets, type_pref, color):
    if not targets:
        raise ModfetchError("No targets given. Use 'modfetch -S <name>' or 'modfetch <name>'.")
    completed = failed = cancelled = 0
    for item in targets:
        print()
        info(f"Resolving {item!r}…", color, a.quiet)
        try:
            project = project_from(item, color, a.can_prompt, a.quiet)
            kind = resolve_kind(project, type_pref)
            if kind == "modpack":
                version = resolve_pack(project, a.mc_version, color, a.quiet)
                install_pack(project, version, a.mods_dir, a.resourcepacks_dir,
                             a.shaderpacks_dir, a.config_dir, a.force, color, a.quiet, a.noconfirm)
            elif kind == "resourcepack":
                version = resolve_resourcepack(project, a.mc_version, a.mod_version, color, a.quiet)
                install_resourcepack(project, version, a.resourcepacks_dir, a.force, color, a.quiet)
            elif kind == "shaderpack":
                version = resolve_shaderpack(project, a.mc_version, a.mod_version, color, a.quiet)
                install_shaderpack(project, version, a.shaderpacks_dir, a.force, color, a.quiet)
            else:
                version = resolve(project, a.mc_version, a.mod_version, color, a.loader, a.quiet)
                install_version(project, version, a.mods_dir, a.force, a.noconfirm,
                                a.mc_version, color, a.loader)
            completed += 1
        except ModfetchCancelled as exc:
            cancelled += 1
            warn(f"Skipped {item!r}: {exc}", color)
        except ModfetchError as exc:
            failed += 1
            fail(f"{item!r}: {exc}", color)
        except KeyboardInterrupt:
            raise
    print()
    if failed or cancelled:
        warn(f"Finished: {completed} completed, {failed} failed, {cancelled} cancelled/skipped.", color)
        return 1 if failed else 0
    ok(f"Finished: {completed} item(s) completed.", color, a.quiet)
    return 0


def cmd_search(a, queries, color):
    if not queries:
        raise ModfetchError("No search query given. Use 'modfetch -Ss <query>'.")
    for index, query in enumerate(queries):
        if index:
            print()
        hits = api("/search", params={"query": query, "limit": 10, "index": "relevance"}).get("hits", [])
        projects = [h for h in hits if h.get("project_type") in PROJECT_TYPES]
        if not projects:
            warn(f"No supported Modrinth projects found for {query!r}.", color)
            continue
        print()
        info(f"Search results for {query!r}:", color, a.quiet)
        for i, item in enumerate(projects, 1):
            title = item.get("title") or item.get("slug") or item.get("project_id")
            kind = item.get("project_type", "project")
            description = (item.get("description") or "").replace("\n", " ").strip()
            description = description if len(description) <= 84 else description[:81] + "..."
            print(f"  {i:>2}) {c(title, BOLD, enabled=color)} {c(f'[{kind}]', DIM, enabled=color)}")
            print(f"      {c(item.get('slug', ''), DIM, enabled=color)}"
                  f"  {count(item.get('downloads', 0))} downloads · {count(item.get('follows', 0))} follows")
            if description:
                print(f"      {description}")
    return 0


def cmd_info(a, targets, color):
    if not targets:
        raise ModfetchError("No target given for info. Use 'modfetch -Si <name>'.")
    for target in targets:
        project = project_from(target, color, a.can_prompt, a.quiet)
        title = project.get("title") or project.get("slug") or project["id"]
        print()
        info(f"{title} {c(f'({project.get("slug", "?")})', DIM, enabled=color)}", color, a.quiet)
        print(f"  Project ID: {project.get('id')}")
        print(f"  Type: {project.get('project_type', '?')}"
              f"  |  Downloads: {count(project.get('downloads', 0))}"
              f"  |  Follows: {count(project.get('follows', 0))}")
        raw_license = project.get("license")
        license_id = raw_license.get("id") if isinstance(raw_license, dict) else raw_license
        categories = ", ".join(project.get("categories") or [])
        if license_id or categories:
            print(f"  License: {license_id or '?'}" + (f"  |  Categories: {categories}" if categories else ""))
        updated = (project.get("date_modified") or project.get("date_created") or "")
        if updated:
            print(f"  Last updated: {updated.split('T')[0]}")
        description = (project.get("description") or "").strip()
        if description:
            print()
            print(f"  {description}")
        try:
            members = api(f"/project/{quote(project['slug'] or project['id'], safe='')}/members")
            names = [f"{m.get('user', {}).get('username', '?')} ({m.get('role', '?')})" for m in members[:4]]
            if names:
                print()
                print(f"  Team: {', '.join(names)}")
        except ModfetchError:
            pass

        try:
            versions = api(f"/project/{quote(project['id'], safe='')}/version",
                           params={"include_changelog": False})
            versions = [v for v in versions if v.get("version_type") in VERSION_TYPES]
            if a.mc_version:
                versions = [v for v in versions if a.mc_version in v.get("game_versions", [])]
            versions.sort(key=lambda v: v.get("date_published", ""), reverse=True)
            if versions:
                print()
                info("Recent versions:", color, a.quiet)
                for v in versions[:5]:
                    channel = version_channel_text(v)
                    game = ", ".join(v.get("game_versions", [])[:3]) or "any"
                    loaders = ", ".join(v.get("loaders", [])[:3]) or "?"
                    date = (v.get("date_published") or "").split("T")[0]
                    print(f"  {c(v['version_number'] + channel, BOLD, enabled=color)}  MC: {game}  [{loaders}]  {date}")
        except ModfetchError as exc:
            warn(f"Could not fetch versions: {exc}", color)
    return 0


def resolve_updates(a, directory, color):
    """Return (installed_pairs, updates) where updates maps sha1 -> newest version."""
    jars = sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() == ".jar") \
        if directory.exists() else []
    if not jars:
        return [], {}
    target = a.mc_version or latest_release(color)
    info(f"Querying Modrinth for {a.loader} mods compatible with Minecraft {target}…", color, a.quiet)
    pairs, hashes = [], []
    for path in jars:
        try:
            digest = sha1(path)
            pairs.append((digest, path))
            hashes.append(digest)
        except OSError as exc:
            warn(f"Could not hash {path.name}: {exc}", color)
    if not hashes:
        return [], {}
    body = {"hashes": hashes, "algorithm": "sha1",
            "loaders": [a.loader], "game_versions": [target]}
    found = api("/version_files/update", method="POST", body=body)
    pending = set(hashes)
    updates = {}
    for digest, version in found.items():
        if digest in pending:
            updates[digest] = version
            pending.discard(digest)
    return pairs, updates


def resolve_missing_deps_from_versions(versions, directory, mc, loader, color, quiet, noconfirm, force, stack=None):
    """Check updated versions for missing required dependencies and install them."""
    if stack is None:
        stack = set()
    index = local_index(directory)
    target = mc or latest_release(color)
    installed = 0
    seen_projects = set()

    # Build set of project IDs already installed (by hashing jars → querying Modrinth).
    installed_projects = set()
    hashes = list(index.keys())
    if hashes:
        body = {"hashes": hashes, "algorithm": "sha1",
                "loaders": [loader], "game_versions": [target]}
        found = api("/version_files/update", method="POST", body=body)
        for ver in found.values():
            pid = ver.get("project_id")
            if pid:
                installed_projects.add(pid)

    for version in versions:
        pid = version.get("project_id")
        if not pid or pid in seen_projects:
            continue
        seen_projects.add(pid)

        deps = [d for d in version.get("dependencies", [])
                if d.get("dependency_type") == "required"
                and (d.get("project_id") or d.get("version_id"))]

        for dep in deps:
            dep_pid = dep.get("project_id")
            dep_vid = dep.get("version_id")
            if dep_pid and dep_pid in stack:
                continue
            if dep_vid and dep_vid in stack:
                continue

            # Skip if the dependency project is already installed (any version).
            if dep_pid and dep_pid in installed_projects:
                continue

            try:
                dep_proj, dep_ver = dep_version(dep, target, loader)
            except ModfetchError as exc:
                warn(f"Could not resolve dependency: {exc}", color)
                continue

            dep_file = primary(dep_ver)
            dep_hash = (dep_file.get("hashes") or {}).get("sha1")
            dep_name = dep_proj.get("title") or dep_proj.get("slug") or dep_proj["id"]

            # Check if already present by hash or filename.
            if dep_hash and dep_hash.lower() in {h.lower() for h in index}:
                continue
            if (directory / dep_file["filename"]).is_file():
                continue

            # Missing dependency — install it.
            info(f"Installing missing dependency: {dep_name} ({dep_ver['version_number']})", color, quiet)
            install_version(dep_proj, dep_ver, directory, force, noconfirm, target, color, loader, stack)
            index = local_index(directory)  # refresh after install
            installed_projects.add(dep_proj["id"])  # track newly installed
            installed += 1

    return installed


def cmd_update(a, dry_run, color):
    directory = a.mods_dir
    pairs, updates = resolve_updates(a, directory, color)
    if not pairs:
        info(f"No .jar mods found in {directory}.", color, a.quiet)
        return 0
    changed = skipped = 0
    # Collect updated versions for dependency resolution.
    updated_versions = []
    for digest, old in pairs:
        version = updates.get(digest)
        if not version:
            warn(f"{old.name}: no {a.loader} version for Minecraft {a.mc_version or 'latest'}; skipped.", color)
            skipped += 1
            continue
        file = primary(version)
        new = directory / file["filename"]
        new_hash = (file.get("hashes") or {}).get("sha1")
        channel = version_channel_text(version)

        if new_hash and new_hash.lower() == digest.lower() and not a.force:
            ok(f"{old.name}: already current ({version['version_number']}{channel}).", color, a.quiet)
            skipped += 1
            continue
        if not new_hash and not a.force:
            warn(f"{old.name}: newest version {version['version_number']} has no SHA-1; "
                 f"use --force to install it without verification.", color)
            skipped += 1
            continue
        if new != old and new.exists() and not a.force:
            warn(f"{old.name}: target {new.name} already exists; use --force to replace it.", color)
            skipped += 1
            continue

        info(f"{old.name} → {new.name} ({version['version_number']}{channel})", color, a.quiet)
        if dry_run:
            changed += 1
            continue
        download(file["url"], new, new_hash)
        if new != old:
            try:
                old.unlink()
            except OSError as exc:
                warn(f"Updated, but could not remove {old.name}: {exc}", color)
        ok(f"Updated to {version['version_number']}{channel}.", color, a.quiet)
        updated_versions.append(version)
        changed += 1
    print()
    if dry_run:
        ok(f"{changed} update(s) available, {skipped} up to date/skipped.", color, a.quiet)
    else:
        ok(f"Update complete: {changed} changed, {skipped} skipped.", color, a.quiet)

    # -Syyu: resolve missing dependencies after updating.
    if a.refresh >= 2 and not dry_run and updated_versions:
        print()
        info("Resolving dependencies…", color, a.quiet)
        deps_installed = resolve_missing_deps_from_versions(
            updated_versions, directory, a.mc_version, a.loader, color, a.quiet, a.noconfirm, a.force)
        if deps_installed:
            ok(f"Installed {deps_installed} missing dependency/dependencies.", color, a.quiet)
        else:
            ok("All dependencies satisfied.", color, a.quiet)
    return 0


def fuzzy_matches(query, files):
    """Rank installed jars against a query; return best matches (top 10) or []."""
    query = query.strip().lower()
    if not query:
        return []
    tokens = query.split()
    scored = []
    for path in files:
        name = path.stem.lower()
        score = difflib.SequenceMatcher(None, query, name).ratio()
        if query in name:
            score += 1.0
        score += 0.5 * sum(1 for token in tokens if token in name)
        scored.append((score, path))
    if not scored:
        return []
    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0][0]
    if best < 0.4:
        return []
    return [path for score, path in scored if score >= best - 0.25][:10]


def cmd_remove(a, targets, color):
    directory = a.mods_dir
    jars = sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() == ".jar") \
        if directory.exists() else []
    if not jars:
        raise ModfetchError(f"No .jar files found in {directory}.")
    if not targets:
        raise ModfetchError("No targets given for removal. Use 'modfetch -R <mod>'.")
    removed = missing = 0
    for query in targets:
        matches = fuzzy_matches(query, jars)
        if not matches:
            fail(f"No installed mod matches {query!r}.", color)
            missing += 1
            continue
        print()
        info(f"Delete search for {query!r}:", color, a.quiet)
        for i, path in enumerate(matches, 1):
            print(f"  {i:>2}) {path.name}")
        if a.can_prompt:
            choice = select_number(f"Select a file [1-{len(matches)}]", len(matches), color)
            selected = matches[choice - 1]
        else:
            selected = matches[0]
            warn(f"Selecting top match {selected.name!r}.", color)
        if not a.noconfirm and not prompt(f"Delete {selected.name}?", default=False):
            print("Nothing deleted.")
            continue
        try:
            selected.unlink()
        except OSError as exc:
            raise ModfetchError(f"Could not delete {selected}: {exc}") from exc
        jars.remove(selected)
        ok(f"Deleted {selected.name}", color)
        removed += 1
    if missing:
        warn(f"{missing} quer(y/ies) had no match.", color)
    return 0


def cmd_list(a, targets, color):
    directory = a.mods_dir
    jars = sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() == ".jar") \
        if directory.exists() else []
    query = " ".join(targets).strip().lower()
    print()
    info(f"Installed mods in {directory}", color, a.quiet)
    if not jars:
        print("  (no .jar files found)")
        return 0
    shown = 0
    for i, path in enumerate(jars, 1):
        if query and query not in path.stem.lower() and query not in path.name.lower():
            continue
        try:
            size = human(path.stat().st_size)
        except OSError:
            size = "?"
        print(f"  {i:>3}. {path.name}  {c('(' + size + ')', DIM, enabled=color)}")
        shown += 1
    if query:
        print(f"\n  {shown} of {len(jars)} mod(s) match.")
    else:
        print(f"\n  Total: {len(jars)} mod JAR(s)")
    return 0


def cmd_config(a, targets, color):
    ensure_config()
    if not targets:
        action = "show"
    elif targets[0] in {"show", "edit"}:
        action = targets[0]
    else:
        action = "setup"

    if action == "show":
        print_config(load_config(), color=color)
        return 0

    if action == "setup":
        instance = targets[0]
        mc_version = targets[1] if len(targets) > 1 else None
        instance_path = Path.home() / ".minecraft" / "versions" / instance
        config = {
            "mods_dir": str(instance_path / "mods"),
            "resourcepacks_dir": str(instance_path / "resourcepacks"),
            "shaderpacks_dir": str(instance_path / "shaderpacks"),
            "config_dir": str(instance_path / "config"),
            "loader": load_config().get("loader", "fabric"),
            "minecraft_version": mc_version or load_config().get("minecraft_version", "latest"),
        }
        validate_config(config)
        write_config(config)
        print_config(config, color=color)
        ok(f"Configured for instance: {instance}", color)
        return 0

    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        for candidate in ("nvim", "vim", "vi", "nano"):
            if shutil.which(candidate):
                editor = candidate
                break
    if not editor:
        raise ModfetchError("No editor found. Set $EDITOR (for example: export EDITOR=nvim).")

    try:
        subprocess.run([editor, str(CONFIG_FILE)], check=True)
    except FileNotFoundError as exc:
        raise ModfetchError(f"Editor not found: {editor}") from exc
    except subprocess.CalledProcessError as exc:
        raise ModfetchError(f"Editor exited with status {exc.returncode}.") from exc

    validate_config(load_config())
    ok(f"Configuration saved: {CONFIG_FILE}", color)
    return 0


# ---------------------------------------------------------------------------
# CLI parsing (paru-style)
# ---------------------------------------------------------------------------

def parser():
    examples = """\
operations:
  -S, --sync             install mods / modpacks / resource packs (auto-detected)
  -Q, --query            list installed mods
  -R, --remove           remove installed mods (fuzzy match)
  modifiers
  -s, --search           with -S: search Modrinth; with -Q: search installed
  -i, --info             with -S: show project information
  -u, --sysupgrade       with -S: update all installed mods   (-Syu / -Syyu / ...)
  -y, --refresh          with -Syu: ignored; with -Syyu: resolve dependencies
  bare invocations:
  modfetch                     update all installed mods        (≈ -Syu)
  modfetch <target>            interactively search and install (≈ -S --interactive)

examples:
  modfetch sodium                  interactive search + install sodium
  modfetch -S sodium               install sodium (auto-selects exact match)
  modfetch -S mypack               install a modpack (project type auto-detected)
  modfetch -S <modrinth-url>       install from a project URL
  modfetch -Ss sodium              search Modrinth
  modfetch -Si sodium              show project info
  modfetch -Syu sodium             update everything, then install sodium
  modfetch -Syyu                    update all mods + resolve dependencies
  modfetch -Qu                     list available updates
  modfetch -Q                      list installed mods
  modfetch -Qs sodium              list installed mods matching 'sodium'
  modfetch -R sodium               remove a mod
  modfetch pack mypack             force modpack installation
  modfetch resourcepack sodium     force resource pack installation
  modfetch shaderpack BSL Shaders  force shader pack installation
  modfetch config show             show the configuration
  modfetch config edit             edit the configuration file
  modfetch config <instance>       configure for a Minecraft instance
  modfetch config <instance> <ver> configure with MC version
"""
    p = argparse.ArgumentParser(
        prog="modfetch",
        description="paru-style Modrinth installer for Minecraft mods, modpacks, and resource packs.",
        epilog=examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("-S", "--sync", dest="op", action="store_const", const=OP_SYNC,
                   help="synchronize (install) targets from Modrinth")
    p.add_argument("-Q", "--query", dest="op", action="store_const", const=OP_QUERY,
                   help="query installed mods")
    p.add_argument("-R", "--remove", dest="op", action="store_const", const=OP_REMOVE,
                   help="remove installed mods")
    p.add_argument("-s", "--search", action="store_true", help="search (modifies -S / -Q)")
    p.add_argument("-i", "--info", action="store_true", help="show project info (modifies -S)")
    p.add_argument("-u", "--sysupgrade", action="store_true", help="update all installed mods")
    p.add_argument("-y", "--refresh", action="count", default=0,
                   help="-Syu: update; -Syyu: update + resolve dependencies")
    p.add_argument("-q", "--quiet", action="store_true", help="suppress informational output")
    p.add_argument("--noconfirm", dest="noconfirm", action="store_true",
                   help="skip all confirmation prompts")
    p.add_argument("--yes", dest="noconfirm", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--needed", action="store_true", dest="needed",
                   help="skip files already installed with identical content (default behavior)")
    p.add_argument("--force", action="store_true", help="re-download and replace existing files")
    p.add_argument("--interactive", action="store_true",
                   help="interactive selection (default for bare invocations)")
    p.add_argument("-g", "--game-version", "--mc-version", "--minecraft-version",
                   dest="mc_version", metavar="VERSION", default=argparse.SUPPRESS,
                   help="Minecraft version to download mods for, e.g. 26.1.2 "
                        "(or 'latest' to use the newest release; defaults to config)")
    p.add_argument("-r", dest="mc_version", metavar="VERSION", default=argparse.SUPPRESS,
                   help=argparse.SUPPRESS)
    p.add_argument("-l", "--loader", choices=SUPPORTED_LOADERS, default=argparse.SUPPRESS,
                   help="mod loader to target (fabric, forge, neoforge, quilt)")
    p.add_argument("-d", "--directory", default=argparse.SUPPRESS, action="store",
                   help="install directory for mods and resource packs")
    p.add_argument("--confdir", dest="config_dir", default=None, action="store",
                   help="directory for mod config files (from modpacks)")
    p.add_argument("--shaderpacks-dir", dest="shaderpacks_dir", default=argparse.SUPPRESS,
                   action="store", help="directory for shader packs")
    p.add_argument("--mod-version", dest="mod_version", default=None,
                   help="exact Modrinth version number to install")
    p.add_argument("--no-color", dest="no_color", action="store_true", help="disable ANSI colors")
    p.add_argument("-v", "--version", action="store_true", help="print version and exit")
    p.add_argument("targets", nargs="*", metavar="TARGET",
                   help="mod name, slug, or Modrinth project URL")
    return p


def compute_command(a):
    """Translate the parsed namespace into (action, targets, type_pref).

    precedence: operation flag (-S/-Q/-R) > legacy subcommand word > bare invocation.
    """
    targets = list(a.targets)
    op = a.op
    type_pref = None
    action = None

    if op is None and targets and targets[0] in LEGACY_SUBCOMMANDS:
        word = targets.pop(0)
        op, action, type_pref = LEGACY_SUBCOMMANDS[word]

    if op is None:
        if a.sysupgrade or a.search or a.info:
            op = OP_SYNC  # long-only modifiers imply a sync operation
        elif not targets:
            action = "update"       # paru: bare invocation == -Syu
        else:
            action = "install"      # paru: bare invocation == -S --interactive
            a.interactive = True

    if op == OP_SYNC:
        if action is None:
            if a.search:
                action = "search"
            elif a.info:
                action = "info"
            elif a.sysupgrade:
                action = "update"
            elif targets:
                action = "install"
            else:
                raise ModfetchError("No targets given. See 'modfetch --help' for usage.")
    elif op == OP_QUERY:
        if action is None:
            action = "check" if a.sysupgrade else "list"
    elif op == OP_REMOVE:
        if action is None:
            action = "remove"

    return action, targets, type_pref


def normalize_argv(argv):
    """Move all options (and their values) before positional targets.

    argparse cannot resume a single `nargs="*"` positional once an optional with
    a value appears mid-way (e.g. `modfetch pack -d /tmp/x mypack` fails), so we
    reorder the argv into [options..., targets...]. With exactly one positional
    argument this is semantically transparent.
    """
    options = []
    targets = []
    only_positional = False
    saw_double_dash = False
    i, n = 0, len(argv)
    while i < n:
        token = argv[i]
        if only_positional:
            targets.append(token)
            i += 1
            continue
        if token == "--":
            only_positional = True
            saw_double_dash = True
            i += 1
            continue
        if token == "-" or not token.startswith("-"):
            targets.append(token)
            i += 1
            continue

        if token.startswith("--"):
            options.append(token)
            if token in VALUE_OPTS and "=" not in token and i + 1 < n:
                options.append(argv[i + 1])
                i += 1
            i += 1
            continue

        # Short option / cluster, e.g. -Syu, -Ss, -d/tmp, -lfabric.
        body = token[1:]
        j = 0
        while j < len(body):
            char = body[j]
            if char in VALUED_SHORTS:
                rest = body[j + 1:]
                if rest:
                    options.append(f"-{char}={rest}")  # inline value
                else:
                    options.append(f"-{char}")
                    if i + 1 < n:
                        options.append(argv[i + 1])
                        i += 1
                break
            options.append(f"-{char}")
            j += 1
        i += 1
    return options + (["--"] if saw_double_dash else []) + targets


def main(argv=None):
    raw = normalize_argv(list(sys.argv[1:] if argv is None else argv))
    parser_cli = parser()
    a = parser_cli.parse_args(raw)
    a.color = not a.no_color and sys.stdout.isatty() and "NO_COLOR" not in os.environ
    a.can_prompt = not a.noconfirm and sys.stdin.isatty()

    try:
        if a.version:
            print(f"modfetch {VERSION}")
            return 0

        action, targets, type_pref = compute_command(a)

        if action == "config":
            return cmd_config(a, targets, a.color)

        config = effective_config(a)
        a.mods_dir = expand_path(config["mods_dir"])
        a.resourcepacks_dir = expand_path(config["resourcepacks_dir"])
        a.shaderpacks_dir = expand_path(config["shaderpacks_dir"])
        a.config_dir = expand_path(config["config_dir"])
        a.loader = config["loader"]
        a.mc_version = None if config["minecraft_version"].lower() == "latest" else config["minecraft_version"]

        if action == "install":
            return cmd_install(a, targets, type_pref, a.color)
        if action == "update":
            result = cmd_update(a, dry_run=False, color=a.color)
            if targets:  # -Syu <target>: update everything, then install the target
                result = cmd_install(a, targets, None, a.color)
            return result
        if action == "search":
            return cmd_search(a, targets, a.color)
        if action == "info":
            return cmd_info(a, targets, a.color)
        if action == "list":
            return cmd_list(a, targets, a.color)
        if action == "check":
            return cmd_update(a, dry_run=True, color=a.color)
        if action == "remove":
            return cmd_remove(a, targets, a.color)

        raise ModfetchError(f"Unhandled action {action!r}.")

    except KeyboardInterrupt:
        fail("Interrupted.", a.color)
        return 130
    except ModfetchError as exc:
        fail(str(exc), a.color)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())