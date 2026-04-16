local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
local runtime = root .. "/.test-runtime"
vim.fn.mkdir(runtime .. "/data", "p")
vim.fn.mkdir(runtime .. "/state", "p")
vim.fn.mkdir(runtime .. "/cache", "p")
vim.fn.mkdir(runtime .. "/config", "p")
vim.env.XDG_DATA_HOME = runtime .. "/data"
vim.env.XDG_STATE_HOME = runtime .. "/state"
vim.env.XDG_CACHE_HOME = runtime .. "/cache"
vim.env.XDG_CONFIG_HOME = runtime .. "/config"
vim.opt.runtimepath:prepend(root)
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. root .. "/tests/?.lua;" .. root .. "/?.lua;" .. package.path
local plenary_dir = os.getenv("PLENARY_DIR") or runtime .. "/site/pack/test/start/plenary.nvim"
vim.opt.runtimepath:append(plenary_dir)
local snacks_dir = os.getenv("SNACKS_DIR") or runtime .. "/site/pack/test/start/snacks.nvim"
vim.opt.runtimepath:append(snacks_dir)
package.path = snacks_dir .. "/lua/?.lua;" .. snacks_dir .. "/lua/?/init.lua;" .. package.path
vim.cmd("runtime plugin/plenary.vim")
require("plenary.busted")
pcall(require, "tests.init")
