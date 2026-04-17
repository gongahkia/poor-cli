local rpc = require("poor-cli.rpc")

local M = {}

M.buf = nil
M.win = nil
M.plan = nil
M.line_step = {}
M.expanded = {}
M.ns = vim.api.nvim_create_namespace("poor-cli_plan_board")

-- Render groups in this order; hidden if empty and not the active bucket.
M.groups = {
    { key = "doing",   title = "DOING",   glyph = "●", hl = "Statement" },
    { key = "blocked", title = "BLOCKED", glyph = "⊘", hl = "ErrorMsg" },
    { key = "todo",    title = "TODO",    glyph = "○", hl = "Identifier" },
    { key = "done",    title = "DONE",    glyph = "✓", hl = "Comment" },
}

local function clip(value, width)
    local text = tostring(value or ""):gsub("\n.*", "")
    if #text <= width then return text end
    return text:sub(1, math.max(1, width - 3)) .. "..."
end

local function normalize_status(status)
    status = tostring(status or "todo")
    if status == "pending" then return "todo" end
    if status == "running" or status == "in-progress" then return "doing" end
    if status == "skipped" then return "done" end
    if status == "blocked" or status == "done" or status == "doing" then return status end
    return "todo"
end

local function step_id(step, index)
    return tostring(step.id or step.stepId or step.step_id or index)
end

local function step_text(step)
    return tostring(step.description or step.title or step.text or "")
end

local function bucketize(plan)
    local buckets = { todo = {}, doing = {}, blocked = {}, done = {} }
    local steps = type(plan.steps) == "table" and plan.steps or {}
    for index, step in ipairs(steps) do
        if type(step) == "table" then
            step.__index = index
            step.__id = step_id(step, index)
            table.insert(buckets[normalize_status(step.status)], step)
        end
    end
    return buckets
end

