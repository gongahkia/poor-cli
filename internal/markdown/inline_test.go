package markdown

import (
	"reflect"
	"strings"
	"testing"
)

func TestInlineTokenizerRequiredCases(t *testing.T) {
	tests := []struct {
		name string
		in   string
		want []Event
	}{
		{
			name: "emphasis pair",
			in:   "*foo* *bar*",
			want: []Event{
				InlineOpenEvent{Kind: InlineEmphasis}, TextEvent{Value: "foo"}, InlineCloseEvent{Kind: InlineEmphasis},
				TextEvent{Value: " "},
				InlineOpenEvent{Kind: InlineEmphasis}, TextEvent{Value: "bar"}, InlineCloseEvent{Kind: InlineEmphasis},
			},
		},
		{
			name: "strong emphasis ambiguity",
			in:   "**foo** vs *foo* vs ***foo***",
			want: []Event{
				InlineOpenEvent{Kind: InlineStrong}, TextEvent{Value: "foo"}, InlineCloseEvent{Kind: InlineStrong},
				TextEvent{Value: " vs "},
				InlineOpenEvent{Kind: InlineEmphasis}, TextEvent{Value: "foo"}, InlineCloseEvent{Kind: InlineEmphasis},
				TextEvent{Value: " vs "},
				InlineOpenEvent{Kind: InlineStrong}, InlineOpenEvent{Kind: InlineEmphasis}, TextEvent{Value: "foo"}, InlineCloseEvent{Kind: InlineEmphasis}, InlineCloseEvent{Kind: InlineStrong},
			},
		},
		{
			name: "code span",
			in:   "`code` backtick",
			want: []Event{InlineOpenEvent{Kind: InlineCode}, TextEvent{Value: "code"}, InlineCloseEvent{Kind: InlineCode}, TextEvent{Value: " backtick"}},
		},
		{
			name: "link",
			in:   "[text](url)",
			want: []Event{LinkEvent{Text: "text", URL: "url"}},
		},
		{
			name: "unclosed flushes literal",
			in:   "*foo bar",
			want: []Event{TextEvent{Value: "*foo bar"}},
		},
		{
			name: "autolink",
			in:   "<https://example.com>",
			want: []Event{LinkEvent{Text: "https://example.com", URL: "https://example.com"}},
		},
		{
			name: "line independence",
			in:   "*close*",
			want: []Event{InlineOpenEvent{Kind: InlineEmphasis}, TextEvent{Value: "close"}, InlineCloseEvent{Kind: InlineEmphasis}},
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := NewInlineTokenizer().FeedLine(RawLineEvent{Block: BlockParagraph, Text: tt.in})
			assertEvents(t, got, tt.want)
		})
	}
}

func TestInlineTokenizerLineIndependence(t *testing.T) {
	tok := NewInlineTokenizer()
	assertEvents(t, tok.FeedLine(RawLineEvent{Text: "*em"}), []Event{TextEvent{Value: "*em"}})
	assertEvents(t, tok.FeedLine(RawLineEvent{Text: "*more"}), []Event{TextEvent{Value: "*more"}})
	assertEvents(t, tok.FeedLine(RawLineEvent{Text: "*close*"}), []Event{InlineOpenEvent{Kind: InlineEmphasis}, TextEvent{Value: "close"}, InlineCloseEvent{Kind: InlineEmphasis}})
	assertEvents(t, tok.Close(), nil)
}

func TestInlineTokenizerHoldbackLimit(t *testing.T) {
	in := "*" + strings.Repeat("a", 129) + "*"
	got := NewInlineTokenizer().FeedLine(RawLineEvent{Text: in})
	assertEvents(t, got, []Event{TextEvent{Value: in}})
}

