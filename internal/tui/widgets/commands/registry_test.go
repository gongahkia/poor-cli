package commands

import "testing"

func TestRegistryNormalizeCloneAndFilter(t *testing.T) {
	r := NewRegistry()
	r.Register(Command{ID: "review", Description: "Review"})
	r.SetCustoms([]Command{{ID: "deploy", Origin: "", RequiresArg: true}, {ID: ""}})
	all := r.All()
	if len(all) < 12 {
		t.Fatalf("all len=%d", len(all))
	}
	all[0].ID = "/mutated"
	if r.Builtins()[0].ID == "/mutated" {
		t.Fatal("registry returned mutable slice")
	}
	if got := r.Filter("dep"); len(got) == 0 || got[0].ID != "/deploy" || got[0].Origin != OriginCustom {
		t.Fatalf("deploy filter=%#v", got)
	}
	if got := r.Filter("/pro"); len(got) == 0 || got[0].ID != "/provider" {
		t.Fatalf("provider filter=%#v", got)
	}
	if got := r.Filter(""); len(got) != len(r.All()) {
		t.Fatalf("empty filter len=%d", len(got))
	}
}
