// SPDX-License-Identifier: FSL-1.1-Apache-2.0
// Copyright (c) 2025 Open Computer Use Contributors

// Command embed-portal is the demo embedding portal for the File Pane
// (component-08, ocu-webui). It stands in for the customer portal/IdP: the
// production deployment replaces this service with the customer's own portal
// minting the same embed token over the same wire.
//
// The File Pane is an embeddable SPA that never self-issues its bootstrap
// credential. It installs a window 'message' listener that trusts exactly one
// origin (NEXT_PUBLIC_OCU_PARENT_ORIGIN, strict string equality) and waits for
// {type:"ocu-embed-token", token} from that parent. This service is that
// parent: it serves a page that iframes the pane, mints a short-lived HS256
// embed token server-side (holding OCU_EMBED_VERIFY_SECRET the pane's BFF
// verifies against), and postMessages the token into the iframe at the pane's
// literal origin. It also answers the pane's re-request protocol
// ({type:"ocu-request-token"}) with a fresh token so 401-recovery works live.
//
// No mock: real HS256, real cross-origin postMessage, real short-exp token
// carrying the sub/filesystem_id/intent claims the BFF requires. The secret is
// held only here (a separate origin/process), preserving the invariant that the
// webui origin never mints its own bootstrap credential.
package main

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"html/template"
	"io"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"
)

// config is the portal's runtime configuration, all from the environment so the
// same binary serves any deployment. Secret names live here only.
type config struct {
	listen       string // e.g. ":3003"
	paneOrigin   string // the pane's literal origin, e.g. http://localhost:3000
	embedSecret  string // OCU_EMBED_VERIFY_SECRET — the HMAC key (raw ASCII, per the BFF)
	audience     string // OCU_EMBED_AUDIENCE — must name the pane surface (ocu-webui)
	subject      string // demo caller identity asserted as `sub`
	filesystemID string // the BASE provisioned filesystem the F9 leg accepts (fs-fleet)
	intent       string // storage intent axis: read | write | preview
	tokenTTL     time.Duration

	// D5 per-chat scope resolution (ADR-0030). The portal embeds the pane for a
	// specific chat; the token it mints must carry that chat's derived scope so
	// the pane's cooperative file view lines up with the guest's isolated subtree.
	// The chat context arrives as a `?chat=<id>` query param on the embed page, or
	// falls back to demoChatID.
	demoChatID string // DEMO_CHAT_ID - chat context when the embed carries no ?chat=

	// controlStatusURL, when set, is control's caller-scoped status verb
	// (https://control:9466/v1alpha/sessions/status). The portal POSTs
	// {session_hint:<chat>} over mTLS and reads effective_scope - the SAME
	// attested owner form the guest is minted with, so pane and guest agree by
	// construction. Unset -> the portal deterministically derives a per-chat scope
	// locally (the north face is client-cooperative in v1; the status verb is the
	// production path).
	controlStatusURL  string // OCU_CONTROL_STATUS_URL
	controlClientCert string // OCU_CONTROL_CLIENT_CERT - mTLS client leaf (PEM)
	controlClientKey  string // OCU_CONTROL_CLIENT_KEY - mTLS client key (PEM)
	controlCACert     string // OCU_CONTROL_CA_CERT - CA that signs control's gateway leaf (PEM)
}

func loadConfig() (config, error) {
	c := config{
		listen:       envOr("LISTEN", ":3003"),
		paneOrigin:   envOr("PANE_ORIGIN", "http://localhost:3000"),
		embedSecret:  os.Getenv("OCU_EMBED_VERIFY_SECRET"),
		audience:     envOr("OCU_EMBED_AUDIENCE", "ocu-webui"),
		subject:      envOr("DEMO_SUBJECT", "demo-user"),
		filesystemID: envOr("DEMO_FILESYSTEM_ID", "fs-fleet"),
		intent:       envOr("DEMO_INTENT", "write"),

		demoChatID:        os.Getenv("DEMO_CHAT_ID"),
		controlStatusURL:  os.Getenv("OCU_CONTROL_STATUS_URL"),
		controlClientCert: os.Getenv("OCU_CONTROL_CLIENT_CERT"),
		controlClientKey:  os.Getenv("OCU_CONTROL_CLIENT_KEY"),
		controlCACert:     os.Getenv("OCU_CONTROL_CA_CERT"),
	}
	// The BFF enforces exp-iat <= 120s; stay well under it.
	ttlSecs := 60
	if v := os.Getenv("TOKEN_TTL_SECONDS"); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil || n <= 0 || n > 120 {
			return c, fmt.Errorf("TOKEN_TTL_SECONDS must be 1..120, got %q", v)
		}
		ttlSecs = n
	}
	c.tokenTTL = time.Duration(ttlSecs) * time.Second

	if len(c.embedSecret) < 32 {
		return c, fmt.Errorf("OCU_EMBED_VERIFY_SECRET must be >= 32 bytes (got %d)", len(c.embedSecret))
	}
	if c.intent != "read" && c.intent != "write" && c.intent != "preview" {
		return c, fmt.Errorf("DEMO_INTENT must be read|write|preview, got %q", c.intent)
	}
	return c, nil
}

