// SPDX-License-Identifier: FSL-1.1-Apache-2.0
// Copyright (c) 2025 Open Computer Use Contributors

package main

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"strings"
	"testing"
	"time"
)

// tokenScope decodes the minted JWT and returns its filesystem_id claim.
func tokenScope(t *testing.T, tok string) string {
	t.Helper()
	parts := strings.Split(tok, ".")
	if len(parts) != 3 {
		t.Fatalf("token is not a 3-part JWT: %q", tok)
	}
	cb, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		t.Fatalf("decode claims: %v", err)
	}
	var claims struct {
		FilesystemID string `json:"filesystem_id"`
	}
	if err := json.Unmarshal(cb, &claims); err != nil {
		t.Fatalf("unmarshal claims: %v", err)
	}
	return claims.FilesystemID
}

func testConfig() config {
	return config{
		audience:     "ocu-webui",
		subject:      "demo-user",
		filesystemID: "fs-fleet",
		intent:       "write",
		embedSecret:  strings.Repeat("k", 32),
		tokenTTL:     60 * time.Second,
		// controlStatusURL unset -> deterministic per-chat derivation (the
		// cooperative fallback path this keystone exercises).
	}
}

// TestMintTokenDistinctScopePerChat is the load-bearing keystone: two different
// chat contexts mint tokens carrying DISTINCT filesystem_id claims. Red-probe:
// if mintToken ignores the chat context (always the base), the distinct-scope
// assertion REDs.
func TestMintTokenDistinctScopePerChat(t *testing.T) {
	cfg := testConfig()
	ctx := context.Background()

	tokA, err := cfg.mintToken(ctx, "chat-a")
	if err != nil {
		t.Fatalf("mint A: %v", err)
	}
	tokB, err := cfg.mintToken(ctx, "chat-b")
	if err != nil {
		t.Fatalf("mint B: %v", err)
	}

	scopeA := tokenScope(t, tokA)
	scopeB := tokenScope(t, tokB)

	if scopeA == scopeB {
		t.Fatalf("two chats minted the SAME scope %q; per-chat isolation is vacuous", scopeA)
	}
	// Both are derived from the base (prefix "fs-fleet-"), never the bare base.
	for name, s := range map[string]string{"chat-a": scopeA, "chat-b": scopeB} {
		if !strings.HasPrefix(s, "fs-fleet-") {
			t.Errorf("%s scope %q lacks the base-derived prefix", name, s)
		}
		if s == "fs-fleet" {
			t.Errorf("%s scope collapsed to the bare base", name)
		}
	}
}

// TestMintTokenDeterministicPerChat: the SAME chat context always mints the SAME
// scope (the pane can re-request a token on 401 and land on the same subtree).
func TestMintTokenDeterministicPerChat(t *testing.T) {
	cfg := testConfig()
	ctx := context.Background()

	tok1, _ := cfg.mintToken(ctx, "chat-a")
	tok2, _ := cfg.mintToken(ctx, "chat-a")

	if s1, s2 := tokenScope(t, tok1), tokenScope(t, tok2); s1 != s2 {
		t.Fatalf("same chat minted different scopes %q vs %q", s1, s2)
	}
}

// TestMintTokenNoChatContextMintsBase: no chat context -> the base scope (today's
// behaviour), never a derived one.
func TestMintTokenNoChatContextMintsBase(t *testing.T) {
	cfg := testConfig()
	tok, err := cfg.mintToken(context.Background(), "")
	if err != nil {
		t.Fatalf("mint: %v", err)
	}
	if scope := tokenScope(t, tok); scope != "fs-fleet" {
		t.Fatalf("no-chat token scope = %q, want the base fs-fleet", scope)
	}
}

// TestDeriveChatScopeShape pins the derived form: "<base>-<16 lowercase hex>".
func TestDeriveChatScopeShape(t *testing.T) {
	got := deriveChatScope("fs-fleet", "chat-a")
	if !strings.HasPrefix(got, "fs-fleet-") {
		t.Fatalf("derived scope %q lacks base prefix", got)
	}
	suffix := strings.TrimPrefix(got, "fs-fleet-")
	if len(suffix) != 16 {
		t.Fatalf("derived suffix %q is %d chars, want 16", suffix, len(suffix))
	}
	for _, r := range suffix {
		if !((r >= '0' && r <= '9') || (r >= 'a' && r <= 'f')) {
			t.Fatalf("derived suffix %q is not lowercase hex", suffix)
		}
	}
}
