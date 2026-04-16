-- poor-cli/integrations/trouble.lua

local diagnostics = require("poor-cli.diagnostics")

local M = {}

M.mode_name = "poor-cli"

local function as_item(diag)
    local item = {
        source = M.mode_name,
        buf = diag.bufnr,
        filename = diag.filename,
        pos = { (diag.lnum or 0) + 1, diag.col or 0 },
        end_pos = {
            diag.end_lnum and (diag.end_lnum + 1) or nil,
            diag.end_col,
        },
        item = diag,
    }
    local ok, trouble_item = pcall(require, "trouble.item")
    if ok and type(trouble_item.new) == "function" then
        return trouble_item.new(item)
    end
    return item
end

local function get_buf(ctx)
    local opts = ctx and ctx.opts or {}
    local filter = type(opts.filter) == "table" and opts.filter or {}
    local buf = filter.buf
    if buf == 0 then
        buf = ctx and ctx.main and ctx.main.buf or nil
    end
    return buf
end

function M.refresh()
    local trouble = require("trouble")
    if type(trouble.refresh) == "function" then
        pcall(trouble.refresh, M.mode_name)
    end
end

M.source = {
    highlights = {
        Message = "TroubleText",
        ItemSource = "Comment",
    },
    get = function(cb, ctx)
        local opts = { namespace = diagnostics.ns }
        local buf = get_buf(ctx)
        local raw = buf and vim.diagnostic.get(buf, opts) or vim.diagnostic.get(nil, opts)
        local items = vim.tbl_map(as_item, raw)
        cb(items)
    end,
}

M.config = {
    modes = {
        ["poor-cli"] = {
            desc = "poor-cli suggestions",
            source = "poor-cli",
            events = {
                "DiagnosticChanged",
                "User PoorCLISuggestionsChanged",
                "User PoorCLITurnEnded",
            },
            groups = {
                { "directory" },
                { "filename", format = "{file_icon} {basename} {count}" },
            },
            sort = { "filename", "pos", "message" },
            format = "{severity_icon} {message:md} {item.source} {pos}",
        },
    },
}

function M.source.setup()
    local group = vim.api.nvim_create_augroup("PoorCLITrouble", { clear = true })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = {
            "PoorCLISuggestionsChanged",
            "PoorCLITurnEnded",
        },
        callback = M.refresh,
    })
    vim.api.nvim_create_autocmd("DiagnosticChanged", {
        group = group,
        callback = M.refresh,
    })
end

local function source_without_config()
    local source = vim.tbl_extend("force", M.source, {})
    source.config = nil
    return source
end

local function register_source()
    local ok, sources = pcall(require, "trouble.sources")
    if not ok or type(sources.register) ~= "function" then
        return false
    end
    if sources.sources and sources.sources[M.mode_name] then
        return true
    end
    local registered = pcall(sources.register, M.mode_name, source_without_config())
    return registered
end

local function trouble_command_exists()
    return vim.api.nvim_get_commands({}).Trouble ~= nil
end

function M.setup()
    local trouble = require("trouble")
    local configured = trouble_command_exists()
    local defaulted = false
    if configured then
        local ok_config, trouble_config = pcall(require, "trouble.config")
        if ok_config and type(trouble_config.defaults) == "function" then
            defaulted = pcall(trouble_config.defaults, M.config)
        end
    end
    if (not configured or not defaulted) and type(trouble.setup) == "function" then
        pcall(trouble.setup, M.config)
    end

    local registered = register_source()

    M._registered = registered
    return true
end

return M
