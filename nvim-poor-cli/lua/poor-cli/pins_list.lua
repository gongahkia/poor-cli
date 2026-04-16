-- poor-cli/pins_list.lua
-- CB2 follow-up: :PoorCLIPinsList — cross-session viewer/cleaner for the
-- turn pin overlay (.poor-cli/turn_pins.json). Migrated from a botright
-- vsplit to pickers.pick with per-row actions (unpin / clear all / jump
-- to chat). Buffer/render helpers stay intact so existing specs pass.

local M = {}

M.buf = nil
M.win = nil
M._rows = {}

local HEADER = {
    "# poor-cli Pinned Turns",
    "",
    "Keys:  x unpin row | X clear all | r refresh | <CR> jump to chat | q close",
    "",
}

local function sort_pins(pins)
    local out = {}
    for turn_id, state in pairs(pins or {}) do
        out[#out + 1] = { turnId = tostring(turn_id), state = tostring(state) }
    end
    table.sort(out, function(a, b)
        if a.state ~= b.state then return a.state < b.state end
        return a.turnId < b.turnId
    end)
    return out
end

M._sort_pins = sort_pins

local function render(pins)
    M._rows = {}
    local lines = {}
    for _, h in ipairs(HEADER) do lines[#lines + 1] = h end
    local items = sort_pins(pins)
    if #items == 0 then
        lines[#lines + 1] = "_no pinned turns_"
    else
        for _, it in ipairs(items) do
            lines[#lines + 1] = string.format("  %-5s  %s", it.state, it.turnId)
            M._rows[#lines] = it
        end
    end
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then return lines end
    vim.bo[M.buf].modifiable = true
    vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, lines)
    vim.bo[M.buf].modifiable = false
    return lines
end

M._render = render

local function notify(msg, level) require("poor-cli.notify").notify("[poor-cli] " .. msg, level) end

local function unpin(turn_id, on_done)
    local rpc = require("poor-cli.rpc")
    rpc.request("poor-cli/setTurnPin", { turnId = turn_id, state = vim.NIL }, function(_, err)
        vim.schedule(function()
            if err then
                notify("setTurnPin: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end
            local ok, tp = pcall(require, "poor-cli.turn_pin")
            if ok then pcall(tp.hydrate) end
            if on_done then on_done() end
        end)
    end)
end

function M.refresh()
    local rpc = require("poor-cli.rpc")
    rpc.request("poor-cli/listTurnPins", {}, function(result, err)
        vim.schedule(function()
            if err then
                notify("listTurnPins: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end
            render((result or {}).pins or {})
        end)
    end)
end

function M.clear_all()
    local rpc = require("poor-cli.rpc")
    rpc.request("poor-cli/listTurnPins", {}, function(result, _err)
        vim.schedule(function()
            local pins = (result or {}).pins or {}
            if vim.tbl_isempty(pins) then
                notify("no pins to clear", vim.log.levels.INFO)
                return
            end
            local choice = vim.fn.confirm(
                string.format("Clear all %d pinned turns?", vim.tbl_count(pins)),
                "&Yes\n&No", 2
            )
            if choice ~= 1 then return end
            local pending = vim.tbl_count(pins)
            for turn_id, _ in pairs(pins) do
                rpc.request("poor-cli/setTurnPin", { turnId = tostring(turn_id), state = vim.NIL }, function()
                    vim.schedule(function()
                        pending = pending - 1
                        if pending <= 0 then
                            local ok, tp = pcall(require, "poor-cli.turn_pin")
                            if ok then pcall(tp.hydrate) end
                            notify("cleared all pins", vim.log.levels.INFO)
                        end
                    end)
                end)
            end
        end)
    end)
end

local function jump_to_chat(turn_id)
    local chat = require("poor-cli.chat")
    if not chat.open then return end
    chat.open()
    for _, turn in ipairs(chat.turns or {}) do
        if tostring(turn.id) == turn_id and chat.win and vim.api.nvim_win_is_valid(chat.win) then
            pcall(vim.api.nvim_win_set_cursor, chat.win, { (turn.start_line or 0) + 1, 0 })
            return
        end
    end
    notify("turn not in current chat buffer", vim.log.levels.WARN)
end

function M.close() end -- no-op; kept for backward compatibility

function M.open()
    local rpc = require("poor-cli.rpc")
    rpc.request("poor-cli/listTurnPins", {}, function(result, err)
        vim.schedule(function()
            if err then notify("listTurnPins: " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local pins = (result or {}).pins or {}
            local rows = sort_pins(pins)
            if #rows == 0 then notify("no pinned turns", vim.log.levels.INFO); return end
            local items = {}
            for _, it in ipairs(rows) do
                items[#items + 1] = {
                    id = it.turnId,
                    label = string.format("%-5s  %s", it.state, it.turnId),
                    preview = "turnId: " .. it.turnId .. "\nstate:  " .. it.state,
                    data = it,
                }
            end
            local pickers = require("poor-cli.pickers")
            pickers.pick(items, {
                title = string.format("poor-cli pinned turns (%d)", #items),
                on_pick = function(it) jump_to_chat(it.turnId) end,
                keys = {
                    ["<C-x>"] = function(it) unpin(it.turnId) end,
                    ["<C-a>"] = function() M.clear_all() end,
                },
            })
        end)
    end)
end

M.unpin_current = function() end -- legacy no-op
M.jump_to_chat = function() end -- legacy no-op

function M.toggle() M.open() end

function M.setup()
    pcall(vim.api.nvim_del_user_command, "PoorCLIPinsList")
    vim.api.nvim_create_user_command("PoorCLIPinsList", function() M.toggle() end, {
        desc = "poor-cli: browse/unpin cross-session turn pins",
    })
end

return M
