local rpc = require("poor-cli.rpc")
local config = require("poor-cli.config")

local M = {
    ns = vim.api.nvim_create_namespace("poor-cli-branches"),
    buf = nil,
    win = nil,
    rows = {},
    active_line = nil,
    tree = nil,
}

local function cfg()
    return config.get("branches") or {}
end

local function max_siblings()
    return tonumber(cfg().max_siblings) or 20
end

local function branch_at_cursor()
    local row = M.rows[vim.api.nvim_win_get_cursor(0)[1]]
    return row and row.branch_id or nil
end

local function apply_snapshot(result)
    if type(result) ~= "table" or type(result.snapshot) ~= "table" then return end
    local ok, chat = pcall(require, "poor-cli.chat")
    if ok and type(chat.render_history) == "function" then
        chat.render_history(result.snapshot, result)
    end
end

local function set_lines(lines)
    if not M.buf or not vim.api.nvim_buf_is_valid(M.buf) then return end
    vim.bo[M.buf].modifiable = true
    vim.api.nvim_buf_clear_namespace(M.buf, M.ns, 0, -1)
    vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, lines)
    if M.active_line then
        vim.api.nvim_buf_set_extmark(M.buf, M.ns, M.active_line - 1, 0, {
            line_hl_group = "Visual",
        })
    end
    vim.bo[M.buf].modifiable = false
end

local function render_node(node, depth, lines)
    if node.collapsed then
        table.insert(lines, string.rep("  ", depth) .. "... " .. tostring(node.count or 0) .. " more siblings")
        return
    end
    local marker = node.active and "> " or "  "
    table.insert(lines, string.rep("  ", depth) .. marker .. tostring(node.label or node.id or ""))
    M.rows[#lines] = { branch_id = node.id, node = node }
    if node.active then M.active_line = #lines end
    for _, child in ipairs(node.children or {}) do
        render_node(child, depth + 1, lines)
    end
end

function M.render_lines(payload)
    M.rows = {}
    M.active_line = nil
    local lines = {
        "# poor-cli branches",
        "",
        -- keys wrapped in backticks so markdown filetype + vim-markdown plugin
        -- don't interpret `[[` / `]]` as wiki-link syntax and draw boxes.
        "keys: `[[` prev sibling | `]]` next sibling | `<CR>` switch",
        "      `r` refresh | `q` close",
        "",
    }
    local roots = type(payload) == "table" and payload.roots or {}
    if #roots == 0 then
        table.insert(lines, "no branches")
        return lines
    end
    for _, root in ipairs(roots) do
        render_node(root, 0, lines)
    end
    return lines
end

function M.refresh()
    rpc.branches_tree({ maxSiblings = max_siblings() }, function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] branches: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end
            M.tree = result or {}
            set_lines(M.render_lines(M.tree))
        end)
    end)
end

local function ensure_buf()
    if M.buf and vim.api.nvim_buf_is_valid(M.buf) then return M.buf end
    M.buf = vim.api.nvim_create_buf(false, true)
    vim.bo[M.buf].buftype = "nofile"
    vim.bo[M.buf].bufhidden = "hide"
    vim.bo[M.buf].swapfile = false
    vim.bo[M.buf].filetype = "markdown"
    vim.api.nvim_buf_set_name(M.buf, "[poor-cli branches]")
    return M.buf
end

local function map(lhs, fn, desc)
    vim.keymap.set("n", lhs, fn, { buffer = M.buf, silent = true, nowait = true, desc = desc })
end

function M.open()
    local buf = ensure_buf()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_set_current_win(M.win)
    else
        local width = tonumber(cfg().panel_width) or 60
        local float_win = require("poor-cli.float_win")
        M.win = float_win.open(buf, {
            width = width,
            height = math.max(20, vim.o.lines - 4),
            position = "right",
            title = " poor-cli branches ",
            close_keys = {},
            wrap = true,
        })
        vim.wo[M.win].linebreak = true
        vim.wo[M.win].breakindent = true
        vim.wo[M.win].conceallevel = 0
    end
    map("q", M.close, "close branches")
    map("<Esc>", M.close, "close branches")
    map("r", M.refresh, "refresh branches")
    map("<CR>", function() M.switch(branch_at_cursor()) end, "switch branch")
    map("[[", function() M.switch(branch_at_cursor(), "prev") end, "previous sibling")
    map("]]", function() M.switch(branch_at_cursor(), "next") end, "next sibling")
    M.refresh()
    return buf
end

function M.close()
    if M.win and vim.api.nvim_win_is_valid(M.win) then vim.api.nvim_win_close(M.win, true) end
    M.win = nil
end

function M.toggle()
    if M.win and vim.api.nvim_win_is_valid(M.win) then M.close() else M.open() end
end

function M.switch(branch_id, direction)
    local params = { maxSiblings = max_siblings() }
    if branch_id and branch_id ~= "" then params.branchId = branch_id end
    if direction and direction ~= "" then params.direction = direction end
    rpc.branches_switch(params, function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] branches: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end
            M.tree = result or {}
            set_lines(M.render_lines(M.tree))
            apply_snapshot(result)
        end)
    end)
end

-- setup() intentionally removed: the branches UI is now reached via
-- `:PoorCLISession branches`. M.open()/M.close()/M.toggle()/M.refresh()/M.switch()
-- remain as the module API called by the session dispatcher and chat module.
function M.setup() end

return M
