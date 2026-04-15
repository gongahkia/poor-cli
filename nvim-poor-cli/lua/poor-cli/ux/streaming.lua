-- poor-cli/ux/streaming.lua
-- virt_text banner at the top of the chat buffer while a stream is active:
--   [streaming... press q to cancel]
-- listens to PoorCLIChatStreaming User events and chat module state.

local M = {}

M.ns = vim.api.nvim_create_namespace("poor-cli-ux-streaming")

local function banner_text()
    return { { "▶ streaming… press q to cancel", "WarningMsg" } }
end

local function place(buf)
    if not buf or not vim.api.nvim_buf_is_valid(buf) then return end
    vim.api.nvim_buf_clear_namespace(buf, M.ns, 0, -1)
    pcall(vim.api.nvim_buf_set_extmark, buf, M.ns, 0, 0, {
        virt_text = banner_text(),
        virt_text_pos = "right_align",
        priority = 200,
    })
end

local function clear(buf)
    if not buf or not vim.api.nvim_buf_is_valid(buf) then return end
    vim.api.nvim_buf_clear_namespace(buf, M.ns, 0, -1)
end

function M.refresh()
    local chat = require("poor-cli.chat")
    if not chat.buf then return end
    if chat.active_stream then place(chat.buf) else clear(chat.buf) end
end

function M.install()
    local group = vim.api.nvim_create_augroup("poor-cli-ux-streaming", { clear = true })
    vim.api.nvim_create_autocmd("User", {
        group = group,
        pattern = { "PoorCLIStreamStart", "PoorCLIStreamEnd", "PoorCLIStreamingStart", "PoorCLIStreamingEnd", "PoorCLIChatStreaming" },
        callback = function() vim.schedule(M.refresh) end,
    })
    -- poll fallback every 1s while nvim idle so it reflects actual state even if events are missed
    local timer = vim.uv.new_timer()
    if timer then
        timer:start(1000, 1000, vim.schedule_wrap(M.refresh))
        M._timer = timer
    end
end

return M
