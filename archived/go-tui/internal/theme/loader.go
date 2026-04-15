package theme

import (
	"bytes"
	"fmt"
	"os"
	"strconv"
	"strings"

	"gopkg.in/yaml.v3"
)

type themeYAML struct {
	Name     string               `yaml:"name"`
	Inherits string               `yaml:"inherits"`
	Styles   map[string]styleYAML `yaml:"styles"`
}

type styleYAML struct {
	Foreground       *string `yaml:"foreground"`
	Background       *string `yaml:"background"`
	BorderForeground *string `yaml:"border_foreground"`
	Bold             *bool   `yaml:"bold"`
	Faint            *bool   `yaml:"faint"`
	Italic           *bool   `yaml:"italic"`
	Underline        *bool   `yaml:"underline"`
	Reverse          *bool   `yaml:"reverse"`
}

var ansiNames = map[string]string{
	"black":          "0",
	"red":            "1",
	"green":          "2",
	"yellow":         "3",
	"blue":           "4",
	"magenta":        "5",
	"cyan":           "6",
	"white":          "7",
	"gray":           "8",
	"grey":           "8",
	"bright_black":   "8",
	"bright_red":     "9",
	"bright_green":   "10",
	"bright_yellow":  "11",
	"bright_blue":    "12",
	"bright_magenta": "13",
	"bright_cyan":    "14",
	"bright_white":   "15",
}

func LoadFromYAML(data []byte) (Theme, error) {
	return LoadFromYAMLWithCapability(data, DetectCapability())
}

func LoadFromYAMLWithCapability(data []byte, caps Capability) (Theme, error) {
	return loadFromYAML(data, caps, 0)
}

func loadFromYAML(data []byte, caps Capability, depth int) (Theme, error) {
	if depth > 8 {
		return Theme{}, fmt.Errorf("theme inheritance too deep")
	}
	var cfg themeYAML
	decoder := yaml.NewDecoder(bytes.NewReader(data))
	decoder.KnownFields(true)
	if err := decoder.Decode(&cfg); err != nil {
		return Theme{}, err
	}

	base, err := inheritedTheme(cfg.Inherits, caps, depth)
	if err != nil {
		return Theme{}, err
	}
	specs := cloneSpecs(base.specs)
	for name, style := range cfg.Styles {
		token := Token(strings.ToLower(strings.TrimSpace(name)))
		if _, ok := tokenFields[token]; !ok {
			return Theme{}, fmt.Errorf("unknown theme token %q", name)
		}
		next, err := applyOverlay(specs[token], style)
		if err != nil {
			return Theme{}, fmt.Errorf("%s: %w", name, err)
		}
		specs[token] = next
	}
	name := cfg.Name
	if strings.TrimSpace(name) == "" {
		name = "custom"
	}
	return buildTheme(name, caps, base.darkBackground, specs), nil
}

func inheritedTheme(inherits string, caps Capability, depth int) (Theme, error) {
	switch strings.ToLower(strings.TrimSpace(inherits)) {
	case "", "dark":
		return DarkWithCapability(caps), nil
	case "light":
		return LightWithCapability(caps), nil
	default:
		data, err := os.ReadFile(inherits)
		if err != nil {
			return Theme{}, err
		}
		return loadFromYAML(data, caps, depth+1)
	}
}

func applyOverlay(spec styleSpec, overlay styleYAML) (styleSpec, error) {
	if overlay.Foreground != nil {
		color, err := normalizeColor(*overlay.Foreground)
		if err != nil {
			return styleSpec{}, fmt.Errorf("foreground: %w", err)
		}
		spec.foreground = color
	}
	if overlay.Background != nil {
		color, err := normalizeColor(*overlay.Background)
		if err != nil {
			return styleSpec{}, fmt.Errorf("background: %w", err)
		}
		spec.background = color
	}
	if overlay.BorderForeground != nil {
		color, err := normalizeColor(*overlay.BorderForeground)
		if err != nil {
			return styleSpec{}, fmt.Errorf("border_foreground: %w", err)
		}
		spec.borderForeground = color
	}
	if overlay.Bold != nil {
		spec.bold = *overlay.Bold
	}
	if overlay.Faint != nil {
		spec.faint = *overlay.Faint
	}
	if overlay.Italic != nil {
		spec.italic = *overlay.Italic
	}
	if overlay.Underline != nil {
		spec.underline = *overlay.Underline
	}
	if overlay.Reverse != nil {
		spec.reverse = *overlay.Reverse
	}
	return spec, nil
}

func normalizeColor(raw string) (string, error) {
	value := strings.ToLower(strings.TrimSpace(raw))
	if value == "" {
		return "", fmt.Errorf("empty color")
	}
	if mapped, ok := ansiNames[value]; ok {
		return mapped, nil
	}
	if strings.HasPrefix(value, "#") {
		if len(value) != 7 {
			return "", fmt.Errorf("hex color must be #RRGGBB")
		}
		if _, err := strconv.ParseUint(value[1:], 16, 32); err != nil {
			return "", fmt.Errorf("invalid hex color")
		}
		return value, nil
	}
	number, err := strconv.Atoi(value)
	if err != nil || number < 0 || number > 255 {
		return "", fmt.Errorf("must be hex, ANSI name, or 0-255 palette number")
	}
	return strconv.Itoa(number), nil
}
