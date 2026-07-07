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
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"html/template"
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
	filesystemID string // the provisioned filesystem the F9 leg accepts (fs-fleet)
	intent       string // storage intent axis: read | write | preview
	tokenTTL     time.Duration
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

// mintToken builds a fresh HS256 embed JWT carrying the claims the BFF requires:
// aud (must equal the configured audience), exp (<= 120s after iat), and the
// scope triple sub/filesystem_id/intent the BFF sources from the attested token.
func (c config) mintToken() (string, error) {
	now := time.Now()
	header := map[string]string{"alg": "HS256", "typ": "JWT"}
	claims := map[string]any{
		"aud":           c.audience,
		"iat":           now.Unix(),
		"exp":           now.Add(c.tokenTTL).Unix(),
		"sub":           c.subject,
		"filesystem_id": c.filesystemID,
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

  function fetchToken() {
    return fetch("/token", { credentials: "same-origin" })
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

	// GET /token — mint a fresh short-lived embed token per call.
	mux.HandleFunc("/token", func(w http.ResponseWriter, r *http.Request) {
		tok, err := cfg.mintToken()
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
