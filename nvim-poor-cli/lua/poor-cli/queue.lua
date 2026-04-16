local rpc = require("poor-cli.rpc")
local M = {}
M.items = {}
M.processing = false

function M.enqueue(message)
    table.insert(M.items, message)
    require("poor-cli.notify").notify(("[poor-cli] queued (%d pending)"):format(#M.items), vim.log.levels.INFO)
    if not M.processing then M.process_next() end
end

function M.process_next()
    if #M.items == 0 then
        M.processing = false
        return
    end
    M.processing = true
    local msg = table.remove(M.items, 1)
    local chat = require("poor-cli.chat")
    chat.open()
    chat.send(msg, function()
        vim.schedule(function() M.process_next() end)
    end)
end

function M.clear()
    local count = #M.items
    M.items = {}
    M.processing = false
    require("poor-cli.notify").notify(("[poor-cli] queue cleared (%d removed)"):format(count), vim.log.levels.INFO)
end

function M.status()
    return { pending = #M.items, processing = M.processing }
end

function M.list()
    local copy = {}
    for i, v in ipairs(M.items) do copy[i] = v end
    return copy
end

function M.remove_at(idx)
    if idx >= 1 and idx <= #M.items then
        return table.remove(M.items, idx)
    end
    return nil
end

function M.open_picker()
    local pickers = require("poor-cli.pickers")
    local items = {}
    for i, msg in ipairs(M.items) do
        items[#items + 1] = {
            id = tostring(i),
            label = string.format("%d. %s", i, tostring(msg):sub(1, 80)),
            preview = tostring(msg),
            data = { idx = i, text = msg },
        }
    end
    if #items == 0 then
        require("poor-cli.notify").notify("[poor-cli] queue empty", vim.log.levels.INFO)
        return
    end
    pickers.pick(items, { title = string.format("poor-cli queue (%d pending)", #M.items), on_pick = function(d)
        vim.ui.select({ "remove", "show" }, { prompt = "Action for queued item:" }, function(choice)
            if choice == "remove" then
                M.remove_at(d.idx)
                require("poor-cli.notify").notify("[poor-cli] removed from queue", vim.log.levels.INFO)
            elseif choice == "show" then
                local float_win = require("poor-cli.float_win")
                float_win.open_lines(vim.split(tostring(d.text), "\n", { plain = true }), {
                    filetype = "markdown",
                    title = " queued message ",
                    width = 0.6, height = 0.5, position = "center",
                })
            end
        end)
    end })
end

function M.setup()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCLIQueue", function() M.open_picker() end, { desc = "Browse queued prompts" })
    create_command("PoorCLIQueueClear", function() M.clear() end, { desc = "Clear prompt queue" })
end

return M
