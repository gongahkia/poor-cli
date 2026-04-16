local rpc = require("poor-cli.rpc")

local M = {
    buf = nil,
    win = nil,
    width = 32,
    members = {},
    rows = {},
    room = nil,
    presence = {},
    queue = {},
    ns = vim.api.nvim_create_namespace("poor-cli-users-panel"),
}

local function current_room_name()
    local state = rpc.get_multiplayer_state and rpc.get_multiplayer_state() or {}
    return tostring(state.room or "")
end

local function notify(message, level)
    local ok, mod = pcall(require, "poor-cli.notify")
    if ok then mod.notify("[poor-cli] " .. message, level or vim.log.levels.INFO) end
end

local function debug_enabled()
    local ok, config = pcall(require, "poor-cli.config")
    return ok and type(config.is_debug) == "function" and config.is_debug()
end

local function display_width(text)
    return vim.fn.strdisplaywidth(tostring(text or ""))
end

local function fit(text, width)
    text = tostring(text or "")
    if display_width(text) <= width then return text end
    local out = ""
    local used = 0
    for _, code in utf8.codes(text) do
        local ch = utf8.char(code)
        local w = display_width(ch)
        if used + w >= width then return out .. "…" end
        out = out .. ch
        used = used + w
    end
    return out
end

local function pad(text, width)
    text = fit(text, width)
    return text .. string.rep(" ", math.max(0, width - display_width(text)))
end

local function id_of(member)
    return tostring(member.connectionId or member.connection_id or member.id or "")
end

local function name_of(member)
    local name = member.displayName or member.display_name or member.clientName or member.client_name or member.name or id_of(member)
    name = tostring(name or "")
    return name ~= "" and name or "?"
end

local function role_of(member)
    return tostring(member.role or "viewer")
end

local function approval_of(member)
    local state = member.approvalState or member.approval_state
    if state and state ~= "" then return tostring(state) end
    if member.approved == true then return "approved" end
    if member.approved == false then return "pending" end
    return ""
end

local function room_from(result)
    if type(result) ~= "table" then return {} end
    if type(result.room) == "table" then return result.room end
    local rooms = type(result.rooms) == "table" and result.rooms or {}
    local wanted = current_room_name()
    for _, room in ipairs(rooms) do
        if type(room) == "table" and tostring(room.name or "") == wanted then return room end
    end
    return rooms[1] or {}
end

local function is_open()
    return M.win and vim.api.nvim_win_is_valid(M.win)
end

local function queue_snapshot(result)
    if type(result) ~= "table" then return {} end
    if type(result.snapshot) == "table" then return result.snapshot end
    if type(result.queue) == "table" then return result.queue end
    if type(result.items) == "table" then return result.items end
    return {}
end

local function merge(host_members, presence, queue)
    local room = room_from(host_members)
    local members = type(room.members) == "table" and room.members or {}
    local by_id, order = {}, {}
    for _, member in ipairs(members) do
        if type(member) == "table" then
            local cid = id_of(member)
            if cid ~= "" then
                by_id[cid] = vim.deepcopy(member)
                table.insert(order, cid)
            end
        end
    end
    if type(presence) == "table" then
        if type(presence.presence) == "table" then
            for cid, typing in pairs(presence.presence) do
                cid = tostring(cid)
                by_id[cid] = by_id[cid] or { connectionId = cid }
                by_id[cid].typing = typing == true
                if not vim.tbl_contains(order, cid) then table.insert(order, cid) end
            end
        end
        if type(presence.members) == "table" then
            for _, item in ipairs(presence.members) do
                if type(item) == "table" then
                    local cid = id_of(item)
                    if cid ~= "" then
                        by_id[cid] = vim.tbl_extend("force", by_id[cid] or { connectionId = cid }, item)
                        if not vim.tbl_contains(order, cid) then table.insert(order, cid) end
                    end
                end
            end
        end
    end
    for _, item in ipairs(queue_snapshot(queue)) do
        if type(item) == "table" then
            local cid = id_of(item)
            if cid ~= "" then
                by_id[cid] = by_id[cid] or { connectionId = cid }
                by_id[cid].queuePosition = tonumber(item.position or item.queuePosition or item.queue_position) or 0
                if not vim.tbl_contains(order, cid) then table.insert(order, cid) end
            end
        end
    end
    local out = {}
    for _, cid in ipairs(order) do table.insert(out, by_id[cid]) end
    return room, out
