-- poor-cli/float_win.lua
-- Shared floating-window primitive used by panels, pickers, and bespoke UIs.
-- Extracts the centered-float pattern duplicated across chat.lua / plan.lua /
-- onboarding.lua / context_mgr.lua so callers don't re-derive geometry.

local M = {}

local function resolve_dim(hint, editor_size, default_frac)
    if type(hint) == "number" then
        if hint > 0 and hint < 1 then
            return math.floor(editor_size * hint)
        end
        return math.max(1, math.floor(hint))
    elseif type(hint) == "table" then
        local frac = tonumber(hint.frac or hint[1] or default_frac or 0.7) or 0.7
        local maxv = tonumber(hint.max or hint[2] or editor_size - 4) or (editor_size - 4)
        return math.min(maxv, math.max(1, math.floor(editor_size * frac)))
    end
    return math.floor(editor_size * (default_frac or 0.7))
end

local function build_config(width, height, opts)
    local cfg = {
        relative = "editor",
        width = width,
        height = height,
        style = opts.style or "minimal",
        border = opts.border or "rounded",
    }
    local pos = opts.position or "center"
    if pos == "center" then
        cfg.row = math.floor((vim.o.lines - height) / 2)
        cfg.col = math.floor((vim.o.columns - width) / 2)
    elseif pos == "top" then
        cfg.row = 1
        cfg.col = math.floor((vim.o.columns - width) / 2)
    elseif pos == "right" then
        cfg.row = 1
        cfg.col = math.max(0, vim.o.columns - width - 2)
    elseif pos == "cursor" then
        cfg.relative = "cursor"
        cfg.row = 1
        cfg.col = 0
    elseif type(pos) == "table" then
        cfg.row = tonumber(pos.row) or 0
        cfg.col = tonumber(pos.col) or 0
    end
    if opts.title then
        cfg.title = opts.title
        cfg.title_pos = opts.title_pos or "center"
    end
    if opts.footer then
        cfg.footer = opts.footer
        cfg.footer_pos = opts.footer_pos or "center"
    end
    return cfg
end

function M.open(buf, opts)
    opts = opts or {}
    if not buf or not vim.api.nvim_buf_is_valid(buf) then
        error("float_win.open: invalid buffer")
    end

    local width = resolve_dim(opts.width, vim.o.columns, 0.7)
    local height = resolve_dim(opts.height, vim.o.lines, 0.7)
    width = math.max(10, math.min(width, vim.o.columns - 2))
    height = math.max(3, math.min(height, vim.o.lines - 2))

    local cfg = build_config(width, height, opts)
    local enter = opts.enter
    if enter == nil then enter = true end
    local win = vim.api.nvim_open_win(buf, enter, cfg)

    if opts.wrap ~= false then vim.wo[win].wrap = true end
    if opts.number == false or opts.number == nil then vim.wo[win].number = false end
    if opts.relativenumber == false or opts.relativenumber == nil then vim.wo[win].relativenumber = false end
    if opts.signcolumn ~= nil then vim.wo[win].signcolumn = opts.signcolumn end
    if opts.cursorline ~= nil then vim.wo[win].cursorline = opts.cursorline end
    if opts.winhighlight then vim.wo[win].winhighlight = opts.winhighlight end

    local close_keys = opts.close_keys
    if close_keys == nil then close_keys = { "q", "<Esc>" } end
    local function do_close()
        if vim.api.nvim_win_is_valid(win) then
            pcall(vim.api.nvim_win_close, win, true)
        end
    end
    for _, key in ipairs(close_keys) do
        vim.keymap.set("n", key, do_close, { buffer = buf, nowait = true, silent = true })
    end

    if opts.on_close then
        local group = vim.api.nvim_create_augroup("PoorCLIFloat_" .. tostring(win), { clear = true })
        vim.api.nvim_create_autocmd("WinClosed", {
            group = group,
            pattern = tostring(win),
            once = true,
            callback = function()
                pcall(opts.on_close)
                pcall(vim.api.nvim_del_augroup_by_id, group)
            end,
        })
    end

    return win
end

function M.open_lines(lines, opts)
    opts = opts or {}
    local buf = vim.api.nvim_create_buf(false, true)
    vim.bo[buf].buftype = "nofile"
    vim.bo[buf].bufhidden = opts.bufhidden or "wipe"
    vim.bo[buf].swapfile = false
    if opts.filetype then vim.bo[buf].filetype = opts.filetype end
    if opts.name then pcall(vim.api.nvim_buf_set_name, buf, opts.name) end
    vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines or {})
    if opts.modifiable == false then
        vim.bo[buf].modifiable = false
    end
    local win = M.open(buf, opts)
    return buf, win
end

function M.is_open(win)
    return win and vim.api.nvim_win_is_valid(win)
end

return M
