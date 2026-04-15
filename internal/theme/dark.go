package theme

const (
	darkBase    = "#f4f4f5"
	darkMuted   = "#585858"
	darkAccent  = "#89b4fa"
	darkSuccess = "#a6e3a1"
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
		TokenSuccess:           {foreground: darkSuccess, bold: true},
		TokenWarning:           {foreground: darkWarn, bold: true},
		TokenInfo:              {foreground: darkAccent},
		TokenChatUser:          {foreground: darkBase, bold: true},
		TokenChatAssistant:     {foreground: darkBase},
		TokenChatTool:          {foreground: darkWarn},
		TokenChatSystem:        {foreground: darkMuted, faint: true},
		TokenChatCode:          {foreground: darkSuccess},
		TokenChatLink:          {foreground: darkAccent, underline: true},
		TokenStatusBar:         {foreground: darkBase},
		TokenStatusBarActive:   {foreground: darkAccent, bold: true},
		TokenTopBar:            {foreground: darkBase, bold: true},
		TokenInputField:        {foreground: darkBase},
		TokenInputFieldFocused: {foreground: darkBase},
		TokenModal:             {foreground: darkBase},
		TokenModalTitle:        {foreground: darkAccent, bold: true},
		TokenPalette:           {foreground: darkBase},
		TokenPaletteHighlight:  {foreground: darkAccent, bold: true},
		TokenMentionList:       {foreground: darkBase},
		TokenMentionHighlight:  {foreground: darkAccent, bold: true},
		TokenCostGood:          {foreground: darkSuccess, bold: true},
		TokenCostWarn:          {foreground: darkWarn, bold: true},
		TokenCostBad:           {foreground: darkError, bold: true},
		TokenToolPending:       {foreground: darkWarn},
		TokenToolSuccess:       {foreground: darkSuccess},
		TokenToolError:         {foreground: darkError},
	}
}
