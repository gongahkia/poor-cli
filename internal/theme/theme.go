package theme

import (
	"fmt"
	"io"
	"reflect"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
)

type Token string

const (
	TokenBase              Token = "base"
	TokenMuted             Token = "muted"
	TokenBorder            Token = "border"
	TokenFocus             Token = "focus"
	TokenError             Token = "error"
	TokenSuccess           Token = "success"
	TokenWarning           Token = "warning"
	TokenInfo              Token = "info"
	TokenChatUser          Token = "chat_user"
	TokenChatAssistant     Token = "chat_assistant"
	TokenChatTool          Token = "chat_tool"
	TokenChatSystem        Token = "chat_system"
	TokenChatCode          Token = "chat_code"
	TokenChatLink          Token = "chat_link"
	TokenStatusBar         Token = "status_bar"
	TokenStatusBarActive   Token = "status_bar_active"
	TokenTopBar            Token = "top_bar"
	TokenInputField        Token = "input_field"
	TokenInputFieldFocused Token = "input_field_focused"
	TokenModal             Token = "modal"
	TokenModalTitle        Token = "modal_title"
	TokenPalette           Token = "palette"
	TokenPaletteHighlight  Token = "palette_highlight"
	TokenMentionList       Token = "mention_list"
	TokenMentionHighlight  Token = "mention_highlight"
	TokenCostGood          Token = "cost_good"
	TokenCostWarn          Token = "cost_warn"
	TokenCostBad           Token = "cost_bad"
	TokenToolPending       Token = "tool_pending"
	TokenToolSuccess       Token = "tool_success"
	TokenToolError         Token = "tool_error"
)

var AllTokens = []Token{
	TokenBase,
	TokenMuted,
	TokenBorder,
	TokenFocus,
	TokenError,
	TokenSuccess,
	TokenWarning,
	TokenInfo,
	TokenChatUser,
	TokenChatAssistant,
	TokenChatTool,
	TokenChatSystem,
	TokenChatCode,
	TokenChatLink,
	TokenStatusBar,
	TokenStatusBarActive,
	TokenTopBar,
	TokenInputField,
	TokenInputFieldFocused,
	TokenModal,
	TokenModalTitle,
	TokenPalette,
	TokenPaletteHighlight,
	TokenMentionList,
	TokenMentionHighlight,
	TokenCostGood,
	TokenCostWarn,
	TokenCostBad,
	TokenToolPending,
	TokenToolSuccess,
	TokenToolError,
}

type Theme struct {
	Name              string
	Capability        Capability
	Base              lipgloss.Style
	Muted             lipgloss.Style
	Border            lipgloss.Style
	Focus             lipgloss.Style
	Error             lipgloss.Style
	Success           lipgloss.Style
	Warning           lipgloss.Style
	Info              lipgloss.Style
	ChatUser          lipgloss.Style
	ChatAssistant     lipgloss.Style
	ChatTool          lipgloss.Style
	ChatSystem        lipgloss.Style
	ChatCode          lipgloss.Style
	ChatLink          lipgloss.Style
	StatusBar         lipgloss.Style
	StatusBarActive   lipgloss.Style
	TopBar            lipgloss.Style
	InputField        lipgloss.Style
	InputFieldFocused lipgloss.Style
	Modal             lipgloss.Style
	ModalTitle        lipgloss.Style
	Palette           lipgloss.Style
	PaletteHighlight  lipgloss.Style
	MentionList       lipgloss.Style
	MentionHighlight  lipgloss.Style
	CostGood          lipgloss.Style
	CostWarn          lipgloss.Style
	CostBad           lipgloss.Style
	ToolPending       lipgloss.Style
	ToolSuccess       lipgloss.Style
	ToolError         lipgloss.Style

	specs map[Token]styleSpec

	darkBackground bool
}

type styleSpec struct {
	foreground       string
	background       string
	borderForeground string
	bold             bool
	faint            bool
	italic           bool
	underline        bool
	reverse          bool
	border           borderKind
}

