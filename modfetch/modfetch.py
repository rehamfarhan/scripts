#!/usr/bin/env python3
"""modfetch: verbose Modrinth CLI for Minecraft Fabric mods."""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import sys
import tempfile
import shutil
import subprocess
import tomllib
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

API = "https://api.modrinth.com/v2"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "modfetch"
CONFIG_FILE = CONFIG_DIR / "config.toml"
DEFAULT_DIR = Path.home() / ".minecraft" / "mods"
DEFAULT_LOADER = "fabric"
UA = "modfetch/0.2.0"

CONFIG_TEMPLATE = """# modfetch configuration
# CLI arguments override these values for a single invocation.

mods_dir = \"~/.minecraft/mods\"
loader = \"fabric\"
# Set to \"latest\" to use the newest Minecraft release supported by the mod.
minecraft_version = \"latest\"
"""

RESET="\033[0m"; BOLD="\033[1m"; DIM="\033[2m"; CYAN="\033[36m"; GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"; MAGENTA="\033[35m"

class ModfetchError(RuntimeError): pass

def c(text, *styles, enabled=True): return "".join(styles)+text+RESET if enabled else text

def info(msg, enabled=True): print(c("==> ", BOLD, CYAN, enabled=enabled)+msg)
def ok(msg, enabled=True): print(c("✓ ", BOLD, GREEN, enabled=enabled)+msg)
def warn(msg, enabled=True): print(c("⚠ ", BOLD, YELLOW, enabled=enabled)+msg)
def fail(msg, enabled=True): print(c("✗ ", BOLD, RED, enabled=enabled)+msg, file=sys.stderr)

def expand_path(value: str | Path) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(value))).strip())

def default_config() -> dict[str, str]:
    return {
        "mods_dir": str(DEFAULT_DIR),
        "loader": DEFAULT_LOADER,
        "minecraft_version": "latest",
    }

def validate_config(config: dict) -> dict[str, str]:
    result = default_config()
    for key in result:
        if key in config:
            value = config[key]
            if not isinstance(value, str) or not value.strip():
                raise ModfetchError(f"Invalid config value for {key!r}: expected a non-empty string.")
            result[key] = value.strip()

    supported_loaders = {"fabric", "forge", "neoforge", "quilt"}
    if result["loader"] not in supported_loaders:
        raise ModfetchError(
            f"Unsupported loader {result['loader']!r} in {CONFIG_FILE}. "
            f"Choose one of: {', '.join(sorted(supported_loaders))}."
        )
    return result

def load_config() -> dict[str, str]:
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

def ensure_config() -> None:
    if CONFIG_FILE.exists():
        return
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(CONFIG_TEMPLATE, encoding="utf-8")
    except OSError as exc:
        raise ModfetchError(f"Could not create {CONFIG_FILE}: {exc}") from exc

def write_config(config: dict[str, str]) -> None:
    validate_config(config)
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            "# modfetch configuration\n"
            "# CLI arguments override these values for a single invocation.\n\n"
            f"mods_dir = {json.dumps(config['mods_dir'])}\n"
            f"loader = {json.dumps(config['loader'])}\n"
            f"minecraft_version = {json.dumps(config['minecraft_version'])}\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise ModfetchError(f"Could not write {CONFIG_FILE}: {exc}") from exc

def effective_config(args: argparse.Namespace, *, command: str) -> dict[str, str]:
    config = load_config()
    if getattr(args, "directory", None) is not None and args.directory_was_explicit:
        config["mods_dir"] = str(args.directory)
    if getattr(args, "loader", None) is not None and args.loader_was_explicit:
        config["loader"] = args.loader
    if getattr(args, "mc_version", None) is not None and args.mc_version_was_explicit:
        config["minecraft_version"] = args.mc_version
    return validate_config(config)

def print_config(config: dict[str, str], *, color: bool) -> None:
    print()
    info(f"Configuration: {CONFIG_FILE}", color)
    print(f"  mods_dir         = {config['mods_dir']}")
    print(f"  loader           = {config['loader']}")
    print(f"  minecraft_version = {config['minecraft_version']}")

