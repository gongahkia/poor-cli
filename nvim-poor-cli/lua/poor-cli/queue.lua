local rpc = require("poor-cli.rpc")
local M = {}
M.items = {}
M.processing = false

function M.enqueue(message)
    table.insert(M.items, message)
    vim.notify(("[poor-cli] queued (%d pending)"):format(#M.items), vim.log.levels.INFO)
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
    vim.notify(("[poor-cli] queue cleared (%d removed)"):format(count), vim.log.levels.INFO)
end

function M.status()
    return { pending = #M.items, processing = M.processing }
end

function M.setup() end

return M
