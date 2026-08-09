# Vendored OCSF class schemas

The payload schemas `audit-fanin.asyncapi.yaml` references, pinned at the
version in the directory name.

They are vendored rather than `$ref`'d at `https://schema.ocsf.io/...` because a
contract gate must not depend on a third-party host being reachable. Validating
the remote form made 16 requests per run and failed intermittently with
`FetchError: Client network socket disconnected`, so a green meant "schema.ocsf.io
answered today" rather than "the document is valid".

Vendoring also makes the OCSF version an auditable artifact: the bytes the gate
validated are the bytes in the commit, and a version move is a reviewable diff
rather than whatever the host serves.

## Updating

Fetch each class the contract references and drop it in a directory named for
the new version, then repoint the `$ref`s:

```sh
for c in api_activity authentication dns_activity entity_management \
         file_activity http_activity network_activity process_activity; do
  curl -sS "https://schema.ocsf.io/api/<version>/classes/$c" \
    -o "contracts/audit/ocsf/<version>/$c.json"
done
```

Each file must parse as JSON and carry a `name` matching its filename and the
`uid` of the OCSF class. The contracts-lint `asyncapi` job fails if a referenced
file is missing or unparseable — deleting one reds it with `ENOENT`, corrupting
one reds it with a parse error.