def api(path, method="GET", params=None, body=None):
    url=API+path
    if params:
        q={k: json.dumps(v,separators=(",",":")) if isinstance(v,list) else v for k,v in params.items()}
        url += "?" + urlencode(q)
    headers={"Accept":"application/json","User-Agent":UA}
    data=None
    if body is not None:
        data=json.dumps(body).encode(); headers["Content-Type"]="application/json"
    req=Request(url,data=data,headers=headers,method=method)
    try:
        with urlopen(req,timeout=25) as r: raw=r.read()
    except HTTPError as e:
        try:
            payload=json.loads(e.read().decode(errors="replace")); detail=payload.get("description") or payload.get("error") or str(payload)
        except Exception: detail=str(e)
        raise ModfetchError(f"Modrinth API returned HTTP {e.code}: {detail}") from e
    except (URLError, TimeoutError) as e:
        raise ModfetchError(f"Could not reach Modrinth API: {getattr(e,'reason',e)}") from e
    try: return json.loads(raw)
    except json.JSONDecodeError as e: raise ModfetchError("Modrinth returned invalid JSON.") from e

def sha1(path):
    h=hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def download(url,dest,expected=None):
    req=Request(url,headers={"User-Agent":UA})
    dest.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".modfetch-",dir=dest.parent); os.close(fd); tmp=Path(tmp)
    try:
        with urlopen(req,timeout=90) as r,tmp.open("wb") as f:
            while chunk:=r.read(256*1024): f.write(chunk)
        if expected and sha1(tmp).lower()!=expected.lower():
            raise ModfetchError(f"SHA-1 verification failed for {dest.name}.")
        tmp.replace(dest)
    except HTTPError as e: raise ModfetchError(f"Download failed with HTTP {e.code}.") from e
    except (URLError,TimeoutError) as e: raise ModfetchError(f"Download failed: {getattr(e,'reason',e)}") from e
    finally: tmp.unlink(missing_ok=True)

def human(n):
    x=float(n)
    for u in ("B","KiB","MiB","GiB"):
        if x<1024 or u=="GiB": return f"{x:.1f} {u}" if u!="B" else f"{int(x)} B"
        x/=1024

def search_project(query,color):
    hits=api("/search",params={"query":query,"limit":20,"index":"relevance"}).get("hits",[])
    mods=[h for h in hits if h.get("project_type")=="mod"]
    if not mods: raise ModfetchError(f"No Modrinth mods found for '{query}'.")
    print(); info(f"Search results for {query!r}:",True)
    for i,item in enumerate(mods[:10],1):
        title=item.get("title") or item.get("slug") or item.get("project_id")
        desc=(item.get("description") or "").replace("\n"," ").strip(); desc=desc if len(desc)<=84 else desc[:81]+"..."
        print(f"  {i:>2}) {c(title,BOLD,enabled=color)}")
        print(f"      {c(item.get('slug',''),DIM,enabled=color)}")
        if desc: print(f"      {desc}")
    if len(mods)==1: return mods[0]
    while True:
        a=input(f"\nSelect a project [1-{min(10,len(mods))}] (q to cancel): ").strip()
        if a.lower() in {"q","quit","cancel"}: raise ModfetchError("Selection cancelled.")
        if a.isdigit() and 1<=int(a)<=min(10,len(mods)): return mods[int(a)-1]
        warn("Enter one of the displayed numbers or q.",color)

def parse_url(value):
    p=urlparse(value)
    if p.scheme not in {"http","https"} or p.netloc.lower() not in {"modrinth.com","www.modrinth.com"}:
        raise ModfetchError("Unsupported URL. Use a Modrinth mod page URL.")
    parts=[x for x in p.path.split("/") if x]
    if len(parts)>=2 and parts[0] in {"mod","project"}: return parts[1]
    raise ModfetchError("Expected https://modrinth.com/mod/<slug>.")

def project_from(value,color):
    if value.startswith(("http://","https://")):
        return api(f"/project/{quote(parse_url(value),safe='')}")
    return search_project(value,color)

def primary(ver):
    files=ver.get("files") or []
    if not files: raise ModfetchError(f"Modrinth version {ver.get('version_number','?')} has no files.")
    return next((f for f in files if f.get("primary")),files[0])

