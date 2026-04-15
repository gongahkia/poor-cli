package markdown

import (
	"math/rand"
	"reflect"
	"strings"
	"testing"
	"testing/quick"
)

func TestBlockTokenizerScenarios(t *testing.T) {
	tests := []struct {
		name string
		in   string
		want []Event
	}{
		{
			name: "paragraph",
			in:   "hello *world*\n",
			want: []Event{
				BlockOpenEvent{Kind: BlockParagraph, Line: 1},
				RawLineEvent{Kind: BlockParagraph, Text: "hello *world*", Line: 1},
				BlockCloseEvent{Kind: BlockParagraph, Line: 1},
				CommitEvent{UpToLine: 1},
			},
		},
		{
			name: "code fence",
			in:   "```go\nfmt.Println()\n```\n",
			want: []Event{
				BlockOpenEvent{Kind: BlockCodeFence, Info: "go", Line: 1},
				RawLineEvent{Kind: BlockCodeFence, Text: "fmt.Println()", Line: 2},
				BlockCloseEvent{Kind: BlockCodeFence, Line: 3},
				CommitEvent{UpToLine: 3},
			},
		},
		{
			name: "heading variants",
			in:   "# One\n## Two\n### Three\n#### Four\n##### Five\n###### Six\n",
			want: []Event{
				BlockOpenEvent{Kind: BlockHeading1, Line: 1}, RawLineEvent{Kind: BlockHeading1, Text: "One", Line: 1}, BlockCloseEvent{Kind: BlockHeading1, Line: 1}, CommitEvent{UpToLine: 1},
				BlockOpenEvent{Kind: BlockHeading2, Line: 2}, RawLineEvent{Kind: BlockHeading2, Text: "Two", Line: 2}, BlockCloseEvent{Kind: BlockHeading2, Line: 2}, CommitEvent{UpToLine: 2},
				BlockOpenEvent{Kind: BlockHeading3, Line: 3}, RawLineEvent{Kind: BlockHeading3, Text: "Three", Line: 3}, BlockCloseEvent{Kind: BlockHeading3, Line: 3}, CommitEvent{UpToLine: 3},
				BlockOpenEvent{Kind: BlockHeading4, Line: 4}, RawLineEvent{Kind: BlockHeading4, Text: "Four", Line: 4}, BlockCloseEvent{Kind: BlockHeading4, Line: 4}, CommitEvent{UpToLine: 4},
				BlockOpenEvent{Kind: BlockHeading5, Line: 5}, RawLineEvent{Kind: BlockHeading5, Text: "Five", Line: 5}, BlockCloseEvent{Kind: BlockHeading5, Line: 5}, CommitEvent{UpToLine: 5},
				BlockOpenEvent{Kind: BlockHeading6, Line: 6}, RawLineEvent{Kind: BlockHeading6, Text: "Six", Line: 6}, BlockCloseEvent{Kind: BlockHeading6, Line: 6}, CommitEvent{UpToLine: 6},
			},
		},
		{
			name: "list item reflow",
			in:   "- a\n  wraps\n- b\n\n",
			want: []Event{
				BlockOpenEvent{Kind: BlockListUnordered, Line: 1},
				BlockOpenEvent{Kind: BlockListItem, Line: 1},
				RawLineEvent{Kind: BlockListItem, Text: "a", Line: 1},
				RawLineEvent{Kind: BlockListItem, Text: "wraps", Line: 2},
				BlockCloseEvent{Kind: BlockListItem, Line: 2},
				BlockOpenEvent{Kind: BlockListItem, Line: 3},
				RawLineEvent{Kind: BlockListItem, Text: "b", Line: 3},
				BlockCloseEvent{Kind: BlockListItem, Line: 4},
				BlockCloseEvent{Kind: BlockListUnordered, Line: 4},
				CommitEvent{UpToLine: 4},
			},
		},
		{
			name: "ordered list",
			in:   "3. a\n4. b\n\n",
			want: []Event{
				BlockOpenEvent{Kind: BlockListOrdered, Info: "3", Line: 1},
				BlockOpenEvent{Kind: BlockListItem, Line: 1},
				RawLineEvent{Kind: BlockListItem, Text: "a", Line: 1},
				BlockCloseEvent{Kind: BlockListItem, Line: 1},
				BlockOpenEvent{Kind: BlockListItem, Line: 2},
				RawLineEvent{Kind: BlockListItem, Text: "b", Line: 2},
				BlockCloseEvent{Kind: BlockListItem, Line: 3},
				BlockCloseEvent{Kind: BlockListOrdered, Line: 3},
				CommitEvent{UpToLine: 3},
			},
		},
		{
			name: "blockquote",
			in:   "> quoted\n> more\n\n",
			want: []Event{
				BlockOpenEvent{Kind: BlockBlockquote, Line: 1},
				RawLineEvent{Kind: BlockBlockquote, Text: "quoted", Line: 1},
				RawLineEvent{Kind: BlockBlockquote, Text: "more", Line: 2},
				BlockCloseEvent{Kind: BlockBlockquote, Line: 2},
				CommitEvent{UpToLine: 2},
			},
		},
		{
			name: "thematic break",
			in:   "---\n",
			want: []Event{
				BlockOpenEvent{Kind: BlockThematicBreak, Line: 1},
				RawLineEvent{Kind: BlockThematicBreak, Text: "---", Line: 1},
				BlockCloseEvent{Kind: BlockThematicBreak, Line: 1},
				CommitEvent{UpToLine: 1},
			},
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := tokenize(tt.in)
			if !reflect.DeepEqual(got, tt.want) {
				t.Fatalf("events mismatch\nwant: %#v\n got: %#v", tt.want, got)
			}
			assertSplitInvariant(t, tt.in)
		})
	}
}

