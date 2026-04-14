-- poor-cli picker adapter.
--
-- pickers.pick(items, opts)
-- items: { { id, label, preview, data }... }
-- opts:
--   title: picker title/prompt.
--   on_pick(data, item): called with selected item.data, or item when data is nil.
--   preview: nil/true uses item.preview, false disables preview, function(item) returns preview text.
--   layout: backend-specific layout hint/table, forwarded best-effort.
--   multi: when true, backend multi-select is enabled where supported and on_pick gets data/item lists.
--   keys: map of key -> function(data, item), forwarded where backend exposes custom picker actions.
--   backend: optional one-shot backend override.
--   precedence: optional backend order; defaults to Snacks > Telescope > fzf-lua > vim.ui.select.

local M = {}

local default_precedence = { "snacks", "telescope", "fzf-lua", "native" }
local detected

local function clone(list)
    local out = {}
    for i, item in ipairs(list or {}) do out[i] = item end
    return out
end

local function backend_precedence(opts)
    if type(opts) == "table" and type(opts.precedence) == "table" then return clone(opts.precedence) end
    if type(vim.g.poor_cli_picker_precedence) == "table" then return clone(vim.g.poor_cli_picker_precedence) end
    return clone(default_precedence)
end

local function has(name)
    if name == "snacks" then return pcall(require, "snacks.picker") end
    if name == "telescope" then return pcall(require, "telescope.pickers") end
    if name == "fzf-lua" then return pcall(require, "fzf-lua") end
    return name == "native"
end

local function item_label(item)
    if type(item) ~= "table" then return tostring(item) end
    return tostring(item.label or item.name or item.id or item.value or "")
end

local function item_data(item)
    if type(item) == "table" and item.data ~= nil then return item.data end
    return item
end

local function preview_text(item, opts)
    if opts.preview == false then return nil end
    if type(opts.preview) == "function" then return opts.preview(item) end
    if type(item) == "table" then return item.preview end
    return nil
end

local function preview_lines(item, opts)
    local text = preview_text(item, opts)
    if type(text) == "table" then return text end
    return vim.split(tostring(text or ""), "\n", { plain = true })
end

local function is_list(value)
    local checker = vim.islist or vim.tbl_islist
    return checker and checker(value) or type(value) == "table"
end

local function apply_choice(items, opts)
    if opts.on_pick then opts.on_pick(item_data(items), items) end
end

local function apply_multi(items, opts)
    if not opts.on_pick then return end
    local data = {}
    for i, item in ipairs(items or {}) do data[i] = item_data(item) end
    opts.on_pick(data, items or {})
end

local function apply_multi_action(fn, items)
    local data = {}
    for i, item in ipairs(items or {}) do data[i] = item_data(item) end
    fn(data, items or {})
end

function M.detect(opts)
    if detected and not (opts and opts.precedence) then return detected end
    for _, backend in ipairs(backend_precedence(opts)) do
        if has(backend) then
            detected = backend
            return detected
        end
    end
    detected = "native"
    return detected
end

local function native_pick(items, opts)
    vim.ui.select(items, {
        prompt = opts.title or "poor-cli",
        format_item = item_label,
    }, function(item)
        if item then apply_choice(item, opts) end
    end)
end

