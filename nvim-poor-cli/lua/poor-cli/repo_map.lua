local rpc = require("poor-cli.rpc")

local M = {}

M.buf = nil
M.win = nil
M.limit = 50
M.files = {}
M.expanded = {}
M.symbols = {}
M.line_rows = {}
M.ns = vim.api.nvim_create_namespace("poor-cli_repo_map")

local MAX_TOP_N = 50
local NEIGHBOR_LIMIT = 8
local SYMBOL_LIMIT = 12

local function n(value)
    return tonumber(value) or 0
end

local function configured_limit(limit)
    local raw = limit or vim.g.poor_cli_repo_map_top_n or 50
    return math.max(1, math.min(MAX_TOP_N, n(raw) > 0 and n(raw) or 50))
end

local function display_path(file)
    return tostring(file.relative_path or file.path or "")
end

local function row_key(file)
    return tostring(file.path or file.relative_path or "")
end

local function fmt_score(score)
    return string.format("%.3f", n(score))
end

local function truncate_list(items, limit)
    items = items or {}
    local visible = {}
    for idx, item in ipairs(items) do
        if idx > limit then break end
        table.insert(visible, item)
    end
    return visible, math.max(0, #items - #visible)
end

local function line_for_neighbor(prefix, arrow, label, item)
    local path = display_path(item)
    local edge_type = tostring(item.edge_type or item.type or "")
    local suffix = edge_type ~= "" and (" [" .. edge_type .. "]") or ""
    return string.format("%s%s %s %s%s", prefix, arrow, label, path, suffix)
end

local function symbol_text(symbol)
    local scope = tostring(symbol.scope or "")
    local name = tostring(symbol.name or "")
    if scope ~= "" then name = scope .. "." .. name end
    return string.format("%s %s:%d", tostring(symbol.kind or "symbol"), name, n(symbol.line_start))
end

function M.render_lines(payload)
    payload = payload or {}
    local files = vim.deepcopy(payload.files or M.files or {})
    table.sort(files, function(a, b)
        local as = n(a.score or a.pagerank)
        local bs = n(b.score or b.pagerank)
        if as == bs then return display_path(a) < display_path(b) end
        return as > bs
    end)
    local lines = {
        string.format("┌──── repo map (top %d by pagerank) ─────────────────────────┐", M.limit),
        "│ keys: <CR> open  gl imports  gs symbols  r refresh  q close │",
    }
    local rows = {}
    for idx, file in ipairs(files) do
        local key = row_key(file)
        local marker = (M.expanded[key] or M.symbols[key]) and "▾" or "▸"
        table.insert(lines, string.format("│ %s %2d. %s %s │", marker, idx, fmt_score(file.score or file.pagerank), display_path(file)))
        rows[#lines] = { kind = "file", file = file }

        local expanded = M.expanded[key]
        if expanded then
            local imports, more_imports = truncate_list(expanded.imports or {}, NEIGHBOR_LIMIT)
            local imported_by, more_imported_by = truncate_list(expanded.imported_by or expanded.importedBy or {}, NEIGHBOR_LIMIT)
            if #imports == 0 then
                table.insert(lines, "│   ├─ ↓ imports: none │")
            else
                table.insert(lines, "│   ├─ ↓ imports │")
                for _, item in ipairs(imports) do
                    table.insert(lines, line_for_neighbor("│   │  ", "├─", "", item) .. " │")
                end
                if more_imports > 0 then
                    table.insert(lines, string.format("│   │  └─ ... %d more │", more_imports))
                end
            end
            if #imported_by == 0 then
                table.insert(lines, "│   └─ ↑ imported-by: none │")
            else
                table.insert(lines, "│   └─ ↑ imported-by │")
                for _, item in ipairs(imported_by) do
                    table.insert(lines, line_for_neighbor("│      ", "├─", "", item) .. " │")
                end
                if more_imported_by > 0 then
                    table.insert(lines, string.format("│      └─ ... %d more │", more_imported_by))
                end
            end
        end

        local symbols = M.symbols[key]
        if symbols then
            local visible, more = truncate_list(symbols.symbols or {}, SYMBOL_LIMIT)
            table.insert(lines, "│   └─ symbols │")
            for _, symbol in ipairs(visible) do
                table.insert(lines, "│      ├─ " .. symbol_text(symbol) .. " │")
            end
            if more > 0 then
                table.insert(lines, string.format("│      └─ ... %d more │", more))
            elseif #visible == 0 then
                table.insert(lines, "│      └─ none │")
            end
        end
    end
    if #files == 0 then
        table.insert(lines, "│ no repo map entries │")
    end
    table.insert(lines, "└─────────────────────────────────────────────────────────────┘")
    return lines, rows
end

function M.render()
    if not (M.buf and vim.api.nvim_buf_is_valid(M.buf)) then return end
    local lines
    lines, M.line_rows = M.render_lines({ files = M.files })
    vim.bo[M.buf].modifiable = true
    vim.api.nvim_buf_set_lines(M.buf, 0, -1, false, lines)
    vim.bo[M.buf].modifiable = false
    vim.api.nvim_buf_clear_namespace(M.buf, M.ns, 0, -1)
end

local function current_file()
    if not (M.win and vim.api.nvim_win_is_valid(M.win)) then return nil end
    local row = M.line_rows[vim.api.nvim_win_get_cursor(M.win)[1]]
    return row and row.file or nil
end

local function set_top(result, err)
    vim.schedule(function()
        if err then
            require("poor-cli.notify").notify("[poor-cli] repo map: " .. rpc.format_error(err), vim.log.levels.ERROR)
            return
        end
        M.files = (result or {}).files or {}
        table.sort(M.files, function(a, b)
            local as = n(a.score or a.pagerank)
            local bs = n(b.score or b.pagerank)
            if as == bs then return display_path(a) < display_path(b) end
            return as > bs
        end)
        M.render()
    end)
end

function M.refresh()
    rpc.repo_map_top({ limit = M.limit }, set_top)
end

function M.toggle_imports()
    local file = current_file()
    if not file then return end
    local key = row_key(file)
    if M.expanded[key] then
        M.expanded[key] = nil
        M.render()
        return
    end
    rpc.repo_map_expand({ path = file.path or file.relative_path }, function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] repo map: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end
            M.expanded[key] = result or {}
            M.render()
        end)
    end)
