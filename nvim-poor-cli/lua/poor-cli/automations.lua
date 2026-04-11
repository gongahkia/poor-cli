local rpc = require("poor-cli.rpc")
local M = {}

function M.create(params, callback) return rpc.request("poor-cli/createAutomation", params or {}, callback) end
function M.list(params, callback) return rpc.request("poor-cli/listAutomations", params or {}, callback) end
function M.get(params, callback) return rpc.request("poor-cli/getAutomation", params or {}, callback) end
function M.set_enabled(params, callback) return rpc.request("poor-cli/setAutomationEnabled", params or {}, callback) end
function M.run_now(params, callback) return rpc.request("poor-cli/runAutomationNow", params or {}, callback) end
function M.run_due(params, callback) return rpc.request("poor-cli/runDueAutomations", params or {}, callback) end
function M.get_history(params, callback) return rpc.request("poor-cli/getAutomationHistory", params or {}, callback) end
function M.replay(params, callback) return rpc.request("poor-cli/replayAutomation", params or {}, callback) end

local function open_scratch(title, content, filetype)
    local buf = vim.api.nvim_create_buf(false, true)
    vim.bo[buf].buftype = "nofile"
    vim.bo[buf].bufhidden = "wipe"
    vim.bo[buf].swapfile = false
    vim.bo[buf].filetype = filetype or "markdown"
    vim.api.nvim_buf_set_name(buf, title)
    vim.api.nvim_buf_set_lines(buf, 0, -1, false, vim.split(content, "\n", { plain = true }))
    vim.cmd("botright split")
    vim.api.nvim_win_set_buf(0, buf)
    return buf
end

local function format_auto(a)
    local enabled = a.enabled and "on" or "off"
    return string.format("%s  [%s]  %s  %s", tostring(a.id or a.automationId or "?"), enabled, tostring(a.schedule or ""), tostring(a.name or a.title or ""))
end

function M.open_picker()
    local has_telescope, pickers = pcall(require, "telescope.pickers")
    if not has_telescope then vim.notify("[poor-cli] telescope.nvim required", vim.log.levels.ERROR); return end
    local finders = require("telescope.finders")
    local conf = require("telescope.config").values
    local actions = require("telescope.actions")
    local action_state = require("telescope.actions.state")
    local previewers = require("telescope.previewers")
    if not rpc.is_running() then vim.notify("[poor-cli] server not running", vim.log.levels.WARN); return end
    rpc.request("poor-cli/listAutomations", {}, function(result, err)
        vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local autos = (result or {}).automations or {}
            if #autos == 0 then vim.notify("[poor-cli] no automations", vim.log.levels.INFO); return end
            pickers.new({}, {
                prompt_title = "poor-cli automations",
                finder = finders.new_table({
                    results = autos,
                    entry_maker = function(a)
                        local id = tostring(a.id or a.automationId or "?")
                        return { value = a, ordinal = id .. " " .. tostring(a.name or a.title or ""), display = format_auto(a) }
                    end,
                }),
                sorter = conf.generic_sorter({}),
                previewer = previewers.new_buffer_previewer({
                    title = "Automation Preview",
                    define_preview = function(self, entry)
                        local a = entry.value
                        vim.api.nvim_buf_set_lines(self.state.bufnr, 0, -1, false, {
                            "ID: " .. tostring(a.id or a.automationId or "?"),
                            "Name: " .. tostring(a.name or a.title or ""),
                            "Schedule: " .. tostring(a.schedule or ""),
                            "Enabled: " .. tostring(a.enabled or false),
                            "Prompt: " .. tostring(a.prompt or ""),
                            "Created: " .. tostring(a.createdAt or "-"),
                        })
                    end,
                }),
                attach_mappings = function(prompt_bufnr)
                    actions.select_default:replace(function()
                        actions.close(prompt_bufnr)
                        local sel = action_state.get_selected_entry()
                        if sel then
                            local a = sel.value
                            local id = tostring(a.id or a.automationId or "")
                            vim.ui.select({ "enable", "disable", "run", "history", "replay" }, { prompt = "Action for " .. id .. ":" }, function(choice)
                                if not choice then return end
                                local map = { enable = { "setAutomationEnabled", { automationId = id, enabled = true } }, disable = { "setAutomationEnabled", { automationId = id, enabled = false } }, run = { "runAutomationNow", { automationId = id } }, history = { "getAutomationHistory", { automationId = id } }, replay = { "replayAutomation", { automationId = id } } }
                                local m = map[choice]
                                rpc.request("poor-cli/" .. m[1], m[2], function(r, e) vim.schedule(function()
                                    if e then vim.notify("[poor-cli] " .. vim.inspect(e), vim.log.levels.ERROR)
                                    elseif choice == "history" then open_scratch("[poor-cli automation history]", vim.inspect(r), "lua")
                                    else vim.notify("[poor-cli] automation " .. choice .. " ok", vim.log.levels.INFO) end
                                end) end)
                            end)
                        end
                    end)
                    return true
                end,
            }):find()
        end)
    end)
end

function M.setup()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCliAutomations", function()
        M.list({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local autos = (result or {}).automations or {}
            local lines = { "# automations", "" }
            for _, a in ipairs(autos) do table.insert(lines, format_auto(a)) end
            if #autos == 0 then table.insert(lines, "no automations found") end
            open_scratch("[poor-cli automations]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { desc = "List automations" })
    create_command("PoorCliAutomationCreate", function()
        vim.ui.input({ prompt = "Automation name: " }, function(name)
            if not name or name == "" then return end
            vim.ui.input({ prompt = "Schedule (cron): " }, function(schedule)
                if not schedule or schedule == "" then return end
                vim.ui.input({ prompt = "Prompt: " }, function(prompt)
                    if not prompt or prompt == "" then return end
                    M.create({ name = name, schedule = schedule, prompt = prompt }, function(_, err) vim.schedule(function()
                        if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
                        else vim.notify("[poor-cli] automation created", vim.log.levels.INFO) end
                    end) end)
                end)
            end)
        end)
    end, { desc = "Create automation" })
    create_command("PoorCliAutomationEnable", function(opts)
        M.set_enabled({ automationId = opts.args, enabled = true }, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] automation enabled", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Enable automation" })
    create_command("PoorCliAutomationDisable", function(opts)
        M.set_enabled({ automationId = opts.args, enabled = false }, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] automation disabled", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Disable automation" })
    create_command("PoorCliAutomationRun", function(opts)
        M.run_now({ automationId = opts.args }, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] automation triggered", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Run automation now" })
    create_command("PoorCliAutomationHistory", function(opts)
        M.get_history({ automationId = opts.args }, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            open_scratch("[poor-cli automation history]", vim.inspect(result), "lua")
        end) end)
    end, { nargs = 1, desc = "Show automation history" })
    create_command("PoorCliAutomationReplay", function(opts)
        M.replay({ automationId = opts.args }, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] automation replayed", vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Replay automation" })
    create_command("PoorCliAutomationsPicker", function() M.open_picker() end, { desc = "Browse automations with Telescope" })
end

return M
