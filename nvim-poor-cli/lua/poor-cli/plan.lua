local rpc = require("poor-cli.rpc")
local M = {}
M.state = { steps = {}, summary = "", original_request = "", prompt_id = "", active = false }
local plan_buf = nil
local plan_win = nil
local status_icons = { pending = "[ ]", running = "[>]", done = "[x]", skipped = "[-]" }

local function render_lines()
    local lines = {}
    table.insert(lines, "# plan review")
    table.insert(lines, "")
    if M.state.summary ~= "" then
        table.insert(lines, M.state.summary)
        table.insert(lines, "")
    end
    for i, step in ipairs(M.state.steps) do
        local icon = status_icons[step.status] or "[ ]"
        local desc = type(step) == "table" and (step.description or tostring(step)) or tostring(step)
        table.insert(lines, ("%s %d. %s"):format(icon, i, desc))
    end
    table.insert(lines, "")
    table.insert(lines, "---")
    table.insert(lines, "a = approve | r = reject | q = close")
    return lines
end

local function update_buffer()
    if not plan_buf or not vim.api.nvim_buf_is_valid(plan_buf) then return end
    vim.bo[plan_buf].modifiable = true
    vim.api.nvim_buf_set_lines(plan_buf, 0, -1, false, render_lines())
    vim.bo[plan_buf].modifiable = false
end

local function close_plan()
    if plan_win and vim.api.nvim_win_is_valid(plan_win) then
        vim.api.nvim_win_close(plan_win, true)
    end
    plan_win = nil
    if plan_buf and vim.api.nvim_buf_is_valid(plan_buf) then
        vim.api.nvim_buf_delete(plan_buf, { force = true })
    end
    plan_buf = nil
end

local function send_decision(allowed)
    rpc.notify("poor-cli/planRes", { promptId = M.state.prompt_id, allowed = allowed })
    vim.notify("[poor-cli] plan " .. (allowed and "approved" or "rejected"),
        allowed and vim.log.levels.INFO or vim.log.levels.WARN)
    M.state.active = false
    close_plan()
end

function M.open(data)
    data = data or {}
    M.state.summary = data.summary or ""
    M.state.original_request = data.original_request or ""
    M.state.prompt_id = data.prompt_id or ""
    M.state.active = true
    M.state.steps = {}
    if type(data.steps) == "table" then
        for _, s in ipairs(data.steps) do
            if type(s) == "table" then
                table.insert(M.state.steps, { description = s.description or s[1] or tostring(s), status = "pending" })
            else
                table.insert(M.state.steps, { description = tostring(s), status = "pending" })
            end
        end
    end
    close_plan() -- close any prior plan window
    plan_buf = vim.api.nvim_create_buf(false, true)
    vim.bo[plan_buf].buftype = "nofile"
    vim.bo[plan_buf].bufhidden = "wipe"
    vim.bo[plan_buf].swapfile = false
    vim.bo[plan_buf].filetype = "markdown"
    vim.api.nvim_buf_set_name(plan_buf, "[poor-cli plan]")
    update_buffer()
    local width = math.min(80, math.floor(vim.o.columns * 0.6))
    local height = math.min(#M.state.steps + 8, math.floor(vim.o.lines * 0.6))
    plan_win = vim.api.nvim_open_win(plan_buf, true, {
        relative = "editor",
        width = width,
        height = height,
        col = math.floor((vim.o.columns - width) / 2),
        row = math.floor((vim.o.lines - height) / 2),
        style = "minimal",
        border = "rounded",
        title = " plan review ",
        title_pos = "center",
    })
    vim.keymap.set("n", "a", function() send_decision(true) end, { buffer = plan_buf, nowait = true })
    vim.keymap.set("n", "r", function() send_decision(false) end, { buffer = plan_buf, nowait = true })
    vim.keymap.set("n", "q", close_plan, { buffer = plan_buf, nowait = true })
    vim.keymap.set("n", "<Esc>", close_plan, { buffer = plan_buf, nowait = true })
end

function M.update_step(index, status)
    if index and M.state.steps[index] then
        M.state.steps[index].status = status
        update_buffer()
    end
end

function M.on_progress(data)
    if not M.state.active then return end
    local phase = data and data.phase or ""
    for i, step in ipairs(M.state.steps) do
        if step.status == "running" and phase ~= step.description then
            step.status = "done"
        end
        if step.status == "pending" and (phase == step.description or phase ~= "") then
            step.status = "running"
            update_buffer()
            return
        end
    end
    update_buffer()
end

function M.is_active() return M.state.active end

function M.setup() end -- placeholder for init.lua registration

return M
