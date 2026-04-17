-- poor-cli/integrations/neogit_bridge.lua
-- Phase-B bridge (Proposal B). Backend git.* tool handlers send RPC
-- notifications to this bridge when they want neogit's UI involved
-- (e.g. showing the commit buffer with a prefilled message). CLI-only
-- code paths bypass this module entirely; the tool still works even if
-- neogit is missing.

local M = {}

local function neogit_available()
    return pcall(require, "neogit")
end

-- Opens the neogit commit buffer and prefills the commit message.
-- Notification params: { message = string }
function M.open_commit(params)
    if not neogit_available() then return end
    params = params or {}
    local ok, neogit = pcall(require, "neogit")
    if not ok then return end
    pcall(function() neogit.open({ kind = "commit" }) end)
    if type(params.message) ~= "string" or params.message == "" then return end
    -- Prefill the commit-message buffer after neogit creates it. Poll briefly
    -- since neogit opens its buffer async.
    local attempts = 0
    local function try_fill()
        attempts = attempts + 1
        local buf = vim.fn.bufnr("NeogitCommitMessage")
        if buf > 0 and vim.api.nvim_buf_is_valid(buf) then
            local lines = vim.split(params.message, "\n", { plain = true })
            pcall(vim.api.nvim_buf_set_lines, buf, 0, 0, false, lines)
            return
        end
        if attempts < 20 then vim.defer_fn(try_fill, 50) end
    end
    vim.defer_fn(try_fill, 100)
end

function M.setup()
    local rpc = require("poor-cli.rpc")
    rpc.register_notification_handler("integration.neogit.openCommit", M.open_commit)
end

return M
