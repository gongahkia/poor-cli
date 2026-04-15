-- poor-cli/ux/collaborators.lua
-- :PoorCLICollaboratorsPanel toggle — a lightweight persistent view of
-- multiplayer room members. Uses poor-cli/listHostMembers.

local M = {}

M.buf = nil
M.win = nil

local function render_lines(members, state)
    local lines = {
        "# poor-cli Collaborators",
        string.format("room: %s  role: %s  enabled: %s",
            tostring(state.room or "?"),
            tostring(state.role or "?"),
            tostring(state.enabled or false)),
        "q close | r refresh",
        "",
    }
    if type(members) ~= "table" or vim.tbl_isempty(members) then
        table.insert(lines, "_no members_")
        return lines
    end
    for _, m in ipairs(members) do
        local name = m.displayName or m.name or m.userId or "?"
        local role = m.role or m.hostRole or "member"
        local presence = m.presence or m.status or ""
        local mark = presence == "active" and "●" or presence == "idle" and "○" or "·"
        table.insert(lines, string.format("  %s %s  [%s]  %s", mark, name, role, presence))
    end
    return lines
end

function M.refresh()
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then return end
    local rpc = require("poor-cli.rpc")
    rpc.request("poor-cli/listHostMembers", {}, function(result, err)
        vim.schedule(function()
            local members = {}
            if not err and type(result) == "table" then
                members = result.members or result or {}
            end
            local state = rpc.multiplayer_state or {}
            local lines = render_lines(members, state)
            vim.bo[M.buf].modifiable = true
            vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, lines)
            vim.bo[M.buf].modifiable = false
        end)
    end)
end

function M.close()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_win_close(M.win, true)
    end
    M.win = nil
end

function M.open()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_set_current_win(M.win)
        M.refresh()
        return
    end
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then
        M.buf = vim.api.nvim_create_buf(false, true)
        vim.bo[M.buf].buftype = "nofile"
        vim.bo[M.buf].bufhidden = "hide"
        vim.bo[M.buf].swapfile = false
        vim.bo[M.buf].filetype = "markdown"
        vim.api.nvim_buf_set_name(M.buf, "[poor-cli collaborators]")
    end
    vim.cmd("botright 50vsplit")
    M.win = vim.api.nvim_get_current_win()
    vim.api.nvim_win_set_buf(M.win, M.buf)
    vim.wo[M.win].wrap = false
    vim.wo[M.win].number = false
    vim.wo[M.win].relativenumber = false
    vim.keymap.set("n", "q", M.close, { buffer = M.buf, nowait = true, desc = "close" })
    vim.keymap.set("n", "r", M.refresh, { buffer = M.buf, nowait = true, desc = "refresh" })
    M.refresh()
end

function M.toggle()
    if M.win and vim.api.nvim_win_is_valid(M.win) then M.close() else M.open() end
end

function M.install()
    pcall(vim.api.nvim_del_user_command, "PoorCLICollaboratorsPanel")
    vim.api.nvim_create_user_command("PoorCLICollaboratorsPanel", function() M.toggle() end, { desc = "Toggle collaborators panel" })

    -- auto-refresh on presence events
    local group = vim.api.nvim_create_augroup("poor-cli-ux-collaborators", { clear = true })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = { "PoorCLIHostMembersChanged", "PoorCLIRoomChanged", "PoorCLIPresenceChanged" },
        callback = function()
            if M.win and vim.api.nvim_win_is_valid(M.win) then vim.schedule(M.refresh) end
        end,
    })
end

M._render_lines = render_lines -- test hook

return M
