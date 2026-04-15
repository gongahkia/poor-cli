package theme

const (
	lightBase    = "#1f2937"
	lightMuted   = "#6b7280"
	lightAccent  = "#2563eb"
	lightSuccess = "#047857"
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
		TokenBorder:            {foreground: lightMuted},
		TokenFocus:             {foreground: lightAccent, bold: true},
		TokenError:             {foreground: lightError, bold: true},
		TokenSuccess:           {foreground: lightSuccess, bold: true},
		TokenWarning:           {foreground: lightWarn, bold: true},
		TokenInfo:              {foreground: lightAccent},
		TokenChatUser:          {foreground: lightBase, bold: true},
		TokenChatAssistant:     {foreground: lightBase},
		TokenChatTool:          {foreground: lightWarn},
		TokenChatSystem:        {foreground: lightMuted, faint: true},
		TokenChatCode:          {foreground: lightSuccess},
		TokenChatLink:          {foreground: lightAccent, underline: true},
		TokenStatusBar:         {foreground: lightBase},
		TokenStatusBarActive:   {foreground: lightAccent, bold: true},
		TokenTopBar:            {foreground: lightBase, bold: true},
		TokenInputField:        {foreground: lightBase},
		TokenInputFieldFocused: {foreground: lightBase},
		TokenModal:             {foreground: lightBase},
		TokenModalTitle:        {foreground: lightAccent, bold: true},
		TokenPalette:           {foreground: lightBase},
		TokenPaletteHighlight:  {foreground: lightAccent, bold: true},
		TokenMentionList:       {foreground: lightBase},
		TokenMentionHighlight:  {foreground: lightAccent, bold: true},
		TokenCostGood:          {foreground: lightSuccess, bold: true},
		TokenCostWarn:          {foreground: lightWarn, bold: true},
		TokenCostBad:           {foreground: lightError, bold: true},
		TokenToolPending:       {foreground: lightWarn},
		TokenToolSuccess:       {foreground: lightSuccess},
		TokenToolError:         {foreground: lightError},
	}
}