end

function M.toggle_symbols()
    local file = current_file()
    if not file then return end
    local key = row_key(file)
    if M.symbols[key] then
        M.symbols[key] = nil
        M.render()
        return
    end
    rpc.repo_map_symbols({ path = file.path or file.relative_path, limit = 80 }, function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] repo map: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end
            M.symbols[key] = result or {}
            M.render()
        end)
    end)
end

function M.open_current()
    local file = current_file()
    if not file then return end
    local path = tostring(file.path or file.relative_path or "")
    if path == "" then return end
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_set_current_win(M.win)
        vim.cmd("wincmd p")
        if vim.api.nvim_get_current_win() == M.win then
            vim.cmd("leftabove split")
        end
    end
    vim.cmd("edit " .. vim.fn.fnameescape(path))
end

function M.close()
    if M.win and vim.api.nvim_win_is_valid(M.win) then
        vim.api.nvim_win_close(M.win, true)
    end
    M.win = nil
end

function M.open(limit)
    M.limit = configured_limit(limit)
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
        vim.bo[M.buf].filetype = "poor-cli-repo-map"
        vim.api.nvim_buf_set_name(M.buf, "[poor-cli repo map]")
    end
    vim.cmd("botright 92vsplit")
    M.win = vim.api.nvim_get_current_win()
    vim.api.nvim_win_set_buf(M.win, M.buf)
    vim.wo[M.win].wrap = false
    vim.wo[M.win].number = false
    vim.wo[M.win].relativenumber = false
    vim.keymap.set("n", "q", M.close, { buffer = M.buf, nowait = true, desc = "Close repo map" })
    vim.keymap.set("n", "r", M.refresh, { buffer = M.buf, nowait = true, desc = "Refresh repo map" })
    vim.keymap.set("n", "<CR>", M.open_current, { buffer = M.buf, nowait = true, desc = "Open repo map file" })
    vim.keymap.set("n", "gl", M.toggle_imports, { buffer = M.buf, nowait = true, desc = "Expand repo map imports" })
    vim.keymap.set("n", "gs", M.toggle_symbols, { buffer = M.buf, nowait = true, desc = "Show repo map symbols" })
    M.refresh()
    return M.buf
end

return M
