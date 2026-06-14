# Contributing to Open Computer Use

Thank you for your interest! PRs and issues welcome.

## Getting Started

1. Fork the repository
2. Clone: `git clone https://github.com/your-username/open-computer-use.git`
3. Branch: `git checkout -b feature/your-feature`

## Git hooks

Install the versioned pre-push hook once per clone. It blocks pushes that
carry `.planning/` artefacts to the public remote, and pushes where a personal
email address (defined in the identity-email detector) appears in tracked file
content — rewrite it to `developer@widemoat.ai`:

```bash
ln -sf ../../scripts/githooks/pre-push .git/hooks/pre-push
```

The same content check runs in CI (`identity-lint` workflow) as a backstop.

## Development

```bash
cp .env.example .env
# Edit .env with your API key

# Build sandbox image
docker build --platform linux/amd64 -t open-computer-use:latest .

# Run tests
./tests/test-no-corporate.sh
./tests/test-project-structure.sh
./tests/test-docker-image.sh open-computer-use:latest

# Run full stack
docker compose up --build
```

## Testing

Before submitting a PR, all tests must pass:

```bash
./tests/test-no-corporate.sh       # No corporate references
./tests/test-project-structure.sh   # Correct directory structure
./tests/test-docker-image.sh        # Docker image validation
```

## Pull Request Process

1. All tests pass
2. Documentation updated if needed
3. Clear PR description
4. Reference related issues

## Creating Skills

1. Create a directory under `skills/public/` or `skills/examples/`
2. Include `SKILL.md` with name, description, usage examples
3. Put scripts in `scripts/` subdirectory

See [docs/DYNAMIC-SKILLS.md](docs/DYNAMIC-SKILLS.md) for the skill format.

## License

By contributing to this project, you agree that:

- Contributions to `skills/public/describe-image/` and `skills/public/sub-agent/` are licensed under the [MIT License](LICENSE-MIT).
- Contributions to all other directories (except third-party skills) are licensed under the [Functional Source License, Version 1.1, Apache 2.0 Future License](LICENSE) (FSL-1.1-Apache-2.0).

See [NOTICE](NOTICE) for the full licensing model.

## Release Process — FSL Apache conversion

Under FSL-1.1-Apache-2.0, each release automatically converts to Apache-2.0 two
years after publication. No per-release LICENSE edit is required — the Grant
of Future License clause in `LICENSE` carries this forward. When publishing a
release, just tag the commit; conversion happens automatically on the second
anniversary of the tag date.
