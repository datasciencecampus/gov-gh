# gov-gh

> Python SDK for GitHub REST and GraphQL APIs, built for government organisations.
> [!WARNING]
> This project is in early development. The API is not stable and the package is not yet available on PyPI.

`gov-gh` provides tools for GitHub organisation administration, repository governance, issue management, and workflow automation — designed for use within UK government and public sector organisations.

## About

Managing GitHub organisations at scale requires consistent, repeatable tooling. `gov-gh` wraps the GitHub REST and GraphQL APIs into a clean Python interface, covering:

- **Organisation administration** — governance policies, settings, and org-wide operations
- **Repository management** — create, configure, and govern repositories
- **Member & team management** — manage organisation members, teams, and permissions
- **Issue operations** — create, retrieve, update, and close issues programmatically
- **Workflow automation** — scripted operations suitable for CI/CD pipelines and scheduled tasks

## Package structure

```text
gov-gh/
├── src/
│   └── gov_gh/
│       ├── __init__.py          # Package exports and version information
│       ├── auth.py              # Shared authentication headers
│       ├── client.py            # Top-level GraphQL facade
│       ├── exceptions.py        # Package-specific exceptions
│       ├── graphql.py           # GraphQL execution and pagination
│       ├── rest.py              # Placeholder for future REST support
│       └── retry.py             # Shared retry policy
```

## Installation

> [!NOTE]
> The package is not yet published to PyPI. Once released, it will be installable as follows.

Requires Python 3.12 or later. Install with `pip`:

```bash
pip install gov-gh
```

Or using `uv`:

```bash
uv add gov-gh
```

### Authentication

`gov-gh` authenticates against the GitHub API using a personal access token (PAT) or a GitHub App. Set your credentials via environment variables:

```bash
export GITHUB_TOKEN="ghp_..."
```

See [configs/](configs/) for available configuration options.

## Development

Requires Python >= 3.12 and [`uv`](https://docs.astral.sh/uv/).

```bash
# Install dependencies
uv sync --group dev

# Enable pre-commit hooks
uvx pre-commit install --hook-type pre-commit --hook-type commit-msg

# Run tests
uv run pytest

# Lint and format
uv run ruff check .
uv run ruff format .
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contribution workflow, code standards, and PR guidelines.

## License

<!-- Unless stated otherwise, the codebase is released under [the MIT Licence][mit]. -->

The code, unless otherwise stated, is released under [the MIT Licence][mit].

The documentation for this work is subject to [© Crown copyright][copyright] and is available under the terms of the [Open Government 3.0][ogl] licence.

[mit]: LICENSE
[copyright]: http://www.nationalarchives.gov.uk/information-management/re-using-public-sector-information/uk-government-licensing-framework/crown-copyright/
[ogl]: http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/
