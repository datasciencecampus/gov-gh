# GitHub Copilot Instructions

## About this repository

`gov-gh` is a Python SDK for the GitHub REST and GraphQL APIs, built for use within UK government and public sector organisations (primarily the Office for National Statistics / Data Science Campus). It provides tools for GitHub organisation administration, repository governance, member and team management, issue operations, and workflow automation.

The package is intended for distribution via PyPI. It is currently in early development and the API is not yet stable.

## Package structure

Source code lives under `src/gov_gh/` (src layout). The intended module breakdown is:

| Module | Responsibility |
|---|---|
| `client.py` | GitHub API client and authentication handling |
| `config.py` | Configuration settings and environment variables |
| `issues.py` | Create, retrieve, update and manage issues |
| `members.py` | Manage organisation members, teams and permissions |
| `models.py` | Shared Pydantic models for all API data objects |
| `organisation.py` | Org-wide administration, governance and policy |
| `repositories.py` | Repository management operations |

## Language and tooling

- **Python 3.12+** — use modern Python features (e.g. `match`, `X | Y` union types, `tomllib`)
- **`uv`** — dependency and virtual environment management; do not use bare `pip install`
- **Ruff** — linting and formatting; line length 88, targets `E`, `F`, `I` rule sets
- **pytest** — test runner; tests live in `tests/`, named `test_<module>.py`
- **pre-commit** — hooks enforce secrets detection, large files, spelling, ruff lint and format

## Code conventions

### Public API and `__init__.py`

Every public function, class, and constant intended for use by package consumers must be explicitly listed in `src/gov_gh/__init__.py` using `__all__`. This defines the package's public API, ensures clean imports, and controls what is exposed when a user runs `from gov_gh import *`.

Private helpers (prefixed `_`) must not appear in `__all__` and should not be imported into `__init__.py`.

### Data models

All data objects passed to or returned from the GitHub API **must** be defined as [Pydantic](https://docs.pydantic.dev/) models in `models.py`. Do not use plain dicts or dataclasses for API payloads. Pydantic models provide validation, serialisation, and type safety.

### Testing

Every public function must have at least one unit test. Tests should be focused and fast. Use `pytest` fixtures and parametrize where appropriate. Do not write integration tests that call the live GitHub API.

- Use `pytest.mark.parametrize` for data-driven tests
- Use `pytest` fixtures for shared setup — avoid `setUp`/`tearDown` patterns
- Test files must include a module-level docstring describing what is being tested
- Each test function should have a docstring explaining the scenario and expected outcome
- Mock GitHub API calls using `pytest-mock` or `unittest.mock` — never call the live API in tests

### Style

- Follow [PEP 8](https://peps.python.org/pep-0008/) and let Ruff enforce it
- Prefer explicit over implicit; avoid unnecessary abstractions
- Keep functions small and single-purpose
- Type-annotate all function signatures using built-in types — do not import from `typing` where a modern equivalent exists:
  - Use `list[str]` not `List[str]`, `dict[str, int]` not `Dict[str, int]`
  - Use `str | None` not `Optional[str]`
  - Use `X | Y` unions not `Union[X, Y]`
  - `typing` imports are only acceptable for `TypeVar`, `Protocol`, `TypedDict`, `Annotated`, and `TYPE_CHECKING`

### Docstrings

All modules, classes, and public functions must have a [Google-style docstring](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings):

```python
def list_repos(self, org: str) -> list[Repository]:
    """List all repositories in a GitHub organisation.

    Args:
        org: The organisation login name.

    Returns:
        A list of Repository objects for the given organisation.

    Raises:
        GitHubAPIError: If the API request fails.
    """
```

- Module-level docstrings should describe the module's responsibility in one or two sentences
- Omit docstrings only for trivial one-liners where the signature is self-explanatory
- Always document `Args`, `Returns`, and `Raises` sections where applicable
- Include an `Example` section for functions with non-obvious behaviour, complex arguments, or multiple return shapes:

```python
def get_repo(self, org: str, name: str) -> Repository | None:
    """Retrieve a repository from a GitHub organisation.

    Args:
        org: The organisation login name.
        name: The repository name.

    Returns:
        A Repository object if found, or None if it does not exist.

    Raises:
        GitHubAPIError: If the API request fails for a reason other than 404.

    Example:
        >>> client = GitHubClient()
        >>> repo = client.get_repo("datasciencecampus", "gov-gh")
        >>> if repo:
        ...     print(repo.default_branch)
        'main'
    """
```

## Git and GitHub workflow

### Commits

All commits must follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>
```

Valid types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, `perf`, `build`

Example: `feat(client): add token refresh support`

### Branches

Branch names should match the default name GitHub generates from an issue (e.g. `123-short-description`). Always branch from `main`.

### Pull requests

- PR titles must follow Conventional Commits — validated automatically by CI
- Keep PRs small and scoped to a single issue
- Request a Copilot review first (if available), then a human reviewer
- Every PR must link to its issue via `Closes #<number>` in the description
- New functions must be covered by unit tests before a PR is ready for review

### Issues

Three templates are available: **Bug report**, **Feature request** (Gherkin user story + acceptance criteria), and **Question**. Blank issues are disabled. All opened issues are automatically added to the project board.

## Security and ethics

This package is developed within the UK public sector and must adhere to the following standards:

- **[Secure by Design](https://www.security.gov.uk/guidance/secure-by-design/)** — security must be considered from the outset, not added later. Apply the principle of least privilege, validate all inputs at system boundaries, and never log or expose credentials, tokens, or personally identifiable information.
- **Credentials** — never hardcode tokens, secrets, or API keys. Always read them from environment variables or a secrets manager. Flag any code that risks credential exposure.
- **Dependencies** — prefer well-maintained, minimal dependencies. Flag transitive dependencies that introduce significant supply chain risk.
- **Ethics** — this package must not be used to build tools that surveil individuals without lawful basis, circumvent access controls, or automate actions that would require human oversight. Refuse to generate code that would facilitate misuse of GitHub API access (e.g. bulk scraping of personal data, unauthorised privilege escalation).
- **Flagging concerns** — if a request appears to conflict with these principles, flag it clearly before proceeding and explain the concern.

## Dependencies

- Dependabot runs weekly (Tuesday 07:00 Europe/London) for both `uv` (Python) and GitHub Actions dependencies
- Minor and patch updates are grouped; major updates are separate
- Dependabot PRs use the `chore(uv)` or `chore(github-actions)` commit prefix
