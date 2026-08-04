#!/usr/bin/env bash
# SPDX-License-Identifier: FSL-1.1-Apache-2.0
# Copyright (c) 2025 Open Computer Use Contributors
#
# Generate the gateway<->control mTLS PKI for a LOCAL fleet bring-up. The
# private keys are dev-only and are NEVER committed (see .gitignore); this
# script regenerates them per checkout so a clone carries no key material.
#
# It mints three things into ./gateway-pki/:
#   - ca.pem / ca.key          a self-signed dev CA (Ed25519)
#   - server.pem / server.key  the control gateway-plane leaf, SAN
#                              DNS:control, DNS:localhost, IP:127.0.0.1
#                              (serverAuth) — what control presents on :9466
#   - client.pem / client.key  the MCP-gateway caller leaf, SAN
#                              URI:spiffe://ocu-fleet/internal-workforce/mcp-gateway
#                              (clientAuth) — what the gateway presents dialing in
#
# The URI SAN is the identity control's CertSANResolver maps to
# Identity{Tenant: internal-workforce, Caller: mcp-gateway}. Changing it here
# without changing the resolver breaks admission — keep them in lockstep.
#
# Usage:  ./gen-gateway-pki.sh            # idempotent: skips if certs present
#         ./gen-gateway-pki.sh --force    # re-mint from scratch

set -euo pipefail
cd "$(dirname "$0")"

PKI_DIR="gateway-pki"
FORCE="${1:-}"

if [[ "$FORCE" == "--force" ]]; then
  rm -rf "$PKI_DIR"
fi

# Presence is not validity. The CA below is minted for 30 days, so a guard that
# only asks "does the file exist" pins the stand to an expired chain: control
# rejects the gateway's handshake, every session create fails, and the suite
# retries into a dead mTLS for as long as it is allowed to. Measured 2026-08-04:
# the chain expired at 13:53:20, the first refusal landed 44s later, and this
# script answered "already present" to every attempt to recover.
#
# Ask the certificates instead. -checkend takes seconds and is true when the
# cert is STILL valid that far ahead, so re-mint whenever any leaf falls inside
# the renewal window.
RENEW_WITHIN_S="${RENEW_WITHIN_S:-172800}"   # 48h

pki_is_fresh() {
  local f
  for f in "$PKI_DIR/ca.pem" "$PKI_DIR/server.pem" "$PKI_DIR/client.pem"; do
    [[ -f "$f" ]] || return 1
    openssl x509 -in "$f" -noout -checkend "$RENEW_WITHIN_S" >/dev/null 2>&1 || return 1
  done
  return 0
}

if pki_is_fresh; then
  echo "gateway-pki: certs present and valid beyond ${RENEW_WITHIN_S}s (pass --force to re-mint)"
  exit 0
fi

if [[ -f "$PKI_DIR/ca.pem" ]]; then
  echo "gateway-pki: existing chain is expired or expires within ${RENEW_WITHIN_S}s -- re-minting"
  # A re-mint replaces the CA, so every leaf signed by the old one must go too,
  # including any this script does not itself produce (portal). Preserve their
  # key + csr + cnf so they can be re-signed against the new CA below.
  rm -f "$PKI_DIR"/*.pem "$PKI_DIR"/*.srl
fi

mkdir -p "$PKI_DIR"
cd "$PKI_DIR"

# --- CA (Ed25519, self-signed) ---
openssl genpkey -algorithm ed25519 -out ca.key
openssl req -x509 -new -key ca.key -sha256 -days 30 \
  -subj "/CN=ocu-fleet-gateway-dev-ca" -out ca.pem

# --- server leaf (control gateway plane, serverAuth) ---
cat > server.cnf <<'EOF'
[req]
distinguished_name = dn
req_extensions = v3
prompt = no
[dn]
CN = control-gateway
[v3]
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = DNS:control, DNS:localhost, IP:127.0.0.1
EOF
openssl genpkey -algorithm ed25519 -out server.key
openssl req -new -key server.key -out server.csr -config server.cnf
openssl x509 -req -in server.csr -CA ca.pem -CAkey ca.key -CAcreateserial \
  -days 30 -extfile server.cnf -extensions v3 -out server.pem

# --- client leaf (MCP-gateway caller, clientAuth, SPIFFE URI SAN) ---
cat > client.cnf <<'EOF'
[req]
distinguished_name = dn
req_extensions = v3
prompt = no
[dn]
CN = mcp-gateway-client
[v3]
basicConstraints = CA:FALSE
keyUsage = digitalSignature
extendedKeyUsage = clientAuth
subjectAltName = URI:spiffe://ocu-fleet/internal-workforce/mcp-gateway
EOF
openssl genpkey -algorithm ed25519 -out client.key
openssl req -new -key client.key -out client.csr -config client.cnf
openssl x509 -req -in client.csr -CA ca.pem -CAkey ca.key -CAcreateserial \
  -days 30 -extfile client.cnf -extensions v3 -out client.pem

# Leaves this script does not mint itself (portal, and anything added later)
# still carry a key + csr + cnf here and were signed by the CA we just
# replaced. Re-sign them, or a re-mint silently drops a client that other
# services depend on: the embed-portal is what the File Pane bootstraps
# through, and losing it is not visible until a browser tries.
for csr in *.csr; do
  base="${csr%.csr}"
  [[ "$base" == "client" || "$base" == "server" ]] && continue
  [[ -f "$base.cnf" ]] || continue
  openssl x509 -req -in "$csr" -CA ca.pem -CAkey ca.key -CAcreateserial \
    -days 30 -extfile "$base.cnf" -extensions v3 -out "$base.pem" >/dev/null 2>&1
  echo "gateway-pki: re-signed $base.pem against the new CA"
done

# openssl writes keys 0600. The services that read this directory run as other
# UIDs and mount it read-only, so 0600 boots control into
# "gateway tls key pair: permission denied" -- measured 2026-08-04. This is a
# dev CA on a local stand; match the permissions the stack was built against.
chmod 644 *.key *.pem 2>/dev/null || true

# Lock down the private keys.
chmod 600 ca.key server.key client.key

echo "gateway-pki: minted CA + server (DNS:control) + client (spiffe://ocu-fleet/internal-workforce/mcp-gateway) into $PWD"
