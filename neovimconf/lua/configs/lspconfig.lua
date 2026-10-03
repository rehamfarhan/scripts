local nvlsp = require "nvchad.configs.lspconfig"

-- Load NvChad default LSP settings & keymaps
nvlsp.defaults()

-- Configure diagnostic options to keep editor clean & non-distracting
vim.diagnostic.config {
  virtual_text = {
    prefix = "●",
    spacing = 2,
    severity = { min = vim.diagnostic.severity.WARN },
  },
  signs = true,
  underline = true,
  update_in_insert = false, -- Prevent error messages from jumping around while typing
  severity_sort = true,
  float = {
    border = "rounded",
    source = "always",
  },
}

-- C# LSP (csharp-ls: fast, Roslyn-powered, lightweight)
vim.lsp.config("csharp_ls", {
  cmd = { vim.fn.expand "~/.dotnet/tools/csharp-ls" },
  filetypes = { "cs" },
  root_markers = { "*.sln", "*.slnx", "*.csproj", ".git" },
  init_options = {
    AutomaticWorkspaceInit = true,
  },
  handlers = {
    -- Suppress automatic signature help popups while typing parameter lists
    ["textDocument/signatureHelp"] = function() end,
  },
})

-- Enable desired LSP servers using native vim.lsp.enable
vim.lsp.enable { "html", "cssls", "csharp_ls" }

-- Completely disable signature help tooltips inside parentheses
vim.api.nvim_create_autocmd("LspAttach", {
  callback = function(args)
    local client = vim.lsp.get_client_by_id(args.data.client_id)
    if client then
      client.server_capabilities.signatureHelpProvider = nil
    end
  end,
})



