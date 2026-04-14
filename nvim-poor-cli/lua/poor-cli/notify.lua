local M = {
    _checked = false,
    _snacks = nil,
    _setup = false,
}

local function cfg()
    local ok, config = pcall(require, "poor-cli.config")
    if not ok or type(config.get) ~= "function" then return {} end
    local notifications = config.get("notifications")
    return type(notifications) == "table" and notifications or {}
end

local function group_name()
    local notifications = cfg()
    return notifications.group or notifications.group_name or notifications.groupName or "poor-cli"
end

function M.detect(force)
    if M._checked and not force then return M._snacks end
    M._checked = true
    local ok, snacks = pcall(require, "snacks")
    if ok and type(snacks) == "table" then
        M._snacks = snacks
        return snacks
    end
    M._snacks = nil
    return nil
end

local function route_snacks(snacks, msg, level, opts)
    if type(snacks.notify) == "function" then
        return pcall(snacks.notify, msg, level, opts)
    end
    if type(snacks.notifier) == "table" and type(snacks.notifier.notify) == "function" then
        return pcall(snacks.notifier.notify, msg, level, opts)
    end
    local global = rawget(_G, "Snacks")
    if type(global) == "table" then
        if type(global.notify) == "function" then
            return pcall(global.notify, msg, level, opts)
        end
        if type(global.notifier) == "table" and type(global.notifier.notify) == "function" then
            return pcall(global.notifier.notify, msg, level, opts)
        end
    end
    return false
end

function M.notify(msg, level, opts)
    level = level or vim.log.levels.INFO
    opts = opts or {}
    if level == vim.log.levels.ERROR then
        return vim.notify(msg, level, opts)
    end
    local notifications = cfg()
    local snacks = notifications.snacks == false and nil or M.detect(false)
    if snacks then
        local snack_opts = vim.tbl_extend("keep", vim.deepcopy(opts), { group = group_name() })
        local ok, result = route_snacks(snacks, msg, level, snack_opts)
        if ok then return result end
    end
    return vim.notify(msg, level, opts)
end

function M.setup()
    if M._setup then return end
    M._setup = true
    M.detect(true)
    local group = vim.api.nvim_create_augroup("PoorCLINotify", { clear = true })
    vim.api.nvim_create_autocmd("VimEnter", {
        group = group,
        callback = function()
            M.detect(true)
            local ok, dashboard = pcall(require, "poor-cli.snacks_dashboard")
            if ok and type(dashboard.setup) == "function" then dashboard.setup() end
        end,
    })
end

function M._reset()
    M._checked = false
    M._snacks = nil
    M._setup = false
end

return M
