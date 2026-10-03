return {
  {
    "stevearc/conform.nvim",
    -- event = 'BufWritePre', -- uncomment for format on save
    opts = require "configs.conform",
  },

  {
    "folke/noice.nvim",
    event = "VeryLazy",
    opts = require "plugins.noice",
  },

  {
    "rcarriga/nvim-notify",
    opts = require "plugins.notify",
  },

  -- These are some examples, uncomment them if you want to see them work!
  {
    "neovim/nvim-lspconfig",
    config = function()
      require "configs.lspconfig"
    end,
  },

  -- test new blink
  -- { import = "nvchad.blink.lazyspec" },

  {
    "nvim-treesitter/nvim-treesitter",
    lazy = false,
    opts = {
      ensure_installed = { "c_sharp", "lua", "vim", "vimdoc" },
    },
  },

  {
    "hrsh7th/nvim-cmp",
    opts = function(_, opts)
      local cmp = require "cmp"
      local types = require "cmp.types"

      opts.matching = {
        disallow_fuzzy_matching = false,
        disallow_fullfuzzy_matching = false,
        disallow_partial_fuzzy_matching = false,
        disallow_partial_matching = false,
        disallow_prefix_unmatching = false,
      }

      opts.sources = {
        { name = "luasnip", priority = 1000 },
        { name = "nvim_lsp", priority = 750 },
        { name = "buffer", priority = 500 },
        { name = "nvim_lua", priority = 250 },
        { name = "async_path", priority = 100 },
      }

      opts.sorting = {
        priority_weight = 2,
        comparators = {
          -- Prioritize Snippets at the top of the autocompletion menu
          function(entry1, entry2)
            local kind1 = entry1:get_kind()
            local kind2 = entry2:get_kind()
            if kind1 == types.lsp.CompletionItemKind.Snippet and kind2 ~= types.lsp.CompletionItemKind.Snippet then
              return true
            elseif kind2 == types.lsp.CompletionItemKind.Snippet and kind1 ~= types.lsp.CompletionItemKind.Snippet then
              return false
            end
          end,
          cmp.config.compare.offset,
          cmp.config.compare.exact,
          cmp.config.compare.score,
          cmp.config.compare.recently_used,
          cmp.config.compare.locality,
          cmp.config.compare.kind,
          cmp.config.compare.sort_text,
          cmp.config.compare.length,
          cmp.config.compare.order,
        },
      }

      opts.mapping = vim.tbl_extend("force", opts.mapping or {}, {
        ["<Tab>"] = cmp.mapping(function(fallback)
          local luasnip = require "luasnip"
          if luasnip.expand_or_jumpable() then
            luasnip.expand_or_jump()
          else
            fallback()
          end
        end, { "i", "s" }),

        ["<S-Tab>"] = cmp.mapping(function(fallback)
          local luasnip = require "luasnip"
          if luasnip.jumpable(-1) then
            luasnip.jump(-1)
          else
            fallback()
          end
        end, { "i", "s" }),

        ["<Down>"] = cmp.mapping(function(fallback)
          if cmp.visible() then
            cmp.select_next_item()
          else
            fallback()
          end
        end, { "i", "s" }),

        ["<Up>"] = cmp.mapping(function(fallback)
          if cmp.visible() then
            cmp.select_prev_item()
          else
            fallback()
          end
        end, { "i", "s" }),
      })

      return opts
    end,
  },



  {
    "L3MON4D3/LuaSnip",
    config = function(_, opts)
      require "nvchad.configs.luasnip"
      require("luasnip.loaders.from_vscode").lazy_load {
        paths = { vim.fn.stdpath "config" .. "/snippets" },
      }
    end,
  },

  {
    "kylechui/nvim-surround",
    version = "*",
    event = "VeryLazy",
    config = function()
      require("nvim-surround").setup({
        surrounds = {
          ["("] = { add = { "(", ")" } },
          ["{"] = { add = { "{", "}" } },
          ["["] = { add = { "[", "]" } },
        },
      })
      vim.keymap.set("x", "s", "<Plug>(nvim-surround-visual)", { desc = "Add surrounding pair around selection" })
    end,
  },



}






