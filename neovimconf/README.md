# neovimconf

My Neovim configuration, built on [NvChad](https://github.com/NvChad/NvChad) v2.5.

This is a personal config, not a distribution. It expects to be used the way NvChad's starter is used: this repo supplies the user files, and NvChad itself is pulled in as a plugin by `init.lua`.

## Layout

```
init.lua            entry point; bootstraps lazy.nvim, loads NvChad and the user files
lua/chadrc.lua      NvChad UI settings (theme, statusline, tabufline)
lua/options.lua     vim options
lua/mappings.lua    keymaps
lua/autocmds.lua    autocommands
lua/configs/        per-plugin configuration
lua/plugins/        plugin specs
snippets/           LuaSnip snippets
lazy-lock.json      pinned plugin versions
```

## Using it

Copy or symlink the folder to `~/.config/nvim`:

```bash
ln -s ~/scripts/neovimconf ~/.config/nvim
```

Then start `nvim`. `init.lua` clones `lazy.nvim` and installs the plugins on first launch. Plugin versions are pinned by `lazy-lock.json`; `:Lazy restore` reinstalls exactly those versions.

If you fork this for your own use, delete the `.git` directory or fork it, since it isn't meant to track upstream NvChad.

## Notes

- Leader key is `Space`.
- The base46 theme cache is written to Neovim's data directory by NvChad.
- Requires Neovim 0.10 or newer, `git`, and a C compiler for `treesitter`.
