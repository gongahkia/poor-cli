-- Walk minimal init.lua example
-- Place at ~/.config/walk/init.lua

walk.bind_key("terminal", "ctrl+shift+t", "new_tab")
walk.bind_key("terminal", "ctrl+shift+d", "split_horizontal")
walk.bind_key("terminal", "ctrl+d", "split_vertical")

walk.register_command("save_demo", "save_session:demo")
walk.register_command("load_demo", "load_session:demo")
walk.bind_key("terminal", "ctrl+shift+s", "save_demo")
walk.bind_key("terminal", "ctrl+shift+r", "load_demo")
