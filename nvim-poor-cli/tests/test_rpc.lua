-- test_rpc.lua
-- Tests for poor-cli RPC client functionality

local rpc = require("poor-cli.rpc")
local config = require("poor-cli.config")

describe("poor-cli.rpc", function()
    before_each(function()
        -- Reset RPC state before each test
        if rpc.is_running() then
            rpc.stop()
        end
        rpc.request_id = 0
        rpc.pending = {}
        rpc.pending_timers = {}
        rpc.buffer = ""
        rpc.manual_stop = false
        rpc.restart_attempt = 0
        if rpc.restart_timer then
            rpc.restart_timer:stop()
            rpc.restart_timer:close()
            rpc.restart_timer = nil
        end
        config.config.multiplayer = {
            enabled = false,
            url = nil,
            room = nil,
            token = nil,
        }
    end)
    
    after_each(function()
        if rpc.is_running() then
            rpc.stop()
        end
    end)
    
    describe("state management", function()
        it("should start with no job running", function()
            assert.is_nil(rpc.job_id)
            assert.is_false(rpc.is_running())
        end)
        
        it("should have empty pending requests initially", function()
            assert.are.same({}, rpc.pending)
        end)
        
        it("should have request_id starting at 0", function()
            assert.are.equal(0, rpc.request_id)
        end)
    end)

    describe("command resolution", function()
        it("should resolve default server command when multiplayer is disabled", function()
            config.config.multiplayer = { enabled = false }
            local cmd, err = rpc.resolve_server_command()
            assert.is_nil(err)
            assert.are.equal(config.get("server_cmd"), cmd)
        end)

        it("should resolve bridge command when multiplayer is enabled", function()
            config.config.multiplayer = {
                enabled = true,
                url = "wss://example.test/rpc",
                room = "dev",
                token = "tok-123",
            }
            local cmd, err = rpc.resolve_server_command()
            assert.is_nil(err)
            assert.are.same({
                "poor-cli-server",
                "--bridge",
                "--url",
                "wss://example.test/rpc",
                "--room",
                "dev",
                "--token",
                "tok-123",
            }, cmd)
        end)

        it("should error when multiplayer config is incomplete", function()
            config.config.multiplayer = {
                enabled = true,
                url = "wss://example.test/rpc",
            }
            local cmd, err = rpc.resolve_server_command()
            assert.is_nil(cmd)
            assert.is_not_nil(err)
        end)
    end)
    
    describe("message parsing", function()
        it("should parse a complete JSON-RPC message", function()
            local json_body = '{"jsonrpc":"2.0","id":1,"result":{"success":true}}'
            rpc.buffer = "Content-Length: " .. #json_body .. "\r\n\r\n" .. json_body
            
            local message = rpc.parse_message()
            
            assert.is_not_nil(message)
            assert.are.equal("2.0", message.jsonrpc)
            assert.are.equal(1, message.id)
            assert.is_not_nil(message.result)
            assert.is_true(message.result.success)
        end)
        
        it("should return nil for incomplete message", function()
            rpc.buffer = "Content-Length: 50\r\n\r\n{\"incomplete\":"
            
            local message = rpc.parse_message()
            
            assert.is_nil(message)
        end)
        
        it("should return nil for missing header", function()
            rpc.buffer = '{"jsonrpc":"2.0","id":1}'
            
            local message = rpc.parse_message()
            
            assert.is_nil(message)
        end)
        
        it("should handle multiple messages in buffer", function()
            local json1 = '{"jsonrpc":"2.0","id":1,"result":"first"}'
            local json2 = '{"jsonrpc":"2.0","id":2,"result":"second"}'
            rpc.buffer = "Content-Length: " .. #json1 .. "\r\n\r\n" .. json1 ..
                         "Content-Length: " .. #json2 .. "\r\n\r\n" .. json2
            
            local message1 = rpc.parse_message()
            assert.are.equal(1, message1.id)
            assert.are.equal("first", message1.result)
            
            local message2 = rpc.parse_message()
            assert.are.equal(2, message2.id)
            assert.are.equal("second", message2.result)
        end)
    end)
    
    describe("request handling", function()
        it("should increment request_id for each request", function()
            -- Mock job_id to allow request
            rpc.job_id = 1
            
            -- Mock chansend to prevent actual sending
            local original_chansend = vim.fn.chansend
            vim.fn.chansend = function() return 1 end
            
            local id1 = rpc.request("test", {}, function() end)
            local id2 = rpc.request("test", {}, function() end)
            local id3 = rpc.request("test", {}, function() end)
            
            assert.are.equal(1, id1)
            assert.are.equal(2, id2)
            assert.are.equal(3, id3)
            
            -- Restore
            vim.fn.chansend = original_chansend
            rpc.job_id = nil
        end)
        
        it("should store callback in pending", function()
            rpc.job_id = 1
            
            local original_chansend = vim.fn.chansend
            vim.fn.chansend = function() return 1 end
            
            local callback = function() end
            local id = rpc.request("test", {}, callback)
            
            assert.are.equal(callback, rpc.pending[id])
            
            vim.fn.chansend = original_chansend
            rpc.job_id = nil
        end)
        
        it("should call callback with error when not running", function()
            local error_received = nil
            rpc.request("test", {}, function(result, err)
                error_received = err
            end)
            
            assert.is_not_nil(error_received)
            assert.is_not_nil(error_received.message)
        end)

        it("should call callback with timeout error when request expires", function()
            rpc.job_id = 1

            local original_chansend = vim.fn.chansend
            vim.fn.chansend = function()
                return 1
            end

            local original_defer_fn = vim.defer_fn
            local timer_callback = nil
            local timer_delay = nil
            vim.defer_fn = function(cb, delay)
                timer_callback = cb
                timer_delay = delay
                return {
                    stop = function() end,
                    close = function() end,
                }
            end

            local original_timeout = config.config.request_timeout
            config.config.request_timeout = 25

            local timeout_error = nil
            local request_id = rpc.request("test", {}, function(_result, err)
                timeout_error = err
            end)

            assert.are.equal(25, timer_delay)
            timer_callback()

            assert.is_nil(rpc.pending[request_id])
            assert.is_not_nil(timeout_error)
            assert.are.equal(-32001, timeout_error.code)
            assert.matches("timed out", timeout_error.message)

            config.config.request_timeout = original_timeout
            vim.defer_fn = original_defer_fn
            vim.fn.chansend = original_chansend
            rpc.job_id = nil
        end)
    end)
    
    describe("response handling", function()
        it("should call callback on successful response", function()
            local result_received = nil
            rpc.pending[1] = function(result, err)
                result_received = result
            end
            
            rpc.handle_response({
                jsonrpc = "2.0",
                id = 1,
                result = { data = "test" },
            })
            
            assert.is_not_nil(result_received)
            assert.are.equal("test", result_received.data)
        end)
        
        it("should call callback with error on error response", function()
            local error_received = nil
            rpc.pending[1] = function(result, err)
                error_received = err
            end
            
            rpc.handle_response({
                jsonrpc = "2.0",
                id = 1,
                error = { code = -32600, message = "Invalid Request" },
            })
            
            assert.is_not_nil(error_received)
            assert.are.equal(-32600, error_received.code)
        end)
        
        it("should remove callback from pending after handling", function()
            rpc.pending[1] = function() end
            
            rpc.handle_response({
                jsonrpc = "2.0",
                id = 1,
                result = {},
            })
            
            assert.is_nil(rpc.pending[1])
        end)
        
        it("should handle notification (no id)", function()
            -- Notifications should not throw errors
            assert.has_no.errors(function()
                rpc.handle_response({
                    jsonrpc = "2.0",
                    method = "poor-cli/streamChunk",
                    params = { chunk = "test", done = false },
                })
            end)
        end)
    end)
end)
