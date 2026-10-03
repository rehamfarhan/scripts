require "nvchad.mappings"

local map = vim.keymap.set

map("n", ";", ":", { desc = "CMD enter command mode" })
map("i", "jk", "<ESC>")

-- C# Execution
map("n", "<leader>rr", "<cmd>w<cr><cmd>split | terminal dotnet run<cr>i", { desc = "Save and run C# project" })
map("n", "<leader>ru", "<cmd>split | terminal dotnet run --no-build<cr>i", { desc = "Run C# project (no build)" })

-- Clean Diagnostic Inspection (Open error window on demand)
map("n", "<leader>e", vim.diagnostic.open_float, { desc = "Show line diagnostic / error details" })
map("n", "gl", vim.diagnostic.open_float, { desc = "Show line diagnostic / error details" })
map("n", "[d", vim.diagnostic.goto_prev, { desc = "Go to previous error/warning" })
map("n", "]d", vim.diagnostic.goto_next, { desc = "Go to next error/warning" })

