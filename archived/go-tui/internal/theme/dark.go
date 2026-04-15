package theme

const (
	darkBase    = "#f4f4f5"
	darkSurface = "#111111"
	darkPanel   = "#1a1a1a"
	darkMuted   = "#585858"
	darkAccent  = "#89b4fa"
	darkWarn    = "#f9e2af"
	darkError   = "#f38ba8"
)

func Dark() Theme {
	return DarkWithCapability(DetectCapability())
}

func DarkWithCapability(caps Capability) Theme {
	return buildTheme("dark", caps, true, darkSpecs())
}

func darkSpecs() map[Token]styleSpec {
	return map[Token]styleSpec{
		TokenBase:              {foreground: darkBase},
		TokenMuted:             {foreground: darkMuted, faint: true},
		TokenBorder:            {foreground: darkMuted},
		TokenFocus:             {foreground: darkAccent, bold: true},
		TokenError:             {foreground: darkError, bold: true},
		TokenSuccess:           {foreground: "#a6e3a1", bold: true},
		TokenWarning:           {foreground: darkWarn, bold: true},
		TokenInfo:              {foreground: darkAccent},
		TokenChatUser:          {foreground: "#89dceb", bold: true},
		TokenChatAssistant:     {foreground: "#cdd6f4"},
		TokenChatTool:          {foreground: darkWarn},
		TokenChatSystem:        {foreground: darkMuted, faint: true},
		TokenChatCode:          {foreground: "#a6e3a1"},
		TokenChatLink:          {foreground: darkAccent, underline: true},
		TokenStatusBar:         {foreground: "#d4d4d8", background: darkPanel},
		TokenStatusBarActive:   {foreground: "#11111b", background: darkAccent, bold: true},
		TokenTopBar:            {foreground: "#e4e4e7", background: darkPanel, bold: true},
		TokenInputField:        {foreground: darkBase, borderForeground: darkMuted, border: borderRounded},
		TokenInputFieldFocused: {foreground: darkBase, borderForeground: darkAccent, border: borderRounded},
		TokenModal:             {foreground: darkBase, background: darkSurface, borderForeground: darkMuted, border: borderRounded},
		TokenModalTitle:        {foreground: "#11111b", background: darkAccent, bold: true},
		TokenPalette:           {foreground: darkBase, background: darkSurface},
		TokenPaletteHighlight:  {foreground: "#11111b", background: darkAccent, bold: true},
		TokenMentionList:       {foreground: darkBase, background: darkSurface},
		TokenMentionHighlight:  {foreground: "#11111b", background: "#89dceb", bold: true},
		TokenCostGood:          {foreground: "#a6e3a1", bold: true},
		TokenCostWarn:          {foreground: darkWarn, bold: true},
		TokenCostBad:           {foreground: darkError, bold: true},
		TokenToolPending:       {foreground: darkWarn},
		TokenToolSuccess:       {foreground: "#a6e3a1"},
		TokenToolError:         {foreground: darkError},
	}
}
