local M = {}

local state = {
    calls = {},
    responses = {},
    running = false,
}

local function copy(value)
    if type(value) ~= "table" then return value end
    local out = {}
    for key, item in pairs(value) do
        out[key] = copy(item)
    end
    return out
end

local function method_from_key(key)
    return tostring(key):gsub("_", ".")
end

function M.reset()
    state.calls = {}
    state.responses = {}
    state.running = false
end

function M.queue_response(result, err)
    table.insert(state.responses, { result = result, err = err })
end

function M.calls()
    return state.calls
end

function M.last_call()
    return state.calls[#state.calls]
end

function M.request(method, params, callback)
    local call = {
        id = #state.calls + 1,
        method = method,
        params = copy(params or {}),
    }
    table.insert(state.calls, call)
    local response = table.remove(state.responses, 1)
    if callback and response then
        callback(copy(response.result), copy(response.err))
    end
    return call.id
end

function M.request_sync(method, params)
    local result, err
    M.request(method, params, function(res, rpc_err)
        result = res
        err = rpc_err
    end)
    return result, err
end

function M.assert_called(method, params)
    for _, call in ipairs(state.calls) do
        if call.method == method and (params == nil or vim.deep_equal(call.params, params)) then
            return call
        end
    end
    error("expected RPC call " .. tostring(method), 2)
end

function M.create(extra)
    local rpc = {
        request = M.request,
        request_sync = M.request_sync,
        format_error = function(err)
            if type(err) == "table" then return err.message or vim.inspect(err) end
            return tostring(err)
        end,
        is_running = function() return state.running end,
        start = function()
            state.running = true
            return true
        end,
        stop = function()
            state.running = false
        end,
        initialize = function(callback)
            if callback then callback({ ok = true }, nil) end
        end,
        get_status = function()
            return state.running and "running" or "stopped"
        end,
        cancel_request = function(id, err)
            table.insert(state.calls, { id = #state.calls + 1, method = "poor-cli/cancelRequest", params = { id = id, err = err } })
            return true
        end,
    }
    setmetatable(rpc, {
        __index = function(_, key)
            return function(params, callback)
                return M.request(method_from_key(key), params or {}, callback)
            end
        end,
    })
    for key, value in pairs(extra or {}) do
        rpc[key] = value
    end
    return rpc
end

function M.install(extra)
    M.reset()
    local rpc = M.create(extra)
    package.loaded["poor-cli.rpc"] = rpc
    return rpc
end

return M
