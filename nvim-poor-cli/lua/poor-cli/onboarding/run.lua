-- poor-cli/onboarding/run.lua
-- Drives a list of step descriptors through vim.ui.select / vim.ui.input.
-- State is a plain table; `done_cb()` fires when the chain completes normally.

local rpc = require("poor-cli.rpc")

local M = {}

local function notify(msg, level)
    require("poor-cli.notify").notify("[poor-cli] " .. msg, level)
end

local function show_info(title, total, index, lines, on_advance, on_cancel)
    local float_win = require("poor-cli.float_win")
    local buf_lines = {
        string.format("# poor-cli setup (%d/%d) — %s", index, total, title),
        "",
    }
    for _, line in ipairs(lines) do table.insert(buf_lines, line) end
    table.insert(buf_lines, "")
    table.insert(buf_lines, "<CR> continue · q cancel")
    local buf, win = float_win.open_lines(buf_lines, {
        filetype = "markdown",
        name = "[poor-cli setup]",
        title = " setup " .. index .. "/" .. total .. " ",
        width = math.min(70, vim.o.columns - 4),
        height = math.min(#buf_lines + 2, vim.o.lines - 4),
        position = "center",
        modifiable = false,
    })
    local function close_and(fn)
        if win and vim.api.nvim_win_is_valid(win) then
            pcall(vim.api.nvim_win_close, win, true)
        end
        if fn then fn() end
    end
    vim.keymap.set("n", "<CR>", function() close_and(on_advance) end,
        { buffer = buf, nowait = true, silent = true })
    vim.keymap.set("n", "q", function() close_and(on_cancel) end,
        { buffer = buf, nowait = true, silent = true })
    vim.keymap.set("n", "<Esc>", function() close_and(on_cancel) end,
        { buffer = buf, nowait = true, silent = true })
end

local function visible_count(steps, state)
    local n = 0
    for _, step in ipairs(steps) do
        if not (step.skip and step.skip(state)) then n = n + 1 end
    end
    return n
end

local function run_step(steps, state, index, visible_index, total_visible, done_cb, cancel_cb)
    if index > #steps then done_cb(); return end
    local step = steps[index]
    if step.skip and step.skip(state) then
        run_step(steps, state, index + 1, visible_index, total_visible, done_cb, cancel_cb)
        return
    end

    local function advance()
        run_step(steps, state, index + 1, visible_index + 1, total_visible, done_cb, cancel_cb)
    end

    if step.kind == "info" then
        local body = type(step.body) == "function" and step.body(state) or step.body or {}
        show_info(step.title or step.id, total_visible, visible_index, body, advance, cancel_cb)
        return
    end

    if step.kind == "select" then
        local items, ids = step.items(state)
        if not items or #items == 0 then
            advance(); return
        end
        vim.ui.select(items, { prompt = step.prompt or (step.title .. ":") }, function(choice, idx)
            if not choice then cancel_cb(); return end
            if step.apply then step.apply(state, choice, idx or 1, ids or items) end
            vim.schedule(advance)
        end)
        return
    end

    if step.kind == "input" then
        vim.ui.input({ prompt = step.prompt or (step.title .. ": "), default = step.default }, function(value)
            if value == nil then cancel_cb(); return end
            if step.apply then step.apply(state, value) end
            vim.schedule(advance)
        end)
        return
    end

    if step.kind == "dynamic" or step.kind == "commit" then
        step.run(state, advance, cancel_cb)
        return
    end

    advance()
end

local function ensure_server(callback)
    if rpc.is_running() then callback(); return end
    rpc.start()
    vim.defer_fn(function()
        if rpc.is_running() then
            rpc.initialize()
            vim.defer_fn(callback, 300)
        else
            notify("server failed to start; API key step will be skipped", vim.log.levels.WARN)
            callback()
        end
    end, 500)
end

local function fetch_providers(state, callback)
    if state.provider_data then callback(); return end
    rpc.request("poor-cli/listProviders", {}, function(result, err)
        vim.schedule(function()
            if not err and result then state.provider_data = result end
            callback()
        end)
    end)
end

-- Public: kick off a step-list. `done_cb` runs on successful completion,
-- `cancel_cb` on user escape. Both default to no-op.
function M.run(steps, done_cb, cancel_cb)
    local state = {
        choices = {
            provider = nil, api_key = nil, model = nil,
            permission_mode = "default", economy_preset = "balanced", budget = nil,
        },
        provider_data = nil,
    }
    done_cb = done_cb or function() end
    cancel_cb = cancel_cb or function()
        notify("onboarding cancelled — progress not saved", vim.log.levels.INFO)
    end
    ensure_server(function()
        fetch_providers(state, function()
            local total = visible_count(steps, state)
            run_step(steps, state, 1, 1, total, done_cb, cancel_cb)
        end)
    end)
end

return M