func TestBlockTokenizerTwoKBSplitInvariant(t *testing.T) {
	doc := canonicalDoc(2048)
	want := tokenize(doc)
	one := tokenizeChunks(doc, singleByteChunks(len(doc)))
	if !reflect.DeepEqual(one, want) {
		t.Fatalf("single-byte split mismatch")
	}
	for i := 0; i <= len(doc); i++ {
		got := tokenizeChunks(doc, []int{i})
		if !reflect.DeepEqual(got, want) {
			t.Fatalf("split at %d mismatch", i)
		}
	}
}

func TestBlockTokenizerQuickSplitInvariant(t *testing.T) {
	cfg := &quick.Config{MaxCount: 10000}
	if err := quick.Check(func(d validDoc) bool {
		in := string(d)
		want := tokenize(in)
		r := rand.New(rand.NewSource(int64(len(in))*7919 + 17))
		var cuts []int
		for i := 1; i < len(in); i++ {
			if r.Intn(5) == 0 {
				cuts = append(cuts, i)
			}
		}
		got := tokenizeChunks(in, cuts)
		return reflect.DeepEqual(got, want)
	}, cfg); err != nil {
		t.Fatal(err)
	}
}

func TestBlockTokenizerCloseIdempotent(t *testing.T) {
	b := NewBlockTokenizer()
	b.Write([]byte("open paragraph"))
	if got := b.Close(); len(got) == 0 {
		t.Fatalf("first Close returned no events")
	}
	if got := b.Close(); got != nil {
		t.Fatalf("second Close = %#v, want nil", got)
	}
}

func tokenize(in string) []Event {
	return tokenizeChunks(in, nil)
}

func tokenizeChunks(in string, cuts []int) []Event {
	b := NewBlockTokenizer()
	var out []Event
	prev := 0
	for _, cut := range cuts {
		if cut < prev || cut > len(in) {
			continue
		}
		b.Write([]byte(in[prev:cut]))
		out = append(out, b.Drain()...)
		prev = cut
	}
	b.Write([]byte(in[prev:]))
	out = append(out, b.Drain()...)
	out = append(out, b.Close()...)
	return out
}

func singleByteChunks(n int) []int {
	cuts := make([]int, 0, n)
	for i := 1; i <= n; i++ {
		cuts = append(cuts, i)
	}
	return cuts
}

func assertSplitInvariant(t *testing.T, in string) {
	t.Helper()
	want := tokenize(in)
	for i := 0; i <= len(in); i++ {
		got := tokenizeChunks(in, []int{i})
		if !reflect.DeepEqual(got, want) {
			t.Fatalf("split at %d mismatch\nwant: %#v\n got: %#v", i, want, got)
		}
	}
}

func canonicalDoc(min int) string {
	base := strings.Join([]string{
		"# Heading",
		"",
		"paragraph with *inline* content",
		"still same paragraph",
		"",
		"```go",
		"fmt.Println(\"x\")",
		"```",
		"",
		"- one",
		"  wraps",
		"- two",
		"",
		"1. ordered",
		"2. list",
		"",
		"> quote",
		"> quote two",
		"",
		"---",
		"",
	}, "\n")
	var b strings.Builder
	for b.Len() < min {
		b.WriteString(base)
	}
	return b.String()
}

type validDoc string

func (validDoc) Generate(r *rand.Rand, size int) reflect.Value {
	blocks := []string{
		"plain text\n",
		"plain *text*\nmore text\n\n",
		"# h\n",
		"## h\n",
		"###### h\n",
		"---\n",
		"***\n",
		"___\n",
		"```go\nx := 1\n```\n",
		"~~~txt\nhello\n~~~\n",
		"- a\n  wrap\n- b\n\n",
		"+ a\n\n",
		"* a\n\n",
		"1. a\n2. b\n\n",
		"> q\n> r\n\n",
	}
	var b strings.Builder
	limit := r.Intn(1024)
	if limit < 1 {
		limit = 1
	}
	for b.Len() < limit {
		b.WriteString(blocks[r.Intn(len(blocks))])
	}
	return reflect.ValueOf(validDoc(b.String()[:minInt(b.Len(), 1024)]))
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}
