local config = require("poor-cli.config")
local rpc = require("poor-cli.rpc")

local M = {
    tabs = {},
    events = {},
    max_events = 80,
}

local function tab_state()
    local tab = vim.api.nvim_get_current_tabpage()
    M.tabs[tab] = M.tabs[tab] or { actions = {}, snapshot = nil, invite = "" }
    return M.tabs[tab]
end

local function multiplayer_enabled()
    local cfg = config.get("multiplayer") or {}
    local state = rpc.get_multiplayer_state() or {}
    return (type(cfg) == "table" and cfg.enabled == true) or state.enabled == true
end

local function add_event(data)
    if type(data) ~= "table" then return end
    local text = string.format(
        "[%s] %s %s",
        os.date("%H:%M:%S"),
        tostring(data.event_type or data.eventType or "event"),
        tostring(data.actor or "")
    )
    table.insert(M.events, 1, text:gsub("%s+$", ""))
    while #M.events > M.max_events do table.remove(M.events) end
end

local function normalize_rooms(snapshot)
    if type(snapshot) ~= "table" then return {} end
    if type(snapshot.rooms) == "table" then return snapshot.rooms end
    local room = snapshot.room
    if type(room) == "table" then return { room } end
    return {}
end

local function current_room_name()
    local state = rpc.get_multiplayer_state() or {}
    return state.room or ""
end

local function pick_room(snapshot)
    local rooms = normalize_rooms(snapshot)
    local wanted = current_room_name()
    for _, room in ipairs(rooms) do
        if type(room) == "table" and tostring(room.name or "") == wanted then return room end
    end
    return rooms[1] or {}
end

local function invite_from_room(room)
    if type(room) ~= "table" then return "" end
    return tostring(room.inviteLink or room.prompterInviteLink or room.prompterInviteCode or room.viewerInviteLink or room.viewerInviteCode or "")
end

local function role_label(member)
    local role = tostring(member.role or "viewer")
    if member.owner == true then return "owner" end
    return role
end

local function display_name(member)
    return tostring(member.displayName or member.display_name or member.clientName or member.name or member.connectionId or member.connection_id or "?")
end

local function connection_id(member)
    return tostring(member.connectionId or member.connection_id or "")
end

function M.render_lines(snapshot)
    local state = rpc.get_multiplayer_state() or {}
    local room = pick_room(snapshot)
    local room_name = tostring(room.name or state.room or "(none)")
    local invite = invite_from_room(room)
    local members = type(room.members) == "table" and room.members or state.members or {}
    local active_id = tostring(room.activeConnectionId or state.active_connection_id or "")
    local lines = {
        "# poor-cli multiplayer room",
        "",
        "room: " .. room_name,
        "invite: " .. (invite ~= "" and invite or "(none)"),
        "",
        "[Copy invite]  [Pass driver]  keys: yi copy, p pass, r refresh, s chat, q close",
        "",
        "## members",
        "host [owner]",
    }
    local hands = {}
    if type(members) == "table" and #members > 0 then
        for _, member in ipairs(members) do
            if type(member) == "table" then
                local cid = connection_id(member)
                local driver = cid ~= "" and cid == active_id or tostring(member.uiRole or member.ui_role or "") == "driver" or member.role == "prompter"
                local marker = driver and " <- driver" or ""
                local hand = member.handRaised == true or member.hand_raised == true
                local queue = tonumber(member.queuePosition or member.queue_position) or 0
                if hand or queue > 0 then table.insert(hands, member) end
                table.insert(lines, string.format("%s [%s]%s %s", display_name(member), role_label(member), marker, cid))
            end
        end
    else
        table.insert(lines, "(no remote members)")
    end
    table.insert(lines, "")
    table.insert(lines, "## hands raised")
    if #hands == 0 then
        table.insert(lines, "(none)")
    else
        table.sort(hands, function(a, b)
            return (tonumber(a.queuePosition or a.queue_position) or 9999) < (tonumber(b.queuePosition or b.queue_position) or 9999)
        end)
        for _, member in ipairs(hands) do
            table.insert(lines, string.format("[Grant] %s %s", display_name(member), connection_id(member)))
        end
    end
    table.insert(lines, "")
    table.insert(lines, "## events")
    if #M.events == 0 then
        table.insert(lines, "(none)")
    else
        for _, event in ipairs(M.events) do table.insert(lines, event) end
    end
    return lines
end

local function set_lines(state, lines)
    vim.bo[state.buf].modifiable = true
    vim.api.nvim_buf_set_lines(state.buf, 0, -1, false, lines)
    vim.bo[state.buf].modifiable = false
