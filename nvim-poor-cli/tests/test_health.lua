local health = require("poor-cli.health")
local rpc = require("poor-cli.rpc")

describe("poor-cli.health", function()
    local original_health = nil
    local original_resolve = nil
    local original_status = nil
    local original_is_running = nil

    before_each(function()
        original_health = vim.health
        original_resolve = rpc.resolve_server_command
        original_status = rpc.get_status
        original_is_running = rpc.is_running
    end)

    after_each(function()
        vim.health = original_health
        rpc.resolve_server_command = original_resolve
        rpc.get_status = original_status
        rpc.is_running = original_is_running
    end)

    it("should report configured command and log path without errors", function()
        local entries = {}

        vim.health = {
            start = function(message)
                table.insert(entries, { level = "start", message = message })
            end,
            ok = function(message)
                table.insert(entries, { level = "ok", message = message })
            end,
            warn = function(message)
                table.insert(entries, { level = "warn", message = message })
            end,
            error = function(message)
                table.insert(entries, { level = "error", message = message })
            end,
            info = function(message)
                table.insert(entries, { level = "info", message = message })
            end,
        }

        rpc.resolve_server_command = function()
            return { "poor-cli-server", "--stdio" }, nil
        end
        rpc.get_status = function()
            return {
                state = "ready",
                provider_info = {
                    name = "gemini",
                    model = "gemini-2.5-pro",
                },
                last_error_message = "",
                last_stderr_excerpt = "",
            }
        end
        rpc.is_running = function()
            return true
        end

        assert.has_no.errors(function()
            health.check()
        end)

        local saw_log_info = false
        for _, entry in ipairs(entries) do
            if entry.level == "info" and entry.message:match("Server log file:") then
                saw_log_info = true
                break
            end
        end

        assert.is_true(saw_log_info)
    end)
end)
