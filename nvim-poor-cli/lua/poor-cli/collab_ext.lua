local rpc = require("poor-cli.rpc")
local M = {}

function M.remove_member(params, callback) return rpc.request("poor-cli/removeHostMember", params or {}, callback) end
function M.set_member_role(params, callback) return rpc.request("poor-cli/setHostMemberRole", params or {}, callback) end
function M.set_lobby(params, callback) return rpc.request("poor-cli/setHostLobby", params or {}, callback) end
function M.approve_member(params, callback) return rpc.request("poor-cli/approveHostMember", params or {}, callback) end
function M.deny_member(params, callback) return rpc.request("poor-cli/denyHostMember", params or {}, callback) end
function M.rotate_token(params, callback) return rpc.request("poor-cli/rotateHostToken", params or {}, callback) end
function M.revoke_token(params, callback) return rpc.request("poor-cli/revokeHostToken", params or {}, callback) end
function M.handoff(params, callback) return rpc.request("poor-cli/handoffHostMember", params or {}, callback) end
function M.list_activity(params, callback) return rpc.request("poor-cli/listHostActivity", params or {}, callback) end
function M.set_hand_raised(params, callback) return rpc.request("poor-cli/setHandRaised", params or {}, callback) end
function M.next_driver(params, callback) return rpc.request("poor-cli/nextDriver", params or {}, callback) end
function M.pair_start(params, callback) return rpc.request("poor-cli/pairStart", params or {}, callback) end
function M.add_agenda_item(params, callback) return rpc.request("poor-cli/addAgendaItem", params or {}, callback) end
function M.list_agenda(params, callback) return rpc.request("poor-cli/listAgenda", params or {}, callback) end
function M.resolve_agenda_item(params, callback) return rpc.request("poor-cli/resolveAgendaItem", params or {}, callback) end

local function open_scratch(title, content, filetype)
    local buf = vim.api.nvim_create_buf(false, true)
    vim.bo[buf].buftype = "nofile"
    vim.bo[buf].bufhidden = "wipe"
    vim.bo[buf].swapfile = false
    vim.bo[buf].filetype = filetype or "markdown"
    vim.api.nvim_buf_set_name(buf, title)
    vim.api.nvim_buf_set_lines(buf, 0, -1, false, vim.split(content, "\n", { plain = true }))
    vim.cmd("botright split")
    vim.api.nvim_win_set_buf(0, buf)
    vim.api.nvim_buf_set_keymap(buf, "n", "q", ":close<CR>", { noremap = true, silent = true })
    return buf
end

local function simple_cb(label)
    return function(_, err) vim.schedule(function()
        if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
        else require("poor-cli.notify").notify("[poor-cli] " .. label .. " ok", vim.log.levels.INFO) end
    end) end
end

local function collab_ext_usage()
    return table.concat({
        "Usage: :PoorCLICollabExt <subcommand> [args]",
        "  remove <connection-id>",
        "  role <connection-id> <role>",
        "  lobby <on|off>",
        "  approve <connection-id>",
        "  deny <connection-id>",
        "  rotate-token",
        "  revoke-token",
        "  handoff <connection-id>",
        "  activity",
        "  hand <up|down>",
        "  next-driver",
        "  pair [preset]",
        "  agenda-add <text>",
        "  agenda-list",
        "  agenda-resolve <item-id>",
    }, "\n")
end

function M.setup()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCLICollabExt", function(opts)
        local args = vim.split(opts.args or "", " ", { trimempty = true })
        local sub = args[1] or ""
        if sub == "remove" and args[2] then
            M.remove_member({ connectionId = args[2] }, simple_cb("remove"))
        elseif sub == "role" and args[2] and args[3] then
            M.set_member_role({ connectionId = args[2], role = args[3] }, simple_cb("role"))
        elseif sub == "lobby" and args[2] then
            M.set_lobby({ enabled = args[2] == "on" }, simple_cb("lobby"))
        elseif sub == "approve" and args[2] then
            M.approve_member({ connectionId = args[2] }, simple_cb("approve"))
        elseif sub == "deny" and args[2] then
            M.deny_member({ connectionId = args[2] }, simple_cb("deny"))
        elseif sub == "rotate-token" then
            M.rotate_token({}, simple_cb("rotate-token"))
        elseif sub == "revoke-token" then
            M.revoke_token({}, simple_cb("revoke-token"))
        elseif sub == "handoff" and args[2] then
            M.handoff({ connectionId = args[2] }, simple_cb("handoff"))
        elseif sub == "activity" then
            M.list_activity({}, function(result, err) vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                open_scratch("[poor-cli collab activity]", vim.inspect(result), "lua")
            end) end)
        elseif sub == "hand" and args[2] then
            M.set_hand_raised({ raised = args[2] == "up" }, simple_cb("hand"))
        elseif sub == "next-driver" then
            M.next_driver({}, simple_cb("next-driver"))
        elseif sub == "pair" then
            local preset = args[2]
            M.pair_start(preset and { preset = preset } or {}, simple_cb("pair"))
        elseif sub == "agenda-add" and #args >= 2 then
            M.add_agenda_item({ text = table.concat(args, " ", 2) }, simple_cb("agenda-add"))
        elseif sub == "agenda-list" then
            M.list_agenda({}, function(result, err) vim.schedule(function()
                if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                local items = (result or {}).items or {}
                local lines = { "# agenda", "" }
                for _, item in ipairs(items) do
                    local resolved = item.resolved and " [resolved]" or ""
                    table.insert(lines, string.format("%s: %s%s", tostring(item.id or "?"), tostring(item.text or ""), resolved))
                end
                if #items == 0 then table.insert(lines, "no agenda items") end
                open_scratch("[poor-cli agenda]", table.concat(lines, "\n"), "markdown")
            end) end)
        elseif sub == "agenda-resolve" and args[2] then
            M.resolve_agenda_item({ itemId = args[2] }, simple_cb("agenda-resolve"))
        else
            require("poor-cli.notify").notify("[poor-cli]\n" .. collab_ext_usage(), vim.log.levels.INFO)
        end
    end, { nargs = "*", desc = "Extended collaboration commands" })
end

return M
