# open-computer-use Helm chart repository

This branch is the GitHub Pages source for the stable Helm chart channel:

```bash
helm repo add open-computer-use https://wide-moat.github.io/open-computer-use
helm repo update
helm install ocu open-computer-use/computer-use-server
```

Stable chart versions land here automatically on every `v*` git tag (excluding pre-releases).

Pre-release (`-rc.N`, `-alpha.N`, `-beta.N`) charts are NOT published here — they go to OCI:

```bash
helm install ocu oci://ghcr.io/wide-moat/charts/computer-use-server --version X.Y.Z-rc.N
```

See https://github.com/Wide-Moat/open-computer-use/tree/main/helm/computer-use-server for the chart source.
