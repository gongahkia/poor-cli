-- poor-cli/pickers.lua
-- Thin wrapper over snacks.pick. snacks.nvim is a hard dependency (enforced
-- in init.lua::setup), so this module no longer dispatches to
-- telescope / fzf-lua / vim.ui.select.
--
-- pickers.pick(items, opts)
-- items: { { id, label, preview, data }... }
-- opts:
--   title: picker title/prompt.
--   on_pick(data, item): called with selected item.data, or item when data is nil.
--   preview: nil/true uses item.preview, false disables preview, function(item) returns preview text.
--   layout: forwarded to snacks.pick.
--   multi: enable multi-select.
--   keys: map of key -> function(data, item), forwarded as snacks actions.

local M = {}

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

function M.pick(items, opts)
    opts = opts or {}
    items = items or {}
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
    return "snacks"
end

function M.backend() return "snacks" end
function M.detect() return "snacks" end

-- setup() intentionally removed: picker backend is reported via
-- `:PoorCLIConfig picker-backend`. M.pick, M.backend, M.detect remain.
function M.setup() end

function M._reset_for_tests() end

return M
