local M = {}

M.plugin_modules = {
    "poor-cli",
    "poor-cli.rpc",
}

function M.reset_modules(modules)
    for _, name in ipairs(modules or M.plugin_modules) do
        package.loaded[name] = nil
    end
end

function M.reset_runtime_state()
    vim.g.poor_cli_test = true
    M.reset_modules()
end

function M.cleanup_buffers()
    for _, buf in ipairs(vim.api.nvim_list_bufs()) do
        if vim.api.nvim_buf_is_valid(buf) then
            local name = vim.api.nvim_buf_get_name(buf)
            if name:find("[poor-cli", 1, true) then
                for _, win in ipairs(vim.api.nvim_list_wins()) do
                    if vim.api.nvim_win_is_valid(win) and vim.api.nvim_win_get_buf(win) == buf then
                        local replacement = vim.api.nvim_create_buf(false, true)
                        pcall(vim.api.nvim_win_set_buf, win, replacement)
                    end
                end
                pcall(vim.api.nvim_buf_delete, buf, { force = true })
            end
        end
    end
end

vim.g.poor_cli_test = true
if type(before_each) == "function" then
    before_each(M.cleanup_buffers)
end

return M
