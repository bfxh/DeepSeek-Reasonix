package netaccel

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"
)

type call struct {
	Dir  string
	Args []string
}

// fakeGit records calls and returns canned values for `--get` queries.
func fakeGit(calls *[]call, values map[string]string, failOn map[string]bool) GitRunner {
	return func(ctx context.Context, dir string, args ...string) (string, error) {
		*calls = append(*calls, call{Dir: dir, Args: args})
		joined := strings.Join(args, " ")
		if failOn[joined] {
			return "", errors.New("git failed: " + joined)
		}
		for _, a := range args {
			if v, ok := values[a]; ok {
				return v, nil
			}
		}
		return "", nil
	}
}

func TestApplyGitReadonlyRecordsReceiptAndCleansPushURL(t *testing.T) {
	dir := t.TempDir()
	store := ReceiptStore{Dir: dir}
	var calls []call
	git := fakeGit(&calls, map[string]string{
		"remote.origin.pushurl": "https://mirror.example/https://github.com/",
	}, nil)

	r, err := ApplyGitReadonly(context.Background(), store, dir, "https://mirror.example/", git)
	if err != nil {
		t.Fatalf("apply: %v", err)
	}
	if r == nil {
		t.Fatal("expected a receipt")
	}
	wantKey := "url.https://mirror.example/.insteadOf"
	if len(r.UndoArgs) != 4 || r.UndoArgs[3] != wantKey {
		t.Fatalf("undo args = %v, want unset %s", r.UndoArgs, wantKey)
	}

	sawInsteadOf := false
	sawPushUnset := false
	for _, c := range calls {
		joined := strings.Join(c.Args, " ")
		if strings.Contains(joined, "insteadOf") && c.Args[0] == "config" {
			sawInsteadOf = true
		}
		if strings.Contains(joined, "unset remote.origin.pushurl") {
			sawPushUnset = true
		}
	}
	if !sawInsteadOf {
		t.Fatal("insteadOf was never written")
	}
	if !sawPushUnset {
		t.Fatal("mirror-tainted pushurl was never removed")
	}
	if strings.Contains(strings.Join(r.UndoArgs, " "), "pushInsteadOf") {
		t.Fatal("pushInsteadOf must never appear")
	}

	loaded, err := store.Load()
	if err != nil {
		t.Fatal(err)
	}
	if len(loaded) != 1 {
		t.Fatalf("receipts = %d, want 1", len(loaded))
	}
}

func TestApplyGitReadonlyNoMirrorIsNoop(t *testing.T) {
	store := ReceiptStore{Dir: t.TempDir()}
	var calls []call
	git := fakeGit(&calls, nil, nil)
	r, err := ApplyGitReadonly(context.Background(), store, "/repo", "", git)
	if err != nil || r != nil {
		t.Fatalf("expected no-op, got %v / %v", r, err)
	}
	if len(calls) != 0 {
		t.Fatalf("git must not be invoked: %v", calls)
	}
}

func TestUndoAllReplaysInReverseOrder(t *testing.T) {
	dir := t.TempDir()
	store := ReceiptStore{Dir: dir}
	first := Receipt{TS: time.Now(), Action: "git.insteadOf", CWD: dir, UndoArgs: []string{"config", "--unset", "first"}}
	second := Receipt{TS: time.Now(), Action: "git.insteadOf", CWD: dir, UndoArgs: []string{"config", "--unset", "second"}}
	if err := store.Append(first); err != nil {
		t.Fatal(err)
	}
	if err := store.Append(second); err != nil {
		t.Fatal(err)
	}

	var calls []call
	git := fakeGit(&calls, nil, nil)
	n, err := store.UndoAll(context.Background(), git)
	if err != nil {
		t.Fatalf("undo: %v", err)
	}
	if n != 2 {
		t.Fatalf("undone = %d, want 2", n)
	}
	if len(calls) != 2 || !strings.Contains(strings.Join(calls[0].Args, " "), "second") {
		t.Fatalf("undo must run in reverse order, got %v", calls)
	}
}

func TestUndoAllReportsPartialFailure(t *testing.T) {
	dir := t.TempDir()
	store := ReceiptStore{Dir: dir}
	_ = store.Append(Receipt{Action: "a", CWD: dir, UndoArgs: []string{"config", "--unset", "broken"}})
	_ = store.Append(Receipt{Action: "b", CWD: dir, UndoArgs: []string{"config", "--unset", "fine"}})

	var calls []call
	git := fakeGit(&calls, nil, map[string]bool{"config --unset broken": true})
	n, err := store.UndoAll(context.Background(), git)
	if err == nil {
		t.Fatal("expected an error for the failed undo")
	}
	var ue *UndoError
	if !errors.As(err, &ue) {
		t.Fatalf("error type = %T, want *UndoError", err)
	}
	if n != 1 {
		t.Fatalf("undone = %d, want 1 (the successful one still counted)", n)
	}
}
