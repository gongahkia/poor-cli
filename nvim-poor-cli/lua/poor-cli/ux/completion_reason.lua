-- poor-cli/ux/completion_reason.lua
-- :PoorCLICompletionReason — reports why inline completion is (or isn't)
-- active in the current buffer. Also :PoorCLICompletionToggle to flip
-- completion on/off for the current filetype without editing config.

local M = {}

function M.report()
    local inline = require("poor-cli.inline")
    local bufnr = vim.api.nvim_get_current_buf()
    local enabled, reason = inline.is_enabled_for_buffer(bufnr, { manual = false })
    local ft = vim.bo[bufnr].filetype or ""
    local lines = {
        "# Inline completion status",
        string.format("buffer: %d (filetype=%s)", bufnr, ft),
        string.format("enabled: %s", tostring(enabled)),
        string.format("reason: %s", tostring(reason or "ok")),
    }
    require("poor-cli.notify").notify(table.concat(lines, "\n"), enabled and vim.log.levels.INFO or vim.log.levels.WARN)
    return enabled, reason
end

function M.toggle_filetype()
    local config = require("poor-cli.config")
    local ft = vim.bo[vim.api.nvim_get_current_buf()].filetype or ""
    if ft == "" then
        require("poor-cli.notify").notify("[poor-cli] no filetype on current buffer", vim.log.levels.WARN)
        return
    end
    local blocklist = config.config.completion_filetype_blocklist or {}
    local found_at
    for i, v in ipairs(blocklist) do if v == ft then found_at = i; break end end
    if found_at then
        table.remove(blocklist, found_at)
        require("poor-cli.notify").notify("[poor-cli] completion ENABLED for filetype " .. ft, vim.log.levels.INFO)
    else
        table.insert(blocklist, ft)
        require("poor-cli.notify").notify("[poor-cli] completion DISABLED for filetype " .. ft, vim.log.levels.INFO)
    end
    config.config.completion_filetype_blocklist = blocklist
end

-- install() intentionally removed: reachable via
-- `:PoorCLICompletion reason` and `:PoorCLICompletion toggle`.
-- M.report() and M.toggle_filetype() remain as the module API.
function M.install() end

return M