type borderKind string

const (
	borderNone    borderKind = ""
	borderNormal  borderKind = "normal"
	borderRounded borderKind = "rounded"
)

var tokenFields = map[Token]string{
	TokenBase:              "Base",
	TokenMuted:             "Muted",
	TokenBorder:            "Border",
	TokenFocus:             "Focus",
	TokenError:             "Error",
	TokenSuccess:           "Success",
	TokenWarning:           "Warning",
	TokenInfo:              "Info",
	TokenChatUser:          "ChatUser",
	TokenChatAssistant:     "ChatAssistant",
	TokenChatTool:          "ChatTool",
	TokenChatSystem:        "ChatSystem",
	TokenChatCode:          "ChatCode",
	TokenChatLink:          "ChatLink",
	TokenStatusBar:         "StatusBar",
	TokenStatusBarActive:   "StatusBarActive",
	TokenTopBar:            "TopBar",
	TokenInputField:        "InputField",
	TokenInputFieldFocused: "InputFieldFocused",
	TokenModal:             "Modal",
	TokenModalTitle:        "ModalTitle",
	TokenPalette:           "Palette",
	TokenPaletteHighlight:  "PaletteHighlight",
	TokenMentionList:       "MentionList",
	TokenMentionHighlight:  "MentionHighlight",
	TokenCostGood:          "CostGood",
	TokenCostWarn:          "CostWarn",
	TokenCostBad:           "CostBad",
	TokenToolPending:       "ToolPending",
	TokenToolSuccess:       "ToolSuccess",
	TokenToolError:         "ToolError",
}

func (t Theme) Style(token Token) lipgloss.Style {
	field, ok := tokenFields[token]
	if !ok {
		return lipgloss.NewStyle()
	}
	return reflect.ValueOf(t).FieldByName(field).Interface().(lipgloss.Style)
}

func Builtin(name string) (Theme, error) {
	return BuiltinWithCapability(name, DetectCapability())
}

func BuiltinWithCapability(name string, caps Capability) (Theme, error) {
	switch strings.ToLower(strings.TrimSpace(name)) {
	case "", "dark":
		return DarkWithCapability(caps), nil
	case "light":
		return LightWithCapability(caps), nil
	default:
		return Theme{}, fmt.Errorf("unknown builtin theme %q", name)
	}
}

func buildTheme(name string, caps Capability, darkBackground bool, specs map[Token]styleSpec) Theme {
	renderer := lipgloss.NewRenderer(io.Discard)
	renderer.SetColorProfile(profile(caps))
	renderer.SetHasDarkBackground(darkBackground)

	theme := Theme{
		Name:           name,
		Capability:     caps,
		specs:          cloneSpecs(specs),
		darkBackground: darkBackground,
	}
	value := reflect.ValueOf(&theme).Elem()
	for _, token := range AllTokens {
		field := value.FieldByName(tokenFields[token])
		field.Set(reflect.ValueOf(buildStyle(renderer, caps, specs[token])))
	}
	return theme
}

func buildStyle(renderer *lipgloss.Renderer, caps Capability, spec styleSpec) lipgloss.Style {
	style := renderer.NewStyle()
	if caps == CapabilityMonochrome {
		return style
	}
	if spec.foreground != "" {
		style = style.Foreground(lipgloss.Color(spec.foreground))
	}
	return style.
		Bold(spec.bold).
		Faint(spec.faint).
		Italic(spec.italic).
		Underline(spec.underline).
		Reverse(spec.reverse)
}

func profile(caps Capability) termenv.Profile {
	switch caps {
	case CapabilityTrueColor:
		return termenv.TrueColor
	case CapabilityANSI256:
		return termenv.ANSI256
	case CapabilityANSI16:
		return termenv.ANSI
	default:
		return termenv.Ascii
	}
}

func cloneSpecs(specs map[Token]styleSpec) map[Token]styleSpec {
	out := make(map[Token]styleSpec, len(specs))
	for token, spec := range specs {
		out[token] = spec
	}
	return out
}
