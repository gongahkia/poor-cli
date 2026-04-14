package theme

import (
	"os"
	"strings"
)

type Capability int

const (
	CapabilityMonochrome Capability = iota
	CapabilityANSI16
	CapabilityANSI256
	CapabilityTrueColor
)

func DetectCapability() Capability {
	return DetectCapabilityFromLookup(os.LookupEnv)
}

func DetectCapabilityFromLookup(lookup func(string) (string, bool)) Capability {
	if _, ok := lookup("NO_COLOR"); ok {
		return CapabilityMonochrome
	}
	colorterm, _ := lookup("COLORTERM")
	switch strings.ToLower(colorterm) {
	case "truecolor", "24bit":
		return CapabilityTrueColor
	}
	term, _ := lookup("TERM")
	if strings.Contains(strings.ToLower(term), "256color") {
		return CapabilityANSI256
	}
	return CapabilityANSI16
}

func (c Capability) String() string {
	switch c {
	case CapabilityMonochrome:
		return "monochrome"
	case CapabilityANSI16:
		return "ansi16"
	case CapabilityANSI256:
		return "ansi256"
	case CapabilityTrueColor:
		return "truecolor"
	default:
		return "unknown"
	}
}
