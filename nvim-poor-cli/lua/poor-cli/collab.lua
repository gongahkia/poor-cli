-- poor-cli/collab.lua
-- Split-pane panel for live collab session state (rooms, members, events)

local rpc = require("poor-cli.rpc")
local M = {}

M.buf = nil
M.win = nil
M.events = {}
M.max_events = 50
M.host_members_cache = nil
M._fetch_in_flight = false

local function now_str()
    return os.date("%H:%M:%S")
end

local function push_event(text)
    table.insert(M.events, 1, string.format("[%s] %s", now_str(), text))
    while #M.events > M.max_events do
        table.remove(M.events)
    end
end

local function render_state(lines)
    local state = rpc.get_multiplayer_state() or {}
    table.insert(lines, "# poor-cli Collab")
    table.insert(lines, "")
    table.insert(lines, "Press q to close. `:PoorCLICollab ...` for actions.")
    table.insert(lines, "")
    table.insert(lines, "## 🟢 Session")
    table.insert(lines, "")
    local enabled = state.enabled and "on" or "off"
    table.insert(lines, string.format("- enabled:        %s", enabled))
    table.insert(lines, string.format("- room:           %s", state.room ~= "" and state.room or "(none)"))
    table.insert(lines, string.format("- role:           %s", state.role ~= "" and state.role or "(none)"))
    table.insert(lines, string.format("- display name:   %s", state.display_name ~= "" and state.display_name or "(none)"))
    table.insert(lines, string.format("- approval:       %s", state.approval_state ~= "" and state.approval_state or "(n/a)"))
    table.insert(lines, string.format("- hand raised:    %s", state.hand_raised and "yes" or "no"))
    table.insert(lines, string.format("- queue position: %d", state.queue_position or 0))
    table.insert(lines, string.format("- lobby:          %s", state.lobby_enabled and "enabled" or "disabled"))
    table.insert(lines, string.format("- preset:         %s", state.preset ~= "" and state.preset or "(none)"))
    table.insert(lines, string.format("- connection id:  %s", state.local_connection_id ~= "" and state.local_connection_id or "(none)"))
    table.insert(lines, "")
    table.insert(lines, "## 👥 Members")
    table.insert(lines, "")
    -- host-side member list from listHostMembers; falls back to cached state.members
    local rendered = false
    if M.host_members_cache and type(M.host_members_cache.rooms) == "table" then
        for _, room in ipairs(M.host_members_cache.rooms) do
            local room_name = room.name or "?"
            local members = room.members or {}
            if #members > 0 then
                table.insert(lines, string.format("### room: %s (%d)", room_name, #members))
                for _, m in ipairs(members) do
                    local name = m.displayName or m.display_name or m.name or "?"
                    local role = m.role or "?"
                    local cid  = m.connectionId or m.connection_id or ""
                    table.insert(lines, string.format("- %s [%s] %s", name, role, cid))
                end
                rendered = true
            end
        end
    end
    if not rendered then
        local members = state.members or {}
        if type(members) == "table" and #members > 0 then
            for _, m in ipairs(members) do
                local name = m.displayName or m.display_name or m.name or "?"
                local role = m.role or "?"
                local cid  = m.connectionId or m.connection_id or ""
                table.insert(lines, string.format("- %s [%s] %s", name, role, cid))
            end
        else
            local count = state.member_count or 0
            if count > 0 then
                table.insert(lines, string.format("- (%d member(s); run `:PoorCLICollab members` for details)", count))
            else
                table.insert(lines, "(no members)")
            end
        end
    end
    table.insert(lines, "")
    table.insert(lines, "## 📜 Events")
    table.insert(lines, "")
    if #M.events == 0 then
        table.insert(lines, "(none yet)")
    else
        for _, ev in ipairs(M.events) do
            table.insert(lines, ev)
        end
    end
end

local function fetch_host_members(on_done)
    if M._fetch_in_flight then return end
    M._fetch_in_flight = true
    rpc.request("poor-cli/listHostMembers", {}, function(result, err)
        vim.schedule(function()
            M._fetch_in_flight = false
            if err then
                if on_done then on_done() end
                return
            end
            M.host_members_cache = result or {}
            if on_done then on_done() end
        end)
    end)
end

function M.refresh()
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        return
    end
    local function render_now()
        local lines = {}
        render_state(lines)
        vim.bo[M.buf].modifiable = true
        vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, lines)
        vim.bo[M.buf].modifiable = false
    end
    render_now()
    -- try to fetch live host member list in background; re-render once we have it
    fetch_host_members(render_now)
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

    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then
        M.buf = vim.api.nvim_create_buf(false, true)
        vim.bo[M.buf].buftype = "nofile"
        vim.bo[M.buf].bufhidden = "hide"
        vim.bo[M.buf].swapfile = false
        vim.bo[M.buf].filetype = "markdown"
        vim.api.nvim_buf_set_name(M.buf, "[poor-cli collab]")
    end

    local width = 60
    vim.cmd("botright " .. width .. "vsplit")
    M.win = vim.api.nvim_get_current_win()
    vim.api.nvim_win_set_buf(M.win, M.buf)
    vim.wo[M.win].wrap = true
    vim.wo[M.win].number = false
    vim.wo[M.win].relativenumber = false
    vim.wo[M.win].signcolumn = "no"

    vim.keymap.set("n", "q", M.close, { buffer = M.buf, desc = "Close collab panel", nowait = true })
    vim.keymap.set("n", "r", M.refresh, { buffer = M.buf, desc = "Refresh collab panel", nowait = true })
    M.refresh()
end

function M.toggle()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        M.close()
    else
        M.open()
    end
end

function M.setup()
    local group = vim.api.nvim_create_augroup("PoorCLICollabPanel", { clear = true })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLIRoomEvent",
        callback = function(ev)
            local data = ev.data or {}
            local t = data.event_type or "event"
            local actor = data.actor or ""
            local tail = actor ~= "" and (" (" .. actor .. ")") or ""
            push_event(t .. tail)
            M.refresh()
        end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLIPeerMessage",
        callback = function(ev)
            local data = ev.data or {}
            push_event(string.format("💬 %s: %s", data.sender or "?", data.text or ""))
            M.refresh()
        end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLIStatusChanged",
        callback = function()
            M.refresh()
        end,
    })

    pcall(vim.api.nvim_del_user_command, "PoorCLICollabPanel")
    vim.api.nvim_create_user_command("PoorCLICollabPanel", function()
        M.toggle()
    end, { desc = "Toggle poor-cli collab panel" })
end

return M