end

local function request_room(callback)
    rpc.request("collab.room", { room = current_room_name() }, function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] room failed: " .. rpc.format_error(err), vim.log.levels.ERROR)
                callback(nil)
                return
            end
            callback(result or {})
        end)
    end)
end

function M.refresh()
    local state = tab_state()
    if not state.buf or not vim.api.nvim_buf_is_valid(state.buf) then return end
    request_room(function(snapshot)
        if not snapshot then return end
        state.snapshot = snapshot
        state.invite = invite_from_room(pick_room(snapshot))
        set_lines(state, M.render_lines(snapshot))
    end)
end

function M.copy_invite()
    local state = tab_state()
    if state.invite == "" then
        require("poor-cli.notify").notify("[poor-cli] no invite link", vim.log.levels.WARN)
        return
    end
    local ok = pcall(vim.fn.setreg, "+", state.invite)
    if not ok then vim.fn.setreg('"', state.invite) end
    require("poor-cli.notify").notify(ok and "[poor-cli] invite copied" or "[poor-cli] invite copied to unnamed register", vim.log.levels.INFO)
end

function M.pass_driver(target)
    local params = { room = current_room_name() }
    if target and target ~= "" then params.connectionId = target end
    rpc.request("collab.room/pass_driver", params, function(_, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] pass driver failed: " .. rpc.format_error(err), vim.log.levels.ERROR)
            else
                require("poor-cli.notify").notify("[poor-cli] driver passed", vim.log.levels.INFO)
                M.refresh()
            end
        end)
    end)
end

function M.chat()
    vim.ui.input({ prompt = "room chat: " }, function(text)
        text = tostring(text or ""):gsub("^%s+", ""):gsub("%s+$", "")
        if text == "" then return end
        rpc.peer_message(text, function(_, err)
            vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] chat failed: " .. rpc.format_error(err), vim.log.levels.ERROR) end
            end)
        end)
    end)
end

function M.open()
    if not multiplayer_enabled() then
        require("poor-cli.notify").notify(
            "[poor-cli] :PoorCLIRoom / :PoorCLICollab require multiplayer to be enabled. "
            .. "Add to your setup:\n\n"
            .. "  require('poor-cli').setup({\n"
            .. "    multiplayer = { enabled = true },\n"
            .. "  })\n\n"
            .. "Then restart nvim or :PoorCLIRestart. "
            .. "(This is the default on new installs; you're seeing this because enabled is explicitly false.)",
            vim.log.levels.WARN,
            { title = "poor-cli multiplayer", timeout = 10000 }
        )
        return nil
    end
    local state = tab_state()
    if not state.buf or not vim.api.nvim_buf_is_valid(state.buf) then
        state.buf = vim.api.nvim_create_buf(false, true)
        vim.bo[state.buf].buftype = "nofile"
        vim.bo[state.buf].bufhidden = "hide"
        vim.bo[state.buf].swapfile = false
        vim.bo[state.buf].filetype = "markdown"
        vim.api.nvim_buf_set_name(state.buf, "[poor-cli multiplayer room]")
    end
    state.win = vim.api.nvim_get_current_win()
    vim.api.nvim_win_set_buf(state.win, state.buf)
    vim.wo[state.win].wrap = false
    vim.wo[state.win].number = false
    vim.wo[state.win].relativenumber = false
    vim.keymap.set("n", "q", function() pcall(vim.cmd, "bdelete") end, { buffer = state.buf, nowait = true, desc = "Close multiplayer room" })
    vim.keymap.set("n", "r", M.refresh, { buffer = state.buf, nowait = true, desc = "Refresh multiplayer room" })
    vim.keymap.set("n", "yi", M.copy_invite, { buffer = state.buf, nowait = true, desc = "Copy invite" })
    vim.keymap.set("n", "p", function() M.pass_driver("") end, { buffer = state.buf, nowait = true, desc = "Pass driver" })
    vim.keymap.set("n", "s", M.chat, { buffer = state.buf, nowait = true, desc = "Send room chat" })
    M.refresh()
    return state.buf
end

function M.setup()
    local group = vim.api.nvim_create_augroup("PoorCLIMultiplayerRoom", { clear = true })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLIRoomEvent",
        callback = function(ev)
            add_event(ev.data or {})
            M.refresh()
        end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLIMemberRoleUpdated",
        callback = function()
            M.refresh()
        end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLIPeerMessage",
        callback = function(ev)
            local data = ev.data or {}
            add_event({ event_type = "chat", actor = tostring(data.sender or "") })
            M.refresh()
        end,
    })
end

return M