def resolve(project,mc=None,mod_version=None,color=False,loader=DEFAULT_LOADER):
    params={"loaders":[loader],"include_changelog":False}
    if mc: params["game_versions"]=[mc]
    versions=api(f"/project/{quote(project['id'],safe='')}/version",params=params)
    versions=[v for v in versions if v.get("version_type")=="release" and loader in v.get("loaders",[]) and (not mc or mc in v.get("game_versions",[]))]
    if mod_version: versions=[v for v in versions if v.get("version_number")==mod_version]
    versions.sort(key=lambda v:v.get("date_published", ""),reverse=True)
    if not versions:
        target=mc or "any supported Minecraft version"
        extra=f" and mod version {mod_version!r}" if mod_version else ""
        raise ModfetchError(f"No {loader} release of {project.get('title',project['id'])} matches {target}{extra}.")
    v=versions[0]
    info(f"Resolved {project.get('title',project['id'])} → {v['version_number']} for {loader} / Minecraft {', '.join(v.get('game_versions',[])[:4])}",color)
    return v

def local_index(directory):
    result={}
    if not directory.exists(): return result
    for p in directory.iterdir():
        if p.is_file() and p.suffix.lower()==".jar":
            try: result[sha1(p)]=p
            except OSError: pass
    return result

def dep_version(dep,mc,color,loader):
    if dep.get("version_id"):
        v=api(f"/version/{quote(dep['version_id'],safe='')}"); p=api(f"/project/{quote(v['project_id'],safe='')}"); return p,v
    if not dep.get("project_id"): raise ModfetchError("A required dependency lacks project/version metadata.")
    p=api(f"/project/{quote(dep['project_id'],safe='')}"); return p,resolve(p,mc,None,color,loader)

def install_version(project,ver,directory,force,yes,mc,color,loader=DEFAULT_LOADER,stack=None):
    stack=set() if stack is None else stack
    pid=project["id"]
    if pid in stack: raise ModfetchError(f"Dependency cycle detected at {project.get('title',pid)}.")
    stack.add(pid)
    try:
        deps=[d for d in ver.get("dependencies",[]) if d.get("dependency_type")=="required"]
        if deps:
            print(); info(f"{project.get('title',pid)} requires {len(deps)} dependency/dependencies.",color)
        for dep in deps:
            p,v=dep_version(dep,mc,color,loader); f=primary(v); existing=local_index(directory)
            expected=(f.get("hashes") or {}).get("sha1"); name=p.get("title") or p.get("slug") or p["id"]
            present=(directory/f["filename"]) if (directory/f["filename"]).is_file() else existing.get(expected) if expected else None
            if present:
                ok(f"Dependency already present: {name} → {present.name}",color); continue
            if not yes:
                a=input(f"  Install required dependency {name} ({v['version_number']})? [Y/n]: ").strip().lower()
                if a not in {"","y","yes"}: raise ModfetchError(f"Required dependency {name} was declined.")
            install_version(p,v,directory,force,yes,mc,color,loader,stack)
        f=primary(ver); dest=directory/f["filename"]; expected=(f.get("hashes") or {}).get("sha1")
        if dest.is_file() and not force:
            if not expected or sha1(dest).lower()==expected.lower(): ok(f"Already present: {dest.name}",color); return
        directory.mkdir(parents=True,exist_ok=True)
        info(f"Downloading {f['filename']} ({human(int(f.get('size',0)))})…",color)
        download(f["url"],dest,expected)
        ok(f"Installed {project.get('title',pid)} {ver['version_number']} → {dest}",color)
    finally: stack.remove(pid)

def cmd_install(a):
    a.directory.mkdir(parents=True,exist_ok=True)
    for item in a.mods:
        print(); info(f"Looking up {item!r}…",a.color)
        p=project_from(item,a.color); v=resolve(p,a.mc_version,a.mod_version,a.color,a.loader)
        install_version(p,v,a.directory,a.force,a.yes,a.mc_version,a.color,a.loader)
    print(); ok(f"Finished. Mods directory: {a.directory}",a.color); return 0

