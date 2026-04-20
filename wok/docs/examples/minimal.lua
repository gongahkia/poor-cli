-- Wok minimal init.lua example
-- Place at ~/.config/wok/init.lua

wok.bind_key("terminal", "ctrl+shift+t", "new_tab")
wok.bind_key("terminal", "ctrl+shift+d", "split_horizontal")
wok.bind_key("terminal", "ctrl+d", "split_vertical")

wok.register_command("save_demo", "save_session:demo")
wok.register_command("load_demo", "load_session:demo")
wok.bind_key("terminal", "ctrl+shift+s", "save_demo")
wok.bind_key("terminal", "ctrl+shift+r", "load_demo")
