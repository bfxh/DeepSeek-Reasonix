package netaccel

import (
	"bufio"
	"context"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

// OfficialPrefix is the URL that read-only acceleration rewrites. push is never
// rewritten: pushInsteadOf is never written, so pushes always reach the origin.
const OfficialPrefix = "https://github.com/"

// GitRunner executes a git command in a directory. It is an indirection so
// tests never need a real git binary.
type GitRunner func(ctx context.Context, dir string, args ...string) (string, error)

// ExecGit is the production GitRunner.
func ExecGit(ctx context.Context, dir string, args ...string) (string, error) {
	cmd := exec.CommandContext(ctx, "git", args...)
	cmd.Dir = dir
	out, err := cmd.Output()
	return strings.TrimSpace(string(out)), err
}

// Receipt records one reversible host-side action together with the exact
// arguments needed to undo it. No receipt ⇒ no write.
type Receipt struct {
	TS       time.Time `json:"ts"`
	Action   string    `json:"action"`
	CWD      string    `json:"cwd"`
	Before   string    `json:"before"`
	After    string    `json:"after"`
	UndoArgs []string  `json:"undoArgs"`
}

// ReceiptStore persists receipts as JSONL.
type ReceiptStore struct {
	Dir string
}

func (s ReceiptStore) path() string { return filepath.Join(s.Dir, "receipts.jsonl") }

// Append records a receipt.
func (s ReceiptStore) Append(r Receipt) error {
	if err := os.MkdirAll(s.Dir, 0o700); err != nil {
		return err
	}
	raw, err := json.Marshal(r)
	if err != nil {
		return err
	}
	f, err := os.OpenFile(s.path(), os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	defer f.Close()
	_, err = f.Write(append(raw, '\n'))
	return err
}

// Load reads receipts in insertion order.
func (s ReceiptStore) Load() ([]Receipt, error) {
	f, err := os.Open(s.path())
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	defer f.Close()
	out := make([]Receipt, 0)
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		var r Receipt
		if err := json.Unmarshal([]byte(line), &r); err != nil {
			continue
		}
		out = append(out, r)
	}
	return out, scanner.Err()
}

// UndoAll replays undo arguments in reverse order and returns how many
// succeeded. Failures are collected, not fatal: a partial undo is still better
// than leaving the user stuck with a rewritten config.
func (s ReceiptStore) UndoAll(ctx context.Context, git GitRunner) (int, error) {
	receipts, err := s.Load()
	if err != nil {
		return 0, err
	}
	done := 0
	var failed []string
	for i := len(receipts) - 1; i >= 0; i-- {
		r := receipts[i]
		if _, err := git(ctx, r.CWD, r.UndoArgs...); err != nil {
			failed = append(failed, r.Action+": "+err.Error())
			continue
		}
		done++
	}
	if len(failed) > 0 {
		return done, &UndoError{Failed: failed}
	}
	return done, nil
}

// UndoError reports receipts whose undo command failed.
type UndoError struct {
	Failed []string
}

func (e *UndoError) Error() string { return "netaccel: undo failed: " + strings.Join(e.Failed, "; ") }

// ApplyGitReadonly writes `url.<mirror>.insteadOf` for read-only traffic and
// records a receipt. It refuses to let the mirror anywhere near push: any
// mirror-tainted remote.origin.pushurl is removed.
func ApplyGitReadonly(ctx context.Context, store ReceiptStore, dir, mirrorBase string, git GitRunner) (*Receipt, error) {
	if mirrorBase == "" {
		return nil, nil
	}
	key := "url." + mirrorBase + ".insteadOf"
	before, _ := git(ctx, dir, "config", "--local", "--get", key)
	if _, err := git(ctx, dir, "config", "--local", key, OfficialPrefix); err != nil {
		return nil, err
	}
	if pushURL, err := git(ctx, dir, "config", "--local", "--get", "remote.origin.pushurl"); err == nil {
		if strings.Contains(pushURL, mirrorBase) {
			_, _ = git(ctx, dir, "config", "--local", "--unset", "remote.origin.pushurl")
		}
	}
	r := Receipt{
		TS:       time.Now(),
		Action:   "git.insteadOf",
		CWD:      dir,
		Before:   before,
		After:    mirrorBase,
		UndoArgs: []string{"config", "--local", "--unset", key},
	}
	if err := store.Append(r); err != nil {
		return nil, err
	}
	return &r, nil
}
