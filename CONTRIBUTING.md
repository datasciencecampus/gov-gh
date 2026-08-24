# Contributing

## Contributions policy

This is a **public repository**, but unsolicited pull requests will not be accepted.

If you have a bug report, feature request, or suggestion, please [open an issue](../../issues/new/choose). Three templates are available — choose the one that best fits:

- **Bug report** — something is broken or not working as expected
- **Feature request** — uses a user story (`As a / I want / So that`) and Gherkin acceptance criteria (`Given / When / Then`) to define the scope clearly
- **Question** — anything else

Blank issues are disabled; all issues must use a template. Opened or reopened issues and pull requests are automatically routed to the project board. The maintainers may then invite you to contribute an implementation. Contributions outside of this process will be closed without review.

## Workflow

1. **Open an issue** using the appropriate template. For feature requests, complete the user story and acceptance criteria — these define the scope of the work and inform test cases.
2. **Create a branch** from the issue. Use the default branch name GitHub suggests when you click *Create a branch* from within the issue (e.g. `123-short-description`).
3. **Make changes scoped to the issue.** Avoid bundling unrelated changes — each branch should address a single issue.
4. **Open a pull request** against `main` when ready.

## Pull request guidelines

- Keep PRs small and focused so they are easy to review.
- If you have the GitHub Copilot code review feature enabled, request a Copilot review before requesting a human review.
- Once Copilot review is complete (or if unavailable), request a human reviewer from the maintainer team.
- A maintainer must approve the PR before it is merged.

## Repository automation

Project-routing workflows run automatically when issues or pull requests are opened or reopened. They dispatch reusable workflows from the `datasciencecampus/github-actions` repository to add items to the organisation project board.

To keep these workflows working, configure the following repository settings:

- `PROJECT_ROUTER_BOT_APP_ID` repository variable: the GitHub App client ID used to mint the dispatch token
- `PROJECT_ROUTER_BOT_PEM` repository secret: the GitHub App private key in PEM format

## Code standards

### Testing

All new functions must have corresponding unit tests. Tests live in `tests/` and follow the `test_<module>.py` naming convention. Run the test suite with:

```bash
uv run pytest
```

### Data models

All data objects passed to or returned from the GitHub API must be defined as [Pydantic](https://docs.pydantic.dev/) models in `src/gov_gh/models.py`. This ensures consistent validation, serialisation, and type safety across the package.

### Style

Code is linted and formatted with [Ruff](https://docs.astral.sh/ruff/). Run checks before committing:

```bash
uv run ruff check .
uv run ruff format .
```

Pre-commit hooks will enforce this automatically if installed:

```bash
uvx pre-commit install --hook-type pre-commit --hook-type commit-msg
```