end

local function apply_queue(snapshot)
    M.queue = { snapshot = snapshot or {} }
    local by_id = {}
    for _, item in ipairs(M.queue.snapshot) do
        if type(item) == "table" then
            local cid = id_of(item)
            if cid ~= "" then by_id[cid] = tonumber(item.position or item.queuePosition or item.queue_position) or 0 end
        end
    end
    for _, member in ipairs(M.members) do
        local cid = id_of(member)
        if by_id[cid] then member.queuePosition = by_id[cid] end
    end
end

local function role_prefix(role)
    if role == "prompter" then return ">" end
    if role == "viewer" then return "·" end
    return " "
end

local function driver_label(member, room)
    local cid = id_of(member)
    local active = tostring(room.activeConnectionId or room.active_connection_id or "") == cid
        or member.active == true
        or tostring(member.uiRole or member.ui_role or "") == "driver"
    if not active then return "" end
    local prompters = 0
    for _, item in ipairs(M.members) do
        if role_of(item) == "prompter" then prompters = prompters + 1 end
    end
    if prompters > 1 or room.queueMode == "roundRobin" or room.multiPrompter == true then return "→ focused" end
    return "← driver"
end

local function status_line(member)
    if member.typing == true then return "● typing…" end
    local queue_position = tonumber(member.queuePosition or member.queue_position) or 0
    if queue_position > 0 then return "#" .. queue_position .. " in queue" end
    if approval_of(member) == "pending" then return "[a]approve [d]deny" end
    if debug_enabled() then return "◌ idle" end
    return ""
end