def latest_release(color):
    versions=api("/tag/game_version")
    releases=[v for v in versions if v.get("version_type")=="release"]
    if not releases: raise ModfetchError("Could not determine the latest Minecraft release.")
    releases.sort(key=lambda x:x.get("date", ""),reverse=True)
    latest=releases[0]["version"]
    info(f"No Minecraft version supplied; using latest release {latest}.",color)
    return latest

def cmd_update(a):
    jars=sorted(p for p in a.directory.iterdir() if p.is_file() and p.suffix.lower()==".jar") if a.directory.exists() else []
    if not jars: print(f"No .jar files found in {a.directory}."); return 0
    target=a.mc_version or latest_release(a.color)
    info(f"Updating {a.loader} mods in {a.directory} for Minecraft {target}…",a.color)
    pairs=[]
    for p in jars:
        try: pairs.append((sha1(p),p))
        except OSError as e: warn(f"Could not hash {p.name}: {e}",a.color)
    if not pairs: return 0
    body={"hashes":[h for h,_ in pairs],"algorithm":"sha1","loaders":[a.loader],"game_versions":[target],"version_types":["release"]}
    updates=api("/version_files/update",method="POST",body=body)
    changed=skipped=0
    for digest,old in pairs:
        v=updates.get(digest)
        if not v:
            warn(f"{old.name}: no compatible release found for Minecraft {target}; skipped.",a.color); skipped+=1; continue
        f=primary(v); new= a.directory/f["filename"]; newhash=(f.get("hashes") or {}).get("sha1")
        if newhash and newhash.lower()==digest.lower() and not a.force:
            ok(f"{old.name}: already current ({v['version_number']}).",a.color); skipped+=1; continue
        if new!=old and new.exists() and not a.force:
            warn(f"{old.name}: target {new.name} already exists; use --force to replace it.",a.color); skipped+=1; continue
        info(f"{old.name} → {new.name} ({v['version_number']})",a.color)
        download(f["url"],new,newhash)
        if new!=old:
            try: old.unlink()
            except OSError as e: warn(f"Updated, but could not remove {old.name}: {e}",a.color)
        ok(f"Updated to {v['version_number']}.",a.color); changed+=1
    print(); ok(f"Update complete: {changed} changed, {skipped} skipped.",a.color); return 0

def cmd_list(a):
    jars=sorted(p for p in a.directory.iterdir() if p.is_file() and p.suffix.lower()==".jar") if a.directory.exists() else []
    print(); info(f"Installed mods in {a.directory}",a.color)
    if not jars: print("  (no .jar files found)"); return 0
    for i,p in enumerate(jars,1):
        try: size=human(p.stat().st_size)
        except OSError: size="?"
        print(f"  {i:>3}. {p.name}  {c('('+size+')',DIM,enabled=a.color)}")
    print(f"\n  Total: {len(jars)} mod JAR(s)"); return 0

def cmd_delete(a):
    jars=sorted(p for p in a.directory.iterdir() if p.is_file() and p.suffix.lower()==".jar") if a.directory.exists() else []
    if not jars: raise ModfetchError(f"No .jar files found in {a.directory}.")
    q=" ".join(a.query).strip().lower(); scored=[]
    for p in jars:
        n=p.stem.lower(); score=difflib.SequenceMatcher(None,q,n).ratio()+(1 if q in n else 0); scored.append((score,p))
    matches=[p for _,p in sorted(scored,key=lambda x:x[0],reverse=True)[:10]]
    print(); info(f"Delete search: {q!r}",a.color)
    for i,p in enumerate(matches,1): print(f"  {i:>2}) {p.name}")
    while True:
        s=input(f"\nSelect a file [1-{len(matches)}] (q to cancel): ").strip()
        if s.lower() in {"q","quit","cancel"}: raise ModfetchError("Deletion cancelled.")
        if s.isdigit() and 1<=int(s)<=len(matches): selected=matches[int(s)-1]; break
        warn("Enter a valid number or q.",a.color)
    if input(f"Delete {selected.name}? [y/N]: ").strip().lower() not in {"y","yes"}: print("Nothing deleted."); return 0
    try: selected.unlink()
    except OSError as e: raise ModfetchError(f"Could not delete {selected}: {e}") from e
    ok(f"Deleted {selected.name}",a.color); return 0