func TestInlineTokenizerCommonMarkFlankingSubset(t *testing.T) {
	tests := []struct {
		name string
		in   string
		want []Event
	}{
		{"cm left basic star", "*foo bar*", []Event{InlineOpenEvent{Kind: InlineEmphasis}, TextEvent{Value: "foo bar"}, InlineCloseEvent{Kind: InlineEmphasis}}},
		{"cm no left after space star", "a * foo bar*", []Event{TextEvent{Value: "a * foo bar*"}}},
		{"cm right before space star", "a* foo bar*", []Event{TextEvent{Value: "a* foo bar*"}}},
		{"cm punctuation opens star", "foo*bar*", []Event{TextEvent{Value: "foo"}, InlineOpenEvent{Kind: InlineEmphasis}, TextEvent{Value: "bar"}, InlineCloseEvent{Kind: InlineEmphasis}}},
		{"cm intraword star", "a*b*c", []Event{TextEvent{Value: "a"}, InlineOpenEvent{Kind: InlineEmphasis}, TextEvent{Value: "b"}, InlineCloseEvent{Kind: InlineEmphasis}, TextEvent{Value: "c"}}},
		{"cm punctuation flanking star", "foo-*(bar)*", []Event{TextEvent{Value: "foo-"}, InlineOpenEvent{Kind: InlineEmphasis}, TextEvent{Value: "(bar)"}, InlineCloseEvent{Kind: InlineEmphasis}}},
		{"cm punctuation close star", "*foo bar*.", []Event{InlineOpenEvent{Kind: InlineEmphasis}, TextEvent{Value: "foo bar"}, InlineCloseEvent{Kind: InlineEmphasis}, TextEvent{Value: "."}}},
		{"cm strong star", "**foo bar**", []Event{InlineOpenEvent{Kind: InlineStrong}, TextEvent{Value: "foo bar"}, InlineCloseEvent{Kind: InlineStrong}}},
		{"cm nested star", "*foo **bar** baz*", []Event{InlineOpenEvent{Kind: InlineEmphasis}, TextEvent{Value: "foo "}, InlineOpenEvent{Kind: InlineStrong}, TextEvent{Value: "bar"}, InlineCloseEvent{Kind: InlineStrong}, TextEvent{Value: " baz"}, InlineCloseEvent{Kind: InlineEmphasis}}},
		{"cm nested reverse star", "**foo *bar* baz**", []Event{InlineOpenEvent{Kind: InlineStrong}, TextEvent{Value: "foo "}, InlineOpenEvent{Kind: InlineEmphasis}, TextEvent{Value: "bar"}, InlineCloseEvent{Kind: InlineEmphasis}, TextEvent{Value: " baz"}, InlineCloseEvent{Kind: InlineStrong}}},
		{"cm triple star", "***foo bar***", []Event{InlineOpenEvent{Kind: InlineStrong}, InlineOpenEvent{Kind: InlineEmphasis}, TextEvent{Value: "foo bar"}, InlineCloseEvent{Kind: InlineEmphasis}, InlineCloseEvent{Kind: InlineStrong}}},
		{"cm left basic underscore", "_foo bar_", []Event{InlineOpenEvent{Kind: InlineEmphasis}, TextEvent{Value: "foo bar"}, InlineCloseEvent{Kind: InlineEmphasis}}},
		{"cm no left after space underscore", "a _ foo bar_", []Event{TextEvent{Value: "a _ foo bar_"}}},
		{"cm intraword underscore literal", "foo_bar_baz", []Event{TextEvent{Value: "foo_bar_baz"}}},
		{"cm underscore can open after punct", "foo-_bar_", []Event{TextEvent{Value: "foo-"}, InlineOpenEvent{Kind: InlineEmphasis}, TextEvent{Value: "bar"}, InlineCloseEvent{Kind: InlineEmphasis}}},
		{"cm underscore cannot open intraword", "foo_bar_", []Event{TextEvent{Value: "foo_bar_"}}},
		{"cm underscore can close before punct", "_foo_bar.", []Event{TextEvent{Value: "_foo_bar."}}},
		{"cm strong underscore", "__foo bar__", []Event{InlineOpenEvent{Kind: InlineStrong}, TextEvent{Value: "foo bar"}, InlineCloseEvent{Kind: InlineStrong}}},
		{"cm nested underscore", "_foo __bar__ baz_", []Event{InlineOpenEvent{Kind: InlineEmphasis}, TextEvent{Value: "foo "}, InlineOpenEvent{Kind: InlineStrong}, TextEvent{Value: "bar"}, InlineCloseEvent{Kind: InlineStrong}, TextEvent{Value: " baz"}, InlineCloseEvent{Kind: InlineEmphasis}}},
		{"cm delimiter across punctuation", "(_foo_)", []Event{TextEvent{Value: "("}, InlineOpenEvent{Kind: InlineEmphasis}, TextEvent{Value: "foo"}, InlineCloseEvent{Kind: InlineEmphasis}, TextEvent{Value: ")"}}},
		{"cm code suppresses emphasis", "`*foo*`", []Event{InlineOpenEvent{Kind: InlineCode}, TextEvent{Value: "*foo*"}, InlineCloseEvent{Kind: InlineCode}}},
		{"cm link suppresses emphasis", "[*foo*](url)", []Event{LinkEvent{Text: "*foo*", URL: "url"}}},
	}
	if len(tests) < 20 {
		t.Fatalf("need at least 20 flanking cases, have %d", len(tests))
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := NewInlineTokenizer().FeedLine(RawLineEvent{Block: BlockParagraph, Text: tt.in})
			assertEvents(t, got, tt.want)
		})
	}
}

func assertEvents(t *testing.T, got, want []Event) {
	t.Helper()
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("events mismatch\ngot:  %#v\nwant: %#v", got, want)
	}
}
