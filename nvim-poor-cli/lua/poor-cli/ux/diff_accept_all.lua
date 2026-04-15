-- poor-cli/ux/diff_accept_all.lua
-- Adds accept-all-hunks-across-all-edits to the diff review panel,
-- mapped to `gAA`.

local M = {}

function M.accept_all()
    local dr = require("poor-cli.diff_review")
    local rpc = require("poor-cli.rpc")
    local edits = dr.edits or {}
    if #edits == 0 then
        require("poor-cli.notify").notify("[poor-cli] no pending edits", vim.log.levels.INFO)
        return 0
    end
    local pending = 0
    for _, edit in ipairs(edits) do
        for _, hunk in ipairs(edit.hunks or {}) do
            if (hunk.status or "pending") == "pending" then
                pending = pending + 1
                rpc.request("diff.accept", {
                    editId = edit.editId or edit.edit_id,
                    hunkId = hunk.hunkId or hunk.hunk_id,
                }, function(_, err)
                    vim.schedule(function()
                        if err then
                            require("poor-cli.notify").notify("[poor-cli] diff.accept: " .. rpc.format_error(err), vim.log.levels.ERROR)
                        end
                        if dr.refresh then dr.refresh() end
                    end)
                end)
            end
        end
    end
    return pending
end

function M.install()
    local dr = require("poor-cli.diff_review")
    local orig_open = dr.open
    dr.open = function(...)
        local ret = orig_open(...)
        if dr.buf and vim.api.nvim_buf_is_valid(dr.buf) then
            vim.keymap.set("n", "gAA", function() M.accept_all() end, {
                buffer = dr.buf, silent = true, nowait = true, desc = "accept all diff hunks",
            })
        end
        return ret
    end
    dr.accept_all = M.accept_all
end

return M
