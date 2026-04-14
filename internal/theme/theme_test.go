package theme

import (
	"flag"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
)

var update = flag.Bool("update", false, "update golden files")

func TestTokenSnapshots(t *testing.T) {
	tests := []struct {
		name  string
		theme Theme
		file  string
	}{
		{"dark", DarkWithCapability(CapabilityTrueColor), "dark.golden"},
		{"light", LightWithCapability(CapabilityTrueColor), "light.golden"},
		{"mono", DarkWithCapability(CapabilityMonochrome), "mono.golden"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := snapshotTheme(tt.theme)
			path := filepath.Join("testdata", tt.file)
			if *update {
				if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
					t.Fatal(err)
				}
				if err := os.WriteFile(path, []byte(got), 0644); err != nil {
					t.Fatal(err)
				}
			}
			want, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			if got != string(want) {
				t.Fatalf("snapshot mismatch\n%s", diffLines(string(want), got))
			}
		})
	}
}

func TestLoadFromYAMLPartialMerge(t *testing.T) {
	got, err := LoadFromYAMLWithCapability([]byte(`
name: custom
styles:
  chat_user:
    foreground: "#00ffff"
    bold: true
  border:
    foreground: "240"
`), CapabilityTrueColor)
	if err != nil {
		t.Fatal(err)
	}
	dark := DarkWithCapability(CapabilityTrueColor)
	if got.ChatAssistant.Render("assistant") != dark.ChatAssistant.Render("assistant") {
		t.Fatal("partial theme lost inherited chat_assistant token")
	}
	if got.ChatUser.Render("user") == dark.ChatUser.Render("user") {
		t.Fatal("chat_user override did not apply")
	}
	if got.Border.Render("border") == dark.Border.Render("border") {
		t.Fatal("border override did not apply")
	}
}

func TestLoadFromYAMLInheritsLight(t *testing.T) {
	got, err := LoadFromYAMLWithCapability([]byte(`
name: custom-light
inherits: light
styles:
  chat_link:
    underline: false
`), CapabilityTrueColor)
	if err != nil {
		t.Fatal(err)
	}
	light := LightWithCapability(CapabilityTrueColor)
	if got.Base.Render("base") != light.Base.Render("base") {
		t.Fatal("light inheritance did not preserve base")
	}
	if got.ChatLink.Render("link") == light.ChatLink.Render("link") {
		t.Fatal("chat_link override did not apply")
	}
}

func TestLoadFromYAMLRejectsUnknownToken(t *testing.T) {
	_, err := LoadFromYAMLWithCapability([]byte(`
styles:
  unknown:
    foreground: cyan
`), CapabilityTrueColor)
	if err == nil {
		t.Fatal("expected unknown token error")
	}
}

func TestDetectCapability(t *testing.T) {
	tests := []struct {
		name string
		env  map[string]string
		want Capability
	}{
		{"no color", map[string]string{"NO_COLOR": ""}, CapabilityMonochrome},
		{"truecolor", map[string]string{"COLORTERM": "truecolor"}, CapabilityTrueColor},
		{"24bit", map[string]string{"COLORTERM": "24bit"}, CapabilityTrueColor},
		{"256", map[string]string{"TERM": "xterm-256color"}, CapabilityANSI256},
		{"fallback", map[string]string{"TERM": "xterm"}, CapabilityANSI16},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := DetectCapabilityFromLookup(func(key string) (string, bool) {
				value, ok := tt.env[key]
				return value, ok
			})
			if got != tt.want {
				t.Fatalf("got %s want %s", got, tt.want)
			}
		})
	}
}

func TestNOColorProducesZeroANSIEscapes(t *testing.T) {
	t.Setenv("NO_COLOR", "")
	got := Dark()
	if got.Capability != CapabilityMonochrome {
		t.Fatalf("got %s want monochrome", got.Capability)
	}
	for _, token := range AllTokens {
		rendered := got.Style(token).Render(string(token))
		if strings.Contains(rendered, "\x1b[") {
			t.Fatalf("%s rendered ANSI escapes: %q", token, rendered)
		}
	}
}

func snapshotTheme(theme Theme) string {
	var b strings.Builder
	for _, token := range AllTokens {
		rendered := theme.Style(token).Copy().Width(20).Render(string(token))
		b.WriteString(string(token))
		b.WriteByte('=')
		b.WriteString(strconv.Quote(rendered))
		b.WriteByte('\n')
	}
	return b.String()
}

func diffLines(want, got string) string {
	wantLines := strings.Split(want, "\n")
	gotLines := strings.Split(got, "\n")
	max := len(wantLines)
	if len(gotLines) > max {
		max = len(gotLines)
	}
	var b strings.Builder
	for i := 0; i < max; i++ {
		var w, g string
		if i < len(wantLines) {
			w = wantLines[i]
		}
		if i < len(gotLines) {
			g = gotLines[i]
		}
		if w != g {
			b.WriteString("line ")
			b.WriteString(strconv.Itoa(i + 1))
			b.WriteString("\nwant: ")
			b.WriteString(w)
			b.WriteString("\n got: ")
			b.WriteString(g)
			b.WriteByte('\n')
		}
	}
	return b.String()
}
