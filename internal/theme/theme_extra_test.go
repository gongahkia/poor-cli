package theme

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestCapabilityStringAndBuiltins(t *testing.T) {
	tests := map[Capability]string{
		CapabilityMonochrome: "monochrome",
		CapabilityANSI16:     "ansi16",
		CapabilityANSI256:    "ansi256",
		CapabilityTrueColor:  "truecolor",
		Capability(99):       "unknown",
	}
	for cap, want := range tests {
		if got := cap.String(); got != want {
			t.Fatalf("%v string=%q want %q", int(cap), got, want)
		}
	}
	if _, err := BuiltinWithCapability("light", CapabilityMonochrome); err != nil {
		t.Fatal(err)
	}
	if _, err := Builtin("missing"); err == nil {
		t.Fatal("expected unknown builtin error")
	}
}

func TestLoadFromYAMLInheritsFileAndRejectsBadColor(t *testing.T) {
	dir := t.TempDir()
	base := filepath.Join(dir, "base.yaml")
	if err := os.WriteFile(base, []byte("name: base\ninherits: light\nstyles:\n  focus:\n    foreground: '#00ff00'\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	tm, err := LoadFromYAMLWithCapability([]byte("name: child\ninherits: "+base+"\nstyles:\n  error:\n    foreground: bright_red\n"), CapabilityANSI256)
	if err != nil {
		t.Fatal(err)
	}
	if tm.Name != "child" || tm.Capability != CapabilityANSI256 {
		t.Fatalf("theme=%#v", tm)
	}
	_, err = LoadFromYAML([]byte("styles:\n  error:\n    foreground: '#bad'\n"))
	if err == nil || !strings.Contains(err.Error(), "hex color") {
		t.Fatalf("bad color err=%v", err)
	}
}
