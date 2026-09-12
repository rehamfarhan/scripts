# modfetch

A paru-style Modrinth installer for Minecraft mods, modpacks, resource packs, and shader packs.

## Configuration

Config file: `~/.config/modfetch/config.toml`

```toml
mods_dir = "~/.minecraft/versions/<instance>/mods/"
resourcepacks_dir = "~/.minecraft/versions/<instance>/resourcepacks/"
shaderpacks_dir = "~/.minecraft/versions/<instance>/shaderpacks/"
config_dir = "~/.minecraft/versions/<instance>/config/"
loader = "fabric"
minecraft_version = "26.1.2"
```

| Key | Description |
|-----|-------------|
| `mods_dir` | Where mod JARs are installed |
| `resourcepacks_dir` | Where resource packs are installed |
| `shaderpacks_dir` | Where shader packs are installed |
| `config_dir` | Where modpack config files are installed |
| `loader` | `fabric`, `forge`, `neoforge`, or `quilt` |
| `minecraft_version` | Target MC version, or `latest` for newest release |

CLI arguments (`-d`, `-l`, `-g`) override config values for a single invocation.

## Operations

| Flag | Description |
|------|-------------|
| `-S` | Install mods / modpacks / resource packs (auto-detected) |
| `-Q` | List installed mods |
| `-R` | Remove installed mods (fuzzy match) |

## Modifiers

| Flag | Description |
|------|-------------|
| `-s` | Search Modrinth (with `-Q`: search installed mods) |
| `-i` | Show project info (with `-S`) |
| `-u` | Update all installed mods (with `-S`: `-Syu` / `-Syyu`) |
| `-y` | `-Syu`: update only; `-Syyu`: update + resolve dependencies |
| `-g <ver>` | Target Minecraft version (e.g. `-g 26.1.2`) |
| `-l <loader>` | Target mod loader (e.g. `-l fabric`) |
| `-d <dir>` | Install directory for mods and resource packs |
| `--confdir <dir>` | Directory for modpack config files |
| `--shaderpacks-dir <dir>` | Directory for shader packs |
| `--force` | Re-download and replace existing files |
| `--noconfirm` | Skip all confirmation prompts |
| `-q` | Suppress informational output |
| `-v` | Print version and exit |

## Examples

### Install

```sh
modfetch sodium                  # interactive search + install
modfetch -S sodium               # install (auto-selects exact match)
modfetch -S "Fabulously Optimized"  # install modpack (auto-detected)
modfetch -S https://modrinth.com/mod/sodium  # install from URL
modfetch -S sodium -g 26.1.2     # install for specific MC version
modfetch -S sodium -l forge      # install for specific loader
modfetch -S mypack -d ~/test     # install to custom directory
```

### Search & Info

```sh
modfetch -Ss sodium              # search Modrinth
modfetch -Si sodium              # show project info
```

### Update

```sh
modfetch                         # update all installed mods (bare = -Syu)
modfetch -Syu                    # update all mods
modfetch -Syyu                   # update all mods + resolve dependencies
modfetch -Syu sodium             # update everything, then install sodium
modfetch -Qu                     # list available updates
```

### List

```sh
modfetch -Q                      # list all installed mods
modfetch -Qs sodium              # list mods matching 'sodium'
```

### Remove

```sh
modfetch -R sodium               # remove a mod (fuzzy match)
```

### Legacy subcommands

These still work as aliases:

```sh
modfetch install sodium          # same as -S sodium
modfetch pack mypack             # force modpack installation
modfetch resourcepack sodium     # force resource pack installation
modfetch shaderpack BSL Shaders  # force shader pack installation
modfetch update                  # same as -Syu
modfetch search foo              # same as -Ss foo
modfetch info sodium             # same as -Si sodium
modfetch config show             # show configuration
modfetch config edit             # edit configuration file
modfetch config <instance>       # configure for a Minecraft instance
modfetch config <instance> <ver> # configure with MC version
```

## Modpack behavior

When installing a modpack (`-S <modpack>`), modfetch:

1. **Downloads mods** → `mods_dir`
2. **Downloads resource packs** → `resourcepacks_dir`
3. **Downloads shader packs** → `shaderpacks_dir`
4. **Applies config overrides** → `config_dir` (always overwritten with pack author's settings)

Files under `overrides/config/modpack_defaults/` are flattened to the root of `config_dir`, so mods find them where they expect.

Unsupported client files are skipped. Server overrides are skipped. Duplicate paths are skipped.

## -Syu vs -Syyu

| Command | Behavior |
|---------|----------|
| `-Syu` | Update all installed mods to latest versions |
| `-Syyu` | Update all mods + check and install missing required dependencies |

The second `-y` triggers dependency resolution after updates.

## Bare invocations

```sh
modfetch                         # = -Syu (update all)
modfetch <target>                # = -S --interactive (search + install)
```