function M.render_lines(members, room)
    members = members or M.members
    room = room or M.room or {}
    local lines = { "users (" .. tostring(#members) .. ")", string.rep("─", M.width) }
    local rows = {}
    if #members == 0 then
        table.insert(lines, "(no members)")
        return lines, rows
    end
    for _, member in ipairs(members) do
        local cid = id_of(member)
        local role = role_of(member)
        local top_status = driver_label(member, room)
        if top_status == "" then top_status = approval_of(member) end
        local first = pad(role_prefix(role) .. name_of(member), 13) .. " " .. pad(role, 8) .. " " .. top_status
        table.insert(lines, fit(first, M.width))
        rows[#lines] = cid
        local second = status_line(member)
        table.insert(lines, fit(string.rep(" ", 14) .. second, M.width))
        rows[#lines] = cid
    end
    return lines, rows
end

local function set_lines(lines, rows)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then return end
    M.rows = rows or {}
    vim.bo[M.buf].modifiable = true
    vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, lines)
    vim.api.nvim_buf_clear_namespace(M.buf, M.ns, 0, -1)
    for line, cid in pairs(M.rows) do
        local member
        for _, item in ipairs(M.members) do
            if id_of(item) == cid then member = item; break end
        end
        if member and member.typing == true then
            pcall(vim.api.nvim_buf_add_highlight, M.buf, M.ns, "WarningMsg", line - 1, 14, -1)
        else
            pcall(vim.api.nvim_buf_add_highlight, M.buf, M.ns, "Comment", line - 1, 0, 1)
        end
    end
    vim.bo[M.buf].modifiable = false
end

function M.render()
    local lines, rows = M.render_lines()
    set_lines(lines, rows)
end

local function refresh_params()
    local room = current_room_name()
    return room ~= "" and { room = room } or {}
end

function M.refresh()
    if not is_open() then return end
    M._request_seq = (M._request_seq or 0) + 1
    local seq = M._request_seq
    local pending = 3
    local data = {}
    local function done(key, result)
        if seq ~= M._request_seq then return end
        data[key] = result or {}
        pending = pending - 1
        if pending > 0 then return end
        M.room, M.members = merge(data.host, data.presence, data.queue)
        M.presence = data.presence or {}
        M.queue = data.queue or {}
        M.render()
    end
    local params = refresh_params()
    rpc.request("poor-cli/listHostMembers", params, function(result, err)
        vim.schedule(function()
            if err then notify("users failed: " .. rpc.format_error(err), vim.log.levels.ERROR) end
            done("host", result)
        end)
    end)
    rpc.request("poor-cli/listPresence", params, function(result)
        vim.schedule(function() done("presence", result) end)
    end)
    rpc.request("poor-cli/listRoomQueue", params, function(result)
        vim.schedule(function() done("queue", result) end)
    end)
end

local function current_member()
    if not M.buf or vim.api.nvim_get_current_buf() ~= M.buf then return nil end
    local line = vim.api.nvim_win_get_cursor(0)[1]
    local cid = M.rows[line]
    if not cid then return nil end
    for _, member in ipairs(M.members) do
        if id_of(member) == cid then return member end
    end
    return nil
end

local function run_action(method, member, extra)
    member = member or current_member()
    if not member then return end
    local cid = id_of(member)
    if cid == "" then return end
    local params = vim.tbl_extend("force", refresh_params(), { connectionId = cid }, extra or {})
    rpc.request(method, params, function(_, err)
        vim.schedule(function()
            if err then
                notify(rpc.format_error(err), vim.log.levels.ERROR)
            else
                M.refresh()
            end
        end)
    end)
end

function M.approve(id)
    run_action("poor-cli/approveHostMember", id and { connectionId = id } or nil)
end

function M.deny(id)
    run_action("poor-cli/denyHostMember", id and { connectionId = id } or nil)
end

function M.kick(id)
    run_action("poor-cli/removeHostMember", id and { connectionId = id } or nil)
end

function M.pass(id)
    run_action("poor-cli/handoffHostMember", id and { connectionId = id } or nil)
end

function M.role(id, role)
    local member = id and { connectionId = id } or current_member()
    if not member then return end
    if role and role ~= "" then
        run_action("poor-cli/setHostMemberRole", member, { role = role })
        return
    end
    vim.ui.input({ prompt = "role (viewer|prompter): " }, function(value)
        value = tostring(value or ""):gsub("^%s+", ""):gsub("%s+$", "")
        if value ~= "viewer" and value ~= "prompter" then return end
        run_action("poor-cli/setHostMemberRole", member, { role = value })
    end)
end

function M.copy_invite()
    local member = current_member()
    if not member then return end
    local role = role_of(member) == "viewer" and "viewer" or "prompter"
    local key = role == "viewer" and "viewerInviteLink" or "prompterInviteLink"
    local fallback = role == "viewer" and "viewerInviteCode" or "prompterInviteCode"
    local invite = tostring((M.room or {})[key] or (M.room or {})[fallback] or (M.room or {}).inviteLink or "")
    if invite == "" then notify("no invite link", vim.log.levels.WARN); return end
    local ok = pcall(vim.fn.setreg, "+", invite)
    if not ok then vim.fn.setreg('"', invite) end
    notify("invite copied", vim.log.levels.INFO)
end

function M.close()
    if is_open() then vim.api.nvim_win_close(M.win, true) end
    M.win = nil
end

local function ensure_buf()
    if M.buf and vim.api.nvim_buf_is_valid(M.buf) then return end
    M.buf = vim.api.nvim_create_buf(false, true)
    vim.bo[M.buf].buftype = "nofile"
    vim.bo[M.buf].bufhidden = "hide"
    vim.bo[M.buf].swapfile = false
    vim.bo[M.buf].filetype = "poorcliusers"
    vim.api.nvim_buf_set_name(M.buf, "[poor-cli users]")
end

function M.open()
    ensure_buf()
    if is_open() then
        vim.api.nvim_set_current_win(M.win)
        M.refresh()
        return M.buf
    end
    local float_win = require("poor-cli.float_win")
    M.win = float_win.open(M.buf, {
        width = M.width,
        height = math.max(20, vim.o.lines - 4),
        position = "right",
        title = " poor-cli users ",
        close_keys = {},
        wrap = false,
        signcolumn = "no",
    })
    vim.keymap.set("n", "q", M.close, { buffer = M.buf, nowait = true, desc = "Close poor-cli users" })
    vim.keymap.set("n", "<Esc>", M.close, { buffer = M.buf, nowait = true, desc = "Close poor-cli users" })
    vim.keymap.set("n", "R", M.refresh, { buffer = M.buf, nowait = true, desc = "Refresh poor-cli users" })
    vim.keymap.set("n", "a", function() M.approve() end, { buffer = M.buf, nowait = true, desc = "Approve user" })
    vim.keymap.set("n", "d", function() M.deny() end, { buffer = M.buf, nowait = true, desc = "Deny user" })
    vim.keymap.set("n", "x", function() M.kick() end, { buffer = M.buf, nowait = true, desc = "Kick user" })
    vim.keymap.set("n", "r", function() M.role() end, { buffer = M.buf, nowait = true, desc = "Set user role" })
    vim.keymap.set("n", "p", function() M.pass() end, { buffer = M.buf, nowait = true, desc = "Pass driver" })
    vim.keymap.set("n", "c", M.copy_invite, { buffer = M.buf, nowait = true, desc = "Copy invite" })
    M.refresh()
    return M.buf
end

function M.toggle()
    if is_open() then M.close() else M.open() end
end

function M.on_member_typing(data)
    data = data or {}
    local cid = tostring(data.connection_id or data.connectionId or "")
    if cid == "" then return end
    for _, member in ipairs(M.members) do
        if id_of(member) == cid then
            member.typing = data.typing == true
            if data.displayName or data.display_name then member.displayName = data.displayName or data.display_name end
            break
        end
    end
    if is_open() then M.render() end
end

function M.on_queue_updated(data)
    data = data or {}
    apply_queue(queue_snapshot(data))
    if is_open() then M.render() end
end

function M.command(args)
    local parts = vim.split(args or "", " ", { trimempty = true })
    local sub = parts[1] or ""
    if sub == "" then M.toggle()
    elseif sub == "approve" and parts[2] then M.approve(parts[2])
    elseif sub == "deny" and parts[2] then M.deny(parts[2])
    elseif sub == "kick" and parts[2] then M.kick(parts[2])
    elseif sub == "pass" and parts[2] then M.pass(parts[2])
    elseif sub == "role" and parts[2] and parts[3] then M.role(parts[2], parts[3])
    else notify("Usage: :PoorCLIUsers [approve|deny|kick|pass <id>|role <id> <viewer|prompter>]", vim.log.levels.WARN) end
end

function M.setup()
    local group = vim.api.nvim_create_augroup("PoorCLIUsersPanel", { clear = true })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLIMemberTyping",
        callback = function(ev) M.on_member_typing(ev.data or {}) end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = "PoorCLIQueueUpdated",
        callback = function(ev) M.on_queue_updated(ev.data or {}) end,
    })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = { "PoorCLICollabMemberJoined", "PoorCLICollabMemberLeft" },
        callback = function() if is_open() then M.refresh() end end,
    })
    vim.api.nvim_create_autocmd("BufWinEnter", {
        group = group,
        callback = function(ev)
            if M.buf and ev.buf == M.buf and is_open() then M.refresh() end
        end,
    })
    pcall(vim.api.nvim_del_user_command, "PoorCLIUsers")
    vim.api.nvim_create_user_command("PoorCLIUsers", function(opts) M.command(opts.args) end, {
        nargs = "*",
        complete = function(_, line)
            local parts = vim.split(line or "", " ", { trimempty = true })
            if #parts <= 1 then return { "approve", "deny", "kick", "role", "pass" } end
            if parts[2] == "role" and #parts >= 4 then return { "viewer", "prompter" } end
            return {}
        end,
        desc = "Toggle poor-cli users panel",
    })
    pcall(vim.keymap.del, "n", "<leader>pu")
    vim.keymap.set("n", "<leader>pu", M.toggle, { desc = "Toggle poor-cli users" })
end

return M