def cmd_config(a):
    ensure_config()
    if a.action == "show":
        print_config(load_config(), color=a.color)
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
    ok(f"Configuration saved: {CONFIG_FILE}", a.color)
    return 0

def common(p):
    p.add_argument("-d","--directory",type=Path,help="mods directory (default: config, then ~/.minecraft/mods)")
    p.add_argument("-r","--mc-version",dest="mc_version",help="Minecraft game version, e.g. 26.1.2")
    p.add_argument("-l","--loader",choices=["fabric","forge","neoforge","quilt"],help="mod loader (default: config, then fabric)")
    p.add_argument("--force",action="store_true",help="re-download/replace existing files")
    p.add_argument("-y","--yes",action="store_true",help="accept required dependency installs automatically")


def parser():
    p=argparse.ArgumentParser(prog="modfetch",description="Verbose Modrinth installer for Minecraft Fabric mods.")
    p.add_argument("--no-color",action="store_true",help="disable ANSI styling")
    sp=p.add_subparsers(dest="command")
    x=sp.add_parser("install",help="search/resolve/install mods"); common(x); x.add_argument("--mod-version",help="exact Modrinth mod version"); x.add_argument("mods",nargs="+"); x.set_defaults(func=cmd_install)
    x=sp.add_parser("url",help="install from Modrinth project URL(s)"); common(x); x.add_argument("urls",nargs="+"); x.set_defaults(func=lambda a:(setattr(a,"mods",a.urls),cmd_install(a))[1])
    x=sp.add_parser("list",help="list installed .jar files"); common(x); x.set_defaults(func=cmd_list)
    x=sp.add_parser("delete",help="fuzzy-search and delete a mod"); common(x); x.add_argument("query",nargs="+"); x.set_defaults(func=cmd_delete)
    x=sp.add_parser("update",help="update all recognized Modrinth mods"); common(x); x.set_defaults(func=cmd_update)
    x=sp.add_parser("config",help="show or edit modfetch configuration")
    x.add_argument("action",nargs="?",choices=["show","edit"],default="show")
    x.set_defaults(func=cmd_config)
    return p

def normalize(argv):
    commands={"install","url","list","delete","update","config","-h","--help"}
    if any(v in commands for v in argv):
        return argv

    # Bare shorthand is an install command. Move install-only/common options
    # after the injected subcommand while keeping the root --no-color flag.
    root_flags=[]
    install_args=[]
    value_flags={"-d","--directory","-r","--mc-version","-l","--loader","--mod-version"}
    boolean_flags={"--force","-y","--yes"}
    i=0
    while i < len(argv):
        v=argv[i]
        if v == "--no-color":
            root_flags.append(v); i += 1; continue
        if v in value_flags:
            if i+1 >= len(argv):
                return argv
            install_args.extend([v,argv[i+1]]); i += 2; continue
        if v in boolean_flags:
            install_args.append(v); i += 1; continue
        install_args.append(v); i += 1
    return root_flags + ["install"] + install_args

def main(argv=None):
    p=parser()
    raw=list(sys.argv[1:] if argv is None else argv)
    raw=normalize(raw)
    a=p.parse_args(raw)
    a.color=not a.no_color and sys.stdout.isatty()

    # Track explicit CLI values so config can supply defaults without
    # accidentally overriding command-line options.
    a.directory_was_explicit = any(x in {"-d","--directory"} for x in raw)
    a.loader_was_explicit = any(x in {"-l","--loader"} for x in raw)
    a.mc_version_was_explicit = any(x in {"-r","--mc-version"} for x in raw)

    if not a.command:
        p.print_help(); return 0
    try:
        if a.command == "config":
            return int(a.func(a))

        cfg=effective_config(a, command=a.command)
        a.directory=expand_path(cfg["mods_dir"])
        a.loader=cfg["loader"]
        a.mc_version=cfg["minecraft_version"]
        if a.mc_version.lower() == "latest":
            a.mc_version=None
        return int(a.func(a))
    except KeyboardInterrupt:
        fail("Interrupted.",a.color); return 130
    except ModfetchError as e:
        fail(str(e),a.color); return 1

if __name__=="__main__": raise SystemExit(main())
