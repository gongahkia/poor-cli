-- poor-cli.lua
-- Auto-load script for poor-cli Neovim plugin
--
-- This file is loaded automatically when Neovim starts.
-- The plugin is NOT initialized until you call:
--   require('poor-cli').setup({})
-- in your init.lua

-- Prevent double-loading
if vim.g.loaded_poor_cli then
  return
end
vim.g.loaded_poor_cli = 1

-- Check for Neovim 0.9+
if vim.fn.has("nvim-0.9") ~= 1 then
  vim.notify("poor-cli works best with Neovim 0.9+. Some features may not work.", vim.log.levels.WARN)
end

-- Warn if setup() is never called — check once on VimEnter
vim.api.nvim_create_autocmd("VimEnter", {
  once = true,
  callback = function()
    local ok, pc = pcall(require, "poor-cli")
    if ok and not pc._setup_complete then
      vim.notify(
        "[poor-cli] plugin loaded but setup() not called. Add: require('poor-cli').setup({}) to your config",
        vim.log.levels.WARN
      )
    end
  end,
})
