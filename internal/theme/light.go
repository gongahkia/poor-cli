package theme

const (
	lightBase    = "#1f2937"
	lightSurface = "#ffffff"
	lightPanel   = "#e5e7eb"
	lightMuted   = "#6b7280"
	lightAccent  = "#2563eb"
	lightWarn    = "#92400e"
	lightError   = "#b91c1c"
)

func Light() Theme {
	return LightWithCapability(DetectCapability())
}

func LightWithCapability(caps Capability) Theme {
	return buildTheme("light", caps, false, lightSpecs())
}

func lightSpecs() map[Token]styleSpec {
	return map[Token]styleSpec{
		TokenBase:              {foreground: lightBase},
		TokenMuted:             {foreground: lightMuted, faint: true},
		TokenBorder:            {foreground: "#9ca3af"},
		TokenFocus:             {foreground: lightAccent, bold: true},
		TokenError:             {foreground: lightError, bold: true},
		TokenSuccess:           {foreground: "#047857", bold: true},
		TokenWarning:           {foreground: lightWarn, bold: true},
		TokenInfo:              {foreground: lightAccent},
		TokenChatUser:          {foreground: "#007c89", bold: true},
		TokenChatAssistant:     {foreground: "#4b5563"},
		TokenChatTool:          {foreground: "#9a6700"},
		TokenChatSystem:        {foreground: lightMuted, faint: true},
		TokenChatCode:          {foreground: "#047857"},
		TokenChatLink:          {foreground: lightAccent, underline: true},
		TokenStatusBar:         {foreground: lightBase, background: lightPanel},
		TokenStatusBarActive:   {foreground: lightSurface, background: lightAccent, bold: true},
		TokenTopBar:            {foreground: lightBase, background: lightPanel, bold: true},
		TokenInputField:        {foreground: lightBase, borderForeground: "#9ca3af", border: borderRounded},
		TokenInputFieldFocused: {foreground: lightBase, borderForeground: lightAccent, border: borderRounded},
		TokenModal:             {foreground: lightBase, background: lightSurface, borderForeground: "#9ca3af", border: borderRounded},
		TokenModalTitle:        {foreground: lightSurface, background: lightAccent, bold: true},
		TokenPalette:           {foreground: lightBase, background: lightSurface},
		TokenPaletteHighlight:  {foreground: lightSurface, background: lightAccent, bold: true},
		TokenMentionList:       {foreground: lightBase, background: lightSurface},
		TokenMentionHighlight:  {foreground: lightSurface, background: "#007c89", bold: true},
		TokenCostGood:          {foreground: "#047857", bold: true},
		TokenCostWarn:          {foreground: lightWarn, bold: true},
		TokenCostBad:           {foreground: lightError, bold: true},
		TokenToolPending:       {foreground: lightWarn},
		TokenToolSuccess:       {foreground: "#047857"},
		TokenToolError:         {foreground: lightError},
	}
}