local function telescope_selected(action_state, prompt_bufnr, opts)
    if opts.multi then
        local picker = action_state.get_current_picker(prompt_bufnr)
        local selection = picker and picker:get_multi_selection() or {}
        if #selection > 0 then
            local items = {}
            for _, entry in ipairs(selection) do items[#items + 1] = entry.value end
            return items
        end
    end
    local entry = action_state.get_selected_entry()
    return entry and entry.value or nil
end

local function telescope_pick(items, opts)
    local pickers = require("telescope.pickers")
    local finders = require("telescope.finders")
    local conf = require("telescope.config").values
    local actions = require("telescope.actions")
    local action_state = require("telescope.actions.state")
    local previewers = require("telescope.previewers")
    local picker_opts = {
        prompt_title = opts.title or "poor-cli",
        initial_mode = opts.initial_mode or "insert",
        finder = finders.new_table({
            results = items,
            entry_maker = function(item)
                return { value = item, ordinal = item_label(item), display = item_label(item) }
            end,
        }),
        sorter = conf.generic_sorter({}),
        attach_mappings = function(prompt_bufnr, map)
            local function run(fn)
                local selected = telescope_selected(action_state, prompt_bufnr, opts)
                actions.close(prompt_bufnr)
                if not selected then return end
                if opts.multi and is_list(selected) then
                    if fn then apply_multi_action(fn, selected) else apply_multi(selected, opts) end
                elseif fn then
                    fn(item_data(selected), selected)
                else
                    apply_choice(selected, opts)
                end
            end
            actions.select_default:replace(function() run(nil) end)
            for key, fn in pairs(opts.keys or {}) do
                map("i", key, function() run(fn) end)
                map("n", key, function() run(fn) end)
            end
            return true
        end,
    }
    if opts.preview ~= false then
        picker_opts.previewer = previewers.new_buffer_previewer({
            title = "Preview",
            define_preview = function(self, entry)
                vim.api.nvim_buf_set_lines(self.state.bufnr, 0, -1, false, preview_lines(entry and entry.value, opts))
            end,
        })
    end
    if type(opts.layout) == "table" then
        picker_opts.layout_config = opts.layout
    elseif type(opts.layout) == "string" then
        picker_opts.layout_strategy = opts.layout
    end
    pickers.new({}, picker_opts):find()
end

local function fzf_pick(items, opts)
    local fzf = require("fzf-lua")
    local labels, lookup = {}, {}
    for _, item in ipairs(items) do
        local label = item_label(item)
        labels[#labels + 1] = label
        lookup[label] = item
    end
    local fzf_opts = {
        prompt = (opts.title or "poor-cli") .. "> ",
        fzf_opts = opts.multi and { ["--multi"] = true } or nil,
        winopts = type(opts.layout) == "table" and opts.layout or nil,
        actions = {
            ["default"] = function(selected)
                local picked = {}
                for _, label in ipairs(selected or {}) do
                    if lookup[label] then picked[#picked + 1] = lookup[label] end
                end
                if opts.multi then apply_multi(picked, opts) elseif picked[1] then apply_choice(picked[1], opts) end
            end,
        },
    }
    if opts.preview ~= false then
        fzf_opts.preview = function(selected)
            local item = selected and lookup[selected[1]]
            return table.concat(preview_lines(item, opts), "\n")
        end
    end
    for key, fn in pairs(opts.keys or {}) do
        fzf_opts.actions[key] = function(selected)
            local picked = {}
            for _, label in ipairs(selected or {}) do
                if lookup[label] then picked[#picked + 1] = lookup[label] end
            end
            if opts.multi then apply_multi_action(fn, picked) elseif picked[1] then fn(item_data(picked[1]), picked[1]) end
        end
    end
    fzf.fzf_exec(labels, fzf_opts)
end

local function snacks_pick(items, opts)
    local snacks = require("snacks.picker")
    snacks.pick({
        title = opts.title or "poor-cli",
        items = items,
        layout = opts.layout,
        multi = opts.multi,
        format = function(item) return { { item_label(item) } } end,
        preview = opts.preview == false and nil or function(ctx)
            local lines = preview_lines(ctx.item, opts)
            if ctx.preview and ctx.preview.set_lines then
                ctx.preview:set_lines(lines)
            elseif ctx.buf then
                vim.api.nvim_buf_set_lines(ctx.buf, 0, -1, false, lines)
            end
        end,
        confirm = function(picker, item)
            local selected = item
            if opts.multi and picker then
                if type(picker.selected) == "function" then
                    selected = picker:selected()
                elseif type(picker.get_selected) == "function" then
                    selected = picker:get_selected()
                elseif type(picker.selected) == "table" then
                    selected = picker.selected
                end
            end
            if picker and picker.close then picker:close() end
            if opts.multi and type(selected) == "table" and is_list(selected) then
                apply_multi(selected, opts)
            elseif item then
                apply_choice(item, opts)
            end
        end,
        actions = opts.keys,
    })
end

local runners = {
    snacks = snacks_pick,
    telescope = telescope_pick,
    ["fzf-lua"] = fzf_pick,
    native = native_pick,
}

local function candidates(opts)
    local list = {}
    local seen = {}
    local function add(name)
        if name and not seen[name] then
            seen[name] = true
            list[#list + 1] = name
        end
    end
    add(opts.backend or detected or M.detect(opts))
    for _, backend in ipairs(backend_precedence(opts)) do add(backend) end
    add("native")
    return list
end

function M.pick(items, opts)
    opts = opts or {}
    items = items or {}
    for _, backend in ipairs(candidates(opts)) do
        if runners[backend] and has(backend) then
            local ok, err = pcall(runners[backend], items, opts)
            if ok then
                detected = backend
                return backend
            end
            require("poor-cli.notify").notify("[poor-cli] " .. backend .. " picker failed: " .. tostring(err), vim.log.levels.WARN)
        end
    end
    return nil
end

function M.backend()
    return M.detect()
end

function M.setup()
    pcall(vim.api.nvim_del_user_command, "PoorCLIPickerBackend")
    vim.api.nvim_create_user_command("PoorCLIPickerBackend", function()
        require("poor-cli.notify").notify("[poor-cli] picker backend: " .. M.backend(), vim.log.levels.INFO)
    end, { desc = "Show poor-cli picker backend" })
end

function M._reset_for_tests()
    detected = nil
end

return M
