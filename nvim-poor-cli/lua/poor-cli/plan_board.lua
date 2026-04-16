local rpc = require("poor-cli.rpc")

local M = {}

M.buf = nil
M.win = nil
M.plan = nil
M.line_cells = {}
M.expanded = {}
M.ns = vim.api.nvim_create_namespace("poor-cli_plan_board")
M.columns = {
    { key = "todo", title = "Todo", hl = "Identifier" },
    { key = "doing", title = "Doing", hl = "Statement" },
    { key = "blocked", title = "Blocked", hl = "ErrorMsg" },
    { key = "done", title = "Done", hl = "Comment" },
}
M.width = 24

local function clip(value, width)
    local text = tostring(value or ""):gsub("\n.*", "")
    if #text <= width then return text end
    return text:sub(1, math.max(1, width - 3)) .. "..."
end

local function pad(value, width)
    local text = clip(value, width)
    return text .. string.rep(" ", math.max(0, width - #text))
end

local function border()
    local cells = {}
    for _ = 1, #M.columns do table.insert(cells, string.rep("-", M.width + 2)) end
    return "+" .. table.concat(cells, "+") .. "+"
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

local function step_text(step, index)
    return ("%d. %s"):format(index, step.description or step.title or step.text or "")
end

function M.render_lines(plan)
    plan = plan or {}
    local buckets = { todo = {}, doing = {}, blocked = {}, done = {} }
    local steps = type(plan.steps) == "table" and plan.steps or {}
    for index, step in ipairs(steps) do
        if type(step) == "table" then
            step.__index = index
            step.__id = step_id(step, index)
            table.insert(buckets[normalize_status(step.status)], step)
        end
    end

    local lines = { "# poor-cli plan", "keys: <Tab> advance  <S-Tab> regress  <CR> expand  x block  a add  d delete  r refresh  q close" }
    if plan.summary and plan.summary ~= "" then table.insert(lines, "summary: " .. tostring(plan.summary)) end
    if plan.originalRequest and plan.originalRequest ~= "" then table.insert(lines, "request: " .. clip(plan.originalRequest, 100)) end
    table.insert(lines, "")
    table.insert(lines, border())

    local header = {}
    for _, col in ipairs(M.columns) do table.insert(header, " " .. pad(col.title, M.width) .. " ") end
    table.insert(lines, "|" .. table.concat(header, "|") .. "|")
    table.insert(lines, border())

    local cells_by_line = {}
    local max_rows = 0
    for _, col in ipairs(M.columns) do max_rows = math.max(max_rows, #buckets[col.key]) end
    if max_rows == 0 then
        table.insert(lines, "| " .. pad("no plan steps", (M.width + 3) * #M.columns - 1) .. "|")
    end
    for row = 1, max_rows do
        local cells, line_cells, cursor = {}, {}, 1
        for _, col in ipairs(M.columns) do
            local step = buckets[col.key][row]
            local text = ""
            if step then text = "- " .. step_text(step, step.__index) end
            local cell = " " .. pad(text, M.width) .. " "
            table.insert(cells, cell)
            if step then
                table.insert(line_cells, { start_col = cursor, end_col = cursor + #cell - 1, step_id = step.__id, status = col.key })
            end
            cursor = cursor + #cell + 1
        end
        table.insert(lines, "|" .. table.concat(cells, "|") .. "|")
        cells_by_line[#lines] = line_cells
        for _, col in ipairs(M.columns) do
            local step = buckets[col.key][row]
            if step and M.expanded[step.__id] then
                local detail = step.details or step.body or ""
                if detail == "" and type(step.dependencies) == "table" and #step.dependencies > 0 then
                    detail = "depends: " .. table.concat(step.dependencies, ", ")
                end
                if detail == "" then detail = step.description or "" end
                table.insert(lines, "| " .. pad("  " .. detail, (M.width + 3) * #M.columns - 1) .. "|")
                cells_by_line[#lines] = { { start_col = 1, end_col = #lines[#lines], step_id = step.__id, status = col.key } }
            end
        end
    end
    table.insert(lines, border())
    return lines, cells_by_line
end

local function apply_extmarks()
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then return end
    vim.api.nvim_buf_clear_namespace(M.buf, M.ns, 0, -1)
    for line, cells in pairs(M.line_cells) do
        for _, cell in ipairs(cells) do
            local hl = "Normal"
            for _, col in ipairs(M.columns) do
                if col.key == cell.status then hl = col.hl end
            end
            vim.api.nvim_buf_set_extmark(M.buf, M.ns, line - 1, cell.start_col, {
                end_col = cell.end_col,
                hl_group = hl,
            })
        end
    end
end

function M.render()
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then return end
    local lines
    lines, M.line_cells = M.render_lines(M.plan or {})
    vim.bo[M.buf].modifiable = true
    vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, lines)
    vim.bo[M.buf].modifiable = false
    apply_extmarks()
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
    local pos = vim.api.nvim_win_get_cursor(win)
    local cells = M.line_cells[pos[1]]
    if not cells then return nil end
    local col = pos[2]
    for _, cell in ipairs(cells) do
        if col >= cell.start_col and col <= cell.end_col then return cell.step_id end
    end
    return cells[1] and cells[1].step_id or nil
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
    local description = vim.fn.input("plan step: ")
    if description == "" then return end
    mutate("plan_add", { description = description })
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
        width = math.min(140, vim.o.columns - 4),
        height = math.max(24, vim.o.lines - 4),
        position = "center",
        title = " poor-cli plan board ",
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
