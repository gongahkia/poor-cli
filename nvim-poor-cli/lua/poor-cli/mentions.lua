local M = {}

M.sources = {}
M.order = {}

local function trim(value)
    return tostring(value or ""):gsub("^%s+", ""):gsub("%s+$", "")
end

local function relpath(path)
    local rel = vim.fn.fnamemodify(path, ":.")
    if rel == "" then return path end
    return rel
end

local function file_preview(path)
    local abs = vim.fn.fnamemodify(path, ":p")
    if vim.fn.filereadable(abs) ~= 1 then return path end
    local lines = vim.fn.readfile(abs, "", 40)
    table.insert(lines, 1, path)
    return table.concat(lines, "\n")
end

local function add_source_order(name)
    for _, existing in ipairs(M.order) do
        if existing == name then return end
    end
    table.insert(M.order, name)
end

function M.register_source(name, provider)
    name = trim(name):lower()
    if name == "" or not name:match("^[%w_%-]+$") then
        error("invalid mention source: " .. tostring(name))
    end
    if type(provider) ~= "table" and type(provider) ~= "function" then
        error("mention provider must be table or function")
    end
    M.sources[name] = provider
    add_source_order(name)
end

local function source_label(name, provider)
    if type(provider) == "table" and provider.label then return tostring(provider.label) end
    return "@" .. name .. ":"
end

function M.source_picker_items()
    local items = {}
    for _, name in ipairs(M.order) do
        local provider = M.sources[name]
        if provider then
            table.insert(items, {
                id = name,
                label = source_label(name, provider),
                preview = type(provider) == "table" and provider.preview or nil,
                data = { name = name },
            })
        end
    end
    return items
end

function M.source_items(name, opts)
    local provider = M.sources[trim(name):lower()]
    if not provider then return {} end
    if type(provider) == "function" then return provider(opts or {}) or {} end
    local fn = provider.items or provider.handler
    if type(fn) ~= "function" then return {} end
    return fn(opts or {}) or {}
end

function M.open_source(name, opts)
    local provider = M.sources[trim(name):lower()]
    if type(provider) ~= "table" or type(provider.open) ~= "function" then return false end
    return provider.open(opts or {}) == true
end

local function file_items()
    local items = {}
    local seen = {}
    local files = vim.fn.systemlist({ "git", "ls-files", "--cached", "--others", "--exclude-standard" })
    if vim.v.shell_error ~= 0 then files = {} end
    table.sort(files)
    for _, path in ipairs(files) do
        path = trim(path)
        if path ~= "" and not seen[path] and vim.fn.filereadable(path) == 1 then
            seen[path] = true
            table.insert(items, {
                id = "file:" .. path,
                label = path,
                preview = file_preview(path),
                data = { source = "file", path = path, token = "@file:" .. path },
            })
        end
    end
    return items
end

local function buffer_items()
    local items = {}
    local seen = {}
    for _, bufnr in ipairs(vim.api.nvim_list_bufs()) do
        if vim.api.nvim_buf_is_loaded(bufnr) then
            local name = vim.api.nvim_buf_get_name(bufnr)
            local line = vim.api.nvim_buf_get_lines(bufnr, 0, 1, false)[1] or ""
            if name ~= "" and trim(line) ~= "" and vim.fn.filereadable(name) == 1 then
                local rel = relpath(name)
                if not seen[rel] then
                    seen[rel] = true
                    table.insert(items, {
                        id = "buffer:" .. rel,
                        label = rel,
                        preview = file_preview(name),
                        data = { source = "buffer", path = rel, bufnr = bufnr, token = "@buffer:" .. rel },
                    })
                end
            end
        end
    end
    return items
end

local severity = {
    [vim.diagnostic.severity.ERROR] = "ERROR",
    [vim.diagnostic.severity.WARN] = "WARN",
    [vim.diagnostic.severity.INFO] = "INFO",
    [vim.diagnostic.severity.HINT] = "HINT",
}

local function lsp_items(opts)
    opts = opts or {}
    local buf = opts.target_buf or vim.api.nvim_get_current_buf()
    if not buf or not vim.api.nvim_buf_is_valid(buf) then return {} end
    local name = vim.api.nvim_buf_get_name(buf)
    if name == "" then return {} end
    local rel = relpath(name)
    local items = {}
    for index, diagnostic in ipairs(vim.diagnostic.get(buf)) do
        local line = (diagnostic.lnum or 0) + 1
        local sev = severity[diagnostic.severity] or "DIAG"
        local msg = tostring(diagnostic.message or ""):gsub("%s+", " ")
        local token = "@lsp:" .. rel .. ":" .. line
        table.insert(items, {
            id = "lsp:" .. rel .. ":" .. line .. ":" .. index,
            label = string.format("%s:%d %s %s", rel, line, sev, msg),
            preview = table.concat({
                rel .. ":" .. line,
                sev,
                msg,
                "",
                vim.api.nvim_buf_get_lines(buf, line - 1, line, false)[1] or "",
            }, "\n"),
            data = { source = "lsp", path = rel, line = line, diagnostic = msg, token = token },
        })
    end
    return items
end

M.register_source("file", { label = "@file: repo files", preview = "Files tracked or unignored by git.", items = file_items })
M.register_source("buffer", { label = "@buffer: open buffers", preview = "Loaded file buffers.", items = buffer_items })
M.register_source("lsp", { label = "@lsp: diagnostics", preview = "Diagnostics for the current source buffer.", items = lsp_items })

function M._reset_for_tests()
    M.sources = {}
    M.order = {}
    M.register_source("file", { label = "@file: repo files", preview = "Files tracked or unignored by git.", items = file_items })
    M.register_source("buffer", { label = "@buffer: open buffers", preview = "Loaded file buffers.", items = buffer_items })
    M.register_source("lsp", { label = "@lsp: diagnostics", preview = "Diagnostics for the current source buffer.", items = lsp_items })
end

return M
