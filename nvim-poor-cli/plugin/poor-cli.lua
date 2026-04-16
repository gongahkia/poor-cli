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
  require("poor-cli.notify").notify("poor-cli works best with Neovim 0.9+. Some features may not work.", vim.log.levels.WARN)
end

-- Warn if setup() is never called — check once on VimEnter.
-- If setup() was called but errored out (e.g. missing hard deps), stay
-- silent: the error has already been surfaced by setup() itself; a second
-- "setup not called" nag on top would be redundant and misleading.
vim.api.nvim_create_autocmd("VimEnter", {
  once = true,
  callback = function()
    local ok, pc = pcall(require, "poor-cli")
    if ok and not pc._setup_complete and not pc._setup_attempted then
      require("poor-cli.notify").notify(
        "[poor-cli] plugin loaded but setup() not called. Add: require('poor-cli').setup({}) to your config",
        vim.log.levels.WARN
      )
    end
  end,
})
