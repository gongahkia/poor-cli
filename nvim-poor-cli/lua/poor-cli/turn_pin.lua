-- poor-cli/turn_pin.lua
-- CB2-UI: soft/hard pin toggle for individual turns in the chat buffer.
-- Persists via the backend poor-cli/setTurnPin RPC; backend merges into
-- history_pruning metadata so pruning respects the runtime toggles.

local M = {}

M.pin_ns = vim.api.nvim_create_namespace("poor-cli-chat-pin")
M._pins = {} -- turn_id -> "soft" | "hard"

local CYCLE = { [false] = "soft", ["soft"] = "hard", ["hard"] = false }

local function badge_for(state)
    if state == "soft" then
        return { { " 📌 soft-pin", "WarningMsg" } }
    elseif state == "hard" then
        return { { " 📍 pinned", "Special" } }
    end
    return nil
end

function M.clear_badges(buf)
    if not (buf and vim.api.nvim_buf_is_valid(buf)) then return end
    vim.api.nvim_buf_clear_namespace(buf, M.pin_ns, 0, -1)
end

function M.render()
    local chat = require("poor-cli.chat")
    local buf = chat.buf
    if not (buf and vim.api.nvim_buf_is_valid(buf)) then return end
    M.clear_badges(buf)
    for _, turn in ipairs(chat.turns or {}) do
        local id = turn.id
        local state = id and M._pins[tostring(id)] or nil
        local virt = badge_for(state)
        if virt and turn.start_line then
            pcall(vim.api.nvim_buf_set_extmark, buf, M.pin_ns, turn.start_line, 0, {
                virt_text = virt,
                virt_text_pos = "eol",
                hl_mode = "combine",
                priority = 160,
            })
        end
    end
end

function M.hydrate()
    local rpc = require("poor-cli.rpc")
    rpc.request("poor-cli/listTurnPins", {}, function(result, err)
        vim.schedule(function()
            if err then return end
            local pins = (result or {}).pins or {}
            if type(pins) == "table" then
                M._pins = pins
                M.render()
            end
        end)
    end)
end

local function turn_at_cursor()
    local chat = require("poor-cli.chat")
    if not (chat.win and vim.api.nvim_win_is_valid(chat.win)) then return nil end
    local row = vim.api.nvim_win_get_cursor(chat.win)[1] -- 1-based
    for _, turn in ipairs(chat.turns or {}) do
        local s = (turn.start_line or 0) + 1 -- 0-based extmark -> 1-based
        local e = (turn.end_line or s)
        if row >= s and row <= e then return turn end
    end
    return nil
end

function M.toggle_at_cursor()
    local turn = turn_at_cursor()
    if not turn or not turn.id then
        require("poor-cli.notify").notify("[poor-cli] no turn under cursor", vim.log.levels.WARN)
        return
    end
    local id = tostring(turn.id)
    local cur = M._pins[id] or false
    local nxt = CYCLE[cur]
    local rpc = require("poor-cli.rpc")
    rpc.request("poor-cli/setTurnPin", { turnId = id, state = nxt or vim.NIL }, function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] setTurnPin: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end
            local pins = (result or {}).pins or {}
            if type(pins) == "table" then M._pins = pins end
            M.render()
            local label = nxt and ("now " .. nxt) or "cleared"
            require("poor-cli.notify").notify("[poor-cli] turn pin " .. label, vim.log.levels.INFO)
        end)
    end)
end

function M.install_keymaps(buf)
    if not (buf and vim.api.nvim_buf_is_valid(buf)) then return end
    vim.keymap.set("n", "gp", M.toggle_at_cursor, {
        buffer = buf, nowait = true, silent = true,
        desc = "poor-cli: cycle turn pin (none→soft→hard→none)",
    })
end

-- Test hooks
M._badge_for = badge_for
M._cycle = CYCLE

return M