func envOr(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

// resolveScope resolves the storage scope to mint for chatID. An empty chatID
// (no ?chat= and no DEMO_CHAT_ID) means "no chat context" and mints the BASE
// filesystemID - today's behaviour.
//
// With a chat context and a configured control status verb, it POSTs
// {session_hint:chatID} to control over mTLS and returns the attested
// effective_scope - the SAME owner form the guest is minted with, so pane and
// guest agree by construction. A miss (no status URL, transport error, non-2xx,
// or an absent effective_scope) falls back to a portal-local DETERMINISTIC
// derivation: "<base>-<16 hex>" over chatID, distinct per chat. That fallback is
// the file-pane's cooperative view (the north face is client-cooperative in v1,
// ADR-0030); it is NOT the attested owner form and keys no authority - the
// guest's minted Storage-JWT claim is the real isolation.
func (c config) resolveScope(ctx context.Context, chatID string) string {
	if chatID == "" {
		return c.filesystemID
	}
	if c.controlStatusURL != "" {
		if scope, ok := c.resolveScopeViaStatusVerb(ctx, chatID); ok {
			return scope
		}
	}
	return deriveChatScope(c.filesystemID, chatID)
}

// resolveScopeViaStatusVerb POSTs the caller-scoped status verb over mTLS and
// reads effective_scope. Returns (scope,true) only on a 2xx carrying a non-empty
// effective_scope; every other outcome is (_, false) so resolveScope can fall
// back deterministically without ever raising.
func (c config) resolveScopeViaStatusVerb(ctx context.Context, chatID string) (string, bool) {
	tlsCfg, err := c.controlTLSConfig()
	if err != nil {
		log.Printf("embed-portal: control mTLS config error: %v", err)
		return "", false
	}
	client := &http.Client{
		Timeout:   5 * time.Second,
		Transport: &http.Transport{TLSClientConfig: tlsCfg},
	}
	body, _ := json.Marshal(map[string]string{"session_hint": chatID})
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.controlStatusURL, bytes.NewReader(body))
	if err != nil {
		return "", false
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	req.Header.Set("X-Chat-Id", chatID)
	resp, err := client.Do(req)
	if err != nil {
		log.Printf("embed-portal: status verb miss for chat %q: %v", chatID, err)
		return "", false
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", false
	}
	var out struct {
		EffectiveScope string `json:"effective_scope"`
	}
	if err := json.NewDecoder(io.LimitReader(resp.Body, 1<<16)).Decode(&out); err != nil {
		return "", false
	}
	if out.EffectiveScope == "" {
		return "", false
	}
	return out.EffectiveScope, true
}

// controlTLSConfig builds the mTLS client config from the configured cert/key/CA.
func (c config) controlTLSConfig() (*tls.Config, error) {
	if c.controlClientCert == "" || c.controlClientKey == "" || c.controlCACert == "" {
		return nil, fmt.Errorf("mTLS material incomplete (need cert, key, CA)")
	}
	cert, err := tls.LoadX509KeyPair(c.controlClientCert, c.controlClientKey)
	if err != nil {
		return nil, err
	}
	caPEM, err := os.ReadFile(c.controlCACert)
	if err != nil {
		return nil, err
	}
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM(caPEM) {
		return nil, fmt.Errorf("no CA cert parsed from %q", c.controlCACert)
	}
	return &tls.Config{
		Certificates: []tls.Certificate{cert},
		RootCAs:      pool,
		MinVersion:   tls.VersionTLS12,
	}, nil
}

// deriveChatScope is the portal-local COOPERATIVE derivation used when the status
// verb is unavailable: lowercase-hex SHA-256 over a domain-separated, chat-scoped
// pre-image, truncated to 16 hex, appended as "<base>-<hex>". Deterministic (same
// chat -> same scope) and distinct across chats. This is the file-pane's view, NOT
// the attested owner form control mints (control's derivation is control-only); it
// keys no authority.
func deriveChatScope(base, chatID string) string {
	h := sha256.New()
	// Domain separator keeps this pre-image disjoint from any other hash use.
	h.Write([]byte("ocu-portal-scope-v1\x00"))
	h.Write([]byte(base))
	h.Write([]byte("\x00"))
	h.Write([]byte(chatID))
	suffix := hex.EncodeToString(h.Sum(nil))[:16]
	return base + "-" + suffix
}

// mintToken builds a fresh HS256 embed JWT carrying the claims the BFF requires:
// aud (must equal the configured audience), exp (<= 120s after iat), and the
// scope triple sub/filesystem_id/intent the BFF sources from the attested token.
// The filesystem_id is the chat's resolved scope (per-chat when a chat context is
// present, else the base).
func (c config) mintToken(ctx context.Context, chatID string) (string, error) {
	scope := c.resolveScope(ctx, chatID)
	now := time.Now()
	header := map[string]string{"alg": "HS256", "typ": "JWT"}
	claims := map[string]any{
		"aud":           c.audience,
		"iat":           now.Unix(),
		"exp":           now.Add(c.tokenTTL).Unix(),
		"sub":           c.subject,
		"filesystem_id": scope,
		"intent":        c.intent,
	}
	hb, err := json.Marshal(header)
	if err != nil {
		return "", err
	}
	cb, err := json.Marshal(claims)
	if err != nil {
		return "", err
	}
	signingInput := b64(hb) + "." + b64(cb)
	mac := hmac.New(sha256.New, []byte(c.embedSecret))
	mac.Write([]byte(signingInput))
	sig := b64(mac.Sum(nil))
	return signingInput + "." + sig, nil
}

func b64(b []byte) string { return base64.RawURLEncoding.EncodeToString(b) }

// portalPage is the embedding parent document. It iframes the pane, delivers a
// token on iframe load, and re-delivers on the pane's re-request. The pane's
// literal origin is injected as a template value so postMessage targetOrigin is
// never a wildcard.
var portalPage = template.Must(template.New("portal").Parse(`<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Open Computer Use — Demo Embedding Portal</title>
<style>
  html,body{margin:0;height:100%;font-family:system-ui,sans-serif;background:#0b1020;color:#e6e9f2}
  header{padding:8px 14px;background:#141a30;border-bottom:1px solid #263056;font-size:14px}
  header b{color:#8ab4ff}
  #frame{width:100%;height:calc(100% - 38px);border:0;display:block;background:#fff}
  #err{color:#ff9c9c}
</style>
</head>
<body>
<header>Demo embedding portal — stands in for the customer portal/IdP. Pane: <b>{{.PaneOrigin}}</b> <span id="err"></span></header>
<iframe id="frame" src="{{.PaneOrigin}}" title="Open Computer Use File Pane"></iframe>
<script>
  var PANE_ORIGIN = {{.PaneOriginJSON}};
  var frame = document.getElementById("frame");
  var errEl = document.getElementById("err");

  // Forward the embed page's ?chat=<id> to /token so the minted token carries
  // this chat's per-chat scope (D5). Absent -> the portal mints the base.
  var CHAT_ID = new URLSearchParams(window.location.search).get("chat") || "";

  function fetchToken() {
    var tokenURL = CHAT_ID ? ("/token?chat=" + encodeURIComponent(CHAT_ID)) : "/token";
    return fetch(tokenURL, { credentials: "same-origin" })
      .then(function (r) { if (!r.ok) throw new Error("token http " + r.status); return r.json(); })
      .then(function (j) { return j.token; });
  }

  function deliver() {
    fetchToken().then(function (token) {
      // targetOrigin is the pane's literal origin — never "*".
      frame.contentWindow.postMessage({ type: "ocu-embed-token", token: token }, PANE_ORIGIN);
    }).catch(function (e) { errEl.textContent = "token mint failed: " + e.message; });
  }

  // Deliver on first load.
  frame.addEventListener("load", deliver);

  // Answer the pane's re-request protocol (fired by reBootstrap on a 401): the
  // pane posts {type:"ocu-request-token"} from its origin; we re-mint and re-post.
  window.addEventListener("message", function (event) {
    if (event.origin !== PANE_ORIGIN) return;            // strict origin trust
    if (!event.data || event.data.type !== "ocu-request-token") return;
    deliver();
  });
</script>
</body>
</html>`))

func main() {
	cfg, err := loadConfig()
	if err != nil {
		log.Fatalf("embed-portal: config error: %v", err)
	}

	mux := http.NewServeMux()

	// GET / — the embedding portal page.
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		paneJSON, _ := json.Marshal(cfg.paneOrigin)
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Header().Set("Cache-Control", "no-store")
		_ = portalPage.Execute(w, map[string]any{
			"PaneOrigin":     cfg.paneOrigin,
			"PaneOriginJSON": template.JS(paneJSON),
		})
	})

	// GET /token - mint a fresh short-lived embed token per call. The chat context
	// (?chat=<id>, else DEMO_CHAT_ID) selects the per-chat scope minted into the token.
	mux.HandleFunc("/token", func(w http.ResponseWriter, r *http.Request) {
		chatID := r.URL.Query().Get("chat")
		if chatID == "" {
			chatID = cfg.demoChatID
		}
		tok, err := cfg.mintToken(r.Context(), chatID)
		if err != nil {
			http.Error(w, "mint failed", http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Cache-Control", "no-store")
		_ = json.NewEncoder(w).Encode(map[string]string{"token": tok})
	})

	// GET /healthz — liveness for compose.
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})

	srv := &http.Server{
		Addr:              cfg.listen,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}
	log.Printf("embed-portal: listening on %s, iframing pane %s, minting aud=%q fs=%q intent=%q ttl=%s",
		cfg.listen, cfg.paneOrigin, cfg.audience, cfg.filesystemID, cfg.intent, cfg.tokenTTL)
	log.Fatal(srv.ListenAndServe())
}