local function count_line(buckets)
    local parts = {}
    for _, group in ipairs(M.groups) do
        table.insert(parts, string.format("%d %s", #buckets[group.key], group.title:lower()))
    end
    return table.concat(parts, " · ")
end

function M.render_lines(plan)
    plan = plan or {}
    local buckets = bucketize(plan)
    local lines = {}
    local line_step = {}
    local section_hl = {}

    table.insert(lines, "# poor-cli plan")
    if plan.summary and plan.summary ~= "" then
        table.insert(lines, "summary: " .. tostring(plan.summary))
    end
    if plan.originalRequest and plan.originalRequest ~= "" then
        table.insert(lines, "request: " .. clip(plan.originalRequest, 120))
    end
    table.insert(lines, count_line(buckets))

    local any = false
    for _, group in ipairs(M.groups) do
        local steps = buckets[group.key]
        if #steps > 0 then
            any = true
            table.insert(lines, "")
            table.insert(lines, group.title)
            section_hl[#lines] = group.hl
            for _, step in ipairs(steps) do
                local row = string.format("  %s %-3d %s", group.glyph, step.__index, step_text(step))
                table.insert(lines, row)
                line_step[#lines] = step.__id
                if M.expanded[step.__id] then
                    if type(step.dependencies) == "table" and #step.dependencies > 0 then
                        local dep_line = "       depends: " .. table.concat(step.dependencies, ", ")
                        table.insert(lines, dep_line)
                        line_step[#lines] = step.__id
                    end
                    local detail = step.details or step.body or ""
                    if detail ~= "" then
                        for _, chunk in ipairs(vim.split(tostring(detail), "\n", { plain = true })) do
                            table.insert(lines, "       " .. chunk)
                            line_step[#lines] = step.__id
                        end
                    end
                end
            end
        end
    end
    if not any then
        table.insert(lines, "")
        table.insert(lines, "no plan steps")
    end
    table.insert(lines, "")
    table.insert(lines, "<CR> expand  <Tab>/<S-Tab> advance/regress  x block  a add  d del  r refresh  q close")
    return lines, line_step, section_hl
end

local function apply_extmarks(section_hl)
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then return end
    vim.api.nvim_buf_clear_namespace(M.buf, M.ns, 0, -1)
    for line, hl in pairs(section_hl) do
        vim.api.nvim_buf_set_extmark(M.buf, M.ns, line - 1, 0, {
            end_col = #vim.api.nvim_buf_get_lines(M.buf, line - 1, line, false)[1],
            hl_group = hl,
        })
    end
end

function M.render()
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then return end
    local lines, line_step, section_hl = M.render_lines(M.plan or {})
    M.line_step = line_step
    vim.bo[M.buf].modifiable = true
    vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, lines)
    vim.bo[M.buf].modifiable = false
    apply_extmarks(section_hl)
end

local function set_plan(result, err)
    vim.schedule(function()
        if err then
            require("poor-cli.notify").notify("[poor-cli] plan: " .. rpc.format_error(err), vim.log.levels.ERROR)
            return
        end
        M.plan = result or {}
        M.render()
    end)
end

function M.refresh()
    rpc.plan_list(set_plan)
end

local function current_step_id()
    local win = M.win and vim.api.nvim_win_is_valid(M.win) and M.win or vim.api.nvim_get_current_win()
    local row = vim.api.nvim_win_get_cursor(win)[1]
    return M.line_step[row]
end

local function mutate(method, params)
    rpc[method](params, set_plan)
end

function M.advance()
    local id = current_step_id()
    if id then mutate("plan_advance", { stepId = id }) end
end

function M.regress()
    local id = current_step_id()
    if id then mutate("plan_regress", { stepId = id }) end
end

function M.block()
    local id = current_step_id()
    if id then mutate("plan_block", { stepId = id }) end
end

function M.delete()
    local id = current_step_id()
    if id then mutate("plan_delete", { stepId = id }) end
end

function M.toggle_expand()
    local id = current_step_id()
    if not id then return end
    M.expanded[id] = not M.expanded[id]
    M.render()
end

function M.add()
    vim.ui.input({ prompt = "plan step: " }, function(description)
        if not description or description == "" then return end
        mutate("plan_add", { description = description })
    end)
end

function M.close()
    if M.win and vim.api.nvim_win_is_valid(M.win) then vim.api.nvim_win_close(M.win, true) end
    M.win = nil
end

function M.open()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_set_current_win(M.win)
        M.refresh()
        return M.buf
    end
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then
        M.buf = vim.api.nvim_create_buf(false, true)
        vim.bo[M.buf].buftype = "nofile"
        vim.bo[M.buf].bufhidden = "hide"
        vim.bo[M.buf].swapfile = false
        vim.bo[M.buf].filetype = "poor-cli-plan"
        vim.api.nvim_buf_set_name(M.buf, "[poor-cli plan board]")
    end
    local float_win = require("poor-cli.float_win")
    M.win = float_win.open(M.buf, {
        width = math.min(100, vim.o.columns - 4),
        height = math.max(24, vim.o.lines - 4),
        position = "center",
        title = " poor-cli plan ",
        close_keys = {},
        wrap = false,
    })
    vim.keymap.set("n", "q", M.close, { buffer = M.buf, nowait = true, desc = "Close plan board" })
    vim.keymap.set("n", "<Esc>", M.close, { buffer = M.buf, nowait = true, desc = "Close plan board" })
    vim.keymap.set("n", "r", M.refresh, { buffer = M.buf, nowait = true, desc = "Refresh plan board" })
    vim.keymap.set("n", "<Tab>", M.advance, { buffer = M.buf, nowait = true, desc = "Advance plan step" })
    vim.keymap.set("n", "<S-Tab>", M.regress, { buffer = M.buf, nowait = true, desc = "Regress plan step" })
    vim.keymap.set("n", "<CR>", M.toggle_expand, { buffer = M.buf, nowait = true, desc = "Expand plan step" })
    vim.keymap.set("n", "x", M.block, { buffer = M.buf, nowait = true, desc = "Block plan step" })
    vim.keymap.set("n", "a", M.add, { buffer = M.buf, nowait = true, desc = "Add plan step" })
    vim.keymap.set("n", "d", M.delete, { buffer = M.buf, nowait = true, desc = "Delete plan step" })
    M.refresh()
    return M.buf
end

return M
