local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("overseer bridge", function()
    local bridge
    local created
    local cancels
    local saved_preload

    local function fake_task(opts)
        local task = {
            id = #created + 1,
            opts = opts,
            name = opts.name,
            metadata = opts.metadata or {},
            status = "PENDING",
            outputs = {},
            subscribers = {},
        }
        task.strategy = {
            task = task,
            send_output = function(_, text)
                table.insert(task.outputs, text)
            end,
            send_exit = function(_, code)
                task.status = code == 0 and "SUCCESS" or "FAILURE"
                task:dispatch("on_status", task.status)
                task:dispatch("on_complete", task.status, task.result)
            end,
        }
        function task:start()
            self.status = "RUNNING"
            self:dispatch("on_status", self.status)
            return true
        end
        function task:stop()
            self.status = "CANCELED"
            self:dispatch("on_status", self.status)
            self:dispatch("on_complete", self.status, self.result)
            return true
        end
        function task:is_running() return self.status == "RUNNING" end
        function task:subscribe(event, cb)
            self.subscribers[event] = self.subscribers[event] or {}
            table.insert(self.subscribers[event], cb)
        end
        function task:dispatch(event, ...)
            for _, cb in ipairs(self.subscribers[event] or {}) do cb(self, ...) end
        end
        return task
    end

    local function install_overseer()
        created = {}
        package.preload["overseer"] = function()
            return {
                new_task = function(opts)
                    local task = fake_task(opts)
                    table.insert(created, task)
                    return task
                end,
            }
        end
    end

    before_each(function()
        created = {}
        cancels = {}
        saved_preload = package.preload["overseer"]
        package.loaded["poor-cli.integrations.overseer"] = nil
        package.loaded["overseer"] = nil
        package.loaded["poor-cli.tasks"] = {
            get = function(_, cb) cb({ task = { taskId = "task-1", status = "running" } }, nil) end,
            cancel = function(params, cb)
                table.insert(cancels, params)
                if cb then cb({ ok = true }, nil) end
            end,
        }
    end)

    after_each(function()
        if bridge then bridge._reset() end
        package.preload["overseer"] = saved_preload
        package.loaded["overseer"] = nil
        package.loaded["poor-cli.tasks"] = nil
        package.loaded["poor-cli.integrations.overseer"] = nil
        pcall(vim.api.nvim_del_augroup_by_name, "PoorCLIOverseer")
    end)

    it("test_noop_when_overseer_absent", function()
        package.preload["overseer"] = function() error("no overseer") end
        bridge = require("poor-cli.integrations.overseer")
        assert.is_false(bridge.setup())
        local ok, autocmds = pcall(vim.api.nvim_get_autocmds, { group = "PoorCLIOverseer" })
        assert.is_false(ok)
        assert.truthy(tostring(autocmds):find("PoorCLIOverseer", 1, true))
    end)

    it("test_task_mirrored_to_overseer", function()
        install_overseer()
        bridge = require("poor-cli.integrations.overseer")
        bridge.poll_interval_ms = 0
        assert.is_true(bridge.setup())
        vim.api.nvim_exec_autocmds("User", {
            pattern = "PoorCLITaskStarted",
            data = { task = { taskId = "task-1", title = "bench", status = "running" } },
        })
        assert.are.equal(1, #created)
        assert.are.equal("RUNNING", created[1].status)
        assert.are.equal("task-1", created[1].metadata.poor_cli_task_id)
        vim.api.nvim_exec_autocmds("User", {
            pattern = "PoorCLITaskFinished",
            data = { task = { taskId = "task-1", title = "bench", status = "completed" } },
        })
        assert.are.equal("SUCCESS", created[1].status)
    end)

    it("pipes_tool_stream_chunks_to_output", function()
        install_overseer()
        bridge = require("poor-cli.integrations.overseer")
        bridge.poll_interval_ms = 0
        bridge.setup()
        bridge.handle_started({ task = { taskId = "task-1", title = "tests", status = "running" } })
        assert.is_true(bridge.handle_tool_chunk({ request_id = "task-task-1", chunk = "line 1\n" }))
        assert.are.equal("line 1\n", created[1].outputs[1])
    end)

    it("propagates_overseer_stop_to_poor-cli_cancel", function()
        install_overseer()
        bridge = require("poor-cli.integrations.overseer")
        bridge.poll_interval_ms = 0
        bridge.setup()
        bridge.handle_started({ task = { taskId = "task-1", title = "deploy", status = "running" } })
        created[1]:stop()
        assert.are.equal(1, #cancels)
        assert.are.equal("task-1", cancels[1].taskId)
    end)

    it("propagates_poor-cli_cancel_to_overseer_stop", function()
        install_overseer()
        bridge = require("poor-cli.integrations.overseer")
        bridge.poll_interval_ms = 0
        bridge.setup()
        bridge.handle_started({ task = { taskId = "task-1", title = "deploy", status = "running" } })
        bridge.handle_finished({ task = { taskId = "task-1", title = "deploy", status = "cancelled" } })
        assert.are.equal("CANCELED", created[1].status)
        assert.are.equal(0, #cancels)
    end)
end)
