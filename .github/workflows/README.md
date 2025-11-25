# GitHub Actions Workflows

This directory contains automated workflows for the Aisher project.

## Workflows

### 1. CI - Tests and Coverage (`ci.yml`)

**Triggers:**
- Push to `main` or `master` branch
- Pull requests to `main` or `master` branch

**What it does:**
- ✅ Runs on Python 3.10, 3.11, and 3.12
- ✅ Installs dependencies using `uv` package manager
- ✅ Runs linting with `ruff`
- ✅ Checks code formatting with `black`
- ✅ Executes pytest with coverage reporting
- ✅ Uploads coverage to Codecov
- ✅ Generates HTML coverage reports as artifacts
- ✅ Posts coverage summary as PR comment

**Artifacts:**
- Coverage HTML reports (30-day retention)
- Coverage XML for Codecov integration

### 2. Claude Code Review (`claude-review.yml`)

**Triggers:**
- Pull requests (opened, synchronized, reopened)
- Only for Python files (`src/**/*.py`, `tests/**/*.py`)

**What it does:**
- 🤖 Uses official Claude Code GitHub Action
- 🔍 Comprehensive code review covering:
  - **Security** - SQL injection, secrets exposure, input validation
  - **Code Quality** - Pydantic v2, type hints, error handling, async patterns
  - **Performance** - Query optimization, async efficiency, resource management
  - **Testing** - Coverage, edge cases, mocking patterns
  - **Documentation** - Docstrings, type hints, inline comments
- 📋 Validates compliance with CLAUDE.md project standards
- 💬 Posts review comments directly on pull requests via `gh` CLI

**Review features:**
- Leverages full Claude Code capabilities with repository context
- Uses GitHub CLI (`gh`) for PR operations
- Follows project-specific conventions from CLAUDE.md
- Provides actionable, constructive feedback

## Setup Instructions

### Step 1: Install Claude Code GitHub App

**IMPORTANT:** Claude Code Review requires the Claude Code GitHub App to be installed.

#### Option A: Direct Installation Link
1. Visit: **https://github.com/apps/claude-code/installations/new**
2. Select the repository (jawsbaek/Aisher)
3. Click "Install"

#### Option B: Using the CLI Command
If you have Claude Code CLI installed locally, run:
```bash
/install-github-app
```

This will open the GitHub App installation page in your browser.

### Step 2: Generate OAuth Token

After installing the GitHub App:

1. Go to: **https://claude.ai/settings/github**
2. Click "Generate OAuth Token"
3. Copy the generated token (starts with `cct_...`)

### Step 3: Add Repository Secret

Configure the OAuth token in your GitHub repository:

1. Go to repository **Settings > Secrets and variables > Actions**
2. Click "New repository secret"
3. Name: `CLAUDE_CODE_OAUTH_TOKEN`
4. Value: Paste your OAuth token from Step 2
5. Click "Add secret"

### Step 4: (Optional) Configure Codecov

For coverage reporting integration:

1. Sign up at [codecov.io](https://codecov.io/)
2. Connect your GitHub repository
3. Copy the repository token
4. Add it as `CODECOV_TOKEN` secret in GitHub (Settings > Secrets and variables > Actions)

### Repository Permissions

The workflows require these permissions (already configured):

**CI Workflow (`ci.yml`):**
- `contents: read` - Read repository code
- `pull-requests: write` - Post coverage comments

**Claude Review Workflow (`claude-review.yml`):**
- `contents: read` - Read repository code
- `pull-requests: write` - Post review comments
- `issues: write` - Optional issue operations
- `id-token: write` - OIDC authentication

Ensure these are enabled in **Settings > Actions > General > Workflow permissions**:
- ✅ Read and write permissions
- ✅ Allow GitHub Actions to create and approve pull requests

## Local Testing

Test your code locally before pushing:

```bash
# Install dependencies
uv sync --dev

# Run linting
uv run ruff check src/ tests/

# Run formatting check
uv run black --check src/ tests/

# Run tests with coverage
uv run pytest -v --cov=aisher --cov-report=term-missing --cov-report=html

# View coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

## Workflow Badges

Add these badges to your README.md:

```markdown
[![CI](https://github.com/jawsbaek/Aisher/actions/workflows/ci.yml/badge.svg)](https://github.com/jawsbaek/Aisher/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jawsbaek/Aisher/branch/main/graph/badge.svg)](https://codecov.io/gh/jawsbaek/Aisher)
[![Claude Code Review](https://github.com/jawsbaek/Aisher/actions/workflows/claude-review.yml/badge.svg)](https://github.com/jawsbaek/Aisher/actions/workflows/claude-review.yml)
```

## Customization

### Adjust Python versions

Edit `ci.yml` matrix:
```yaml
strategy:
  matrix:
    python-version: ["3.10", "3.11", "3.12"]  # Modify as needed
```

### Change coverage thresholds

Edit `ci.yml`:
```yaml
- name: Comment coverage on PR
  with:
    MINIMUM_GREEN: 80   # Change thresholds
    MINIMUM_ORANGE: 60
```

### Customize Claude review focus

Edit `claude-review.yml` prompt section to adjust:
- Review criteria and priorities
- Project-specific standards
- Feedback format and style

### Filter by PR author

Uncomment the `if` condition in `claude-review.yml` to only review PRs from specific users:
```yaml
if: |
  github.event.pull_request.user.login == 'external-contributor' ||
  github.event.pull_request.author_association == 'FIRST_TIME_CONTRIBUTOR'
```

### Modify allowed tools for Claude

Edit the `claude_args` in `claude-review.yml` to restrict or expand tool access:
```yaml
claude_args: '--allowed-tools "Bash(gh pr view:*),Bash(gh pr diff:*),Bash(gh pr comment:*)"'
```

See [Claude Code CLI Reference](https://docs.claude.com/docs/claude-code/cli-reference) for more options.

## Troubleshooting

### Claude review doesn't run
- **Check GitHub App installation**: Visit https://github.com/apps/claude-code
  - Ensure the app is installed for your repository
  - Verify repository access permissions
- **Verify OAuth token**: Check `CLAUDE_CODE_OAUTH_TOKEN` secret is set correctly
  - Token should start with `cct_`
  - Generate a new token at https://claude.ai/settings/github if expired
- **Check workflow permissions**: Ensure "Read and write permissions" are enabled in Settings > Actions > General

### Claude review fails with authentication error
- OAuth token may have expired - generate a new one at https://claude.ai/settings/github
- Ensure the GitHub App installation hasn't been revoked
- Check the workflow run logs for specific error messages

### CI workflow fails with "uv: command not found"
- Ensure `astral-sh/setup-uv@v4` action is present in `ci.yml`
- Check uv installation step runs successfully in workflow logs

### Coverage not uploading to Codecov
- Verify `CODECOV_TOKEN` secret is set
- Check that `coverage.xml` file is generated (review CI logs)
- Ensure repository is properly connected at codecov.io

### "Resource not accessible by integration" error
1. Go to repository **Settings > Actions > General**
2. Under "Workflow permissions", select **"Read and write permissions"**
3. Check **"Allow GitHub Actions to create and approve pull requests"**
4. Save changes and re-run the workflow

### Claude review doesn't comment on PR
- Check that Python files were modified (`.py` files in `src/` or `tests/`)
- Verify the PR is not from a fork (GitHub Actions have limited permissions for forks)
- Review workflow logs for any errors in the Claude Code action step
- Ensure `gh` CLI commands have proper permissions

## Cost Considerations

### Claude Code Review
- **Free tier**: Claude Code offers a free tier for open-source projects
- **Paid usage**: Billed through your Claude.ai account
- Review frequency: Only runs on PR creation/updates with Python file changes
- Typical cost: ~$0.01-0.05 per review depending on PR size
- Cost control: Use the `paths` filter to limit when reviews run

### GitHub Actions Minutes
- **Public repositories**: Unlimited minutes (free)
- **Private repositories**: 2,000 minutes/month on free tier
- CI workflow: ~3-5 minutes per run × 3 Python versions = ~15 minutes per push
- Claude review: ~1-3 minutes per PR
- Should stay within free tier for small-to-medium projects

### Codecov
- **Open source**: Free unlimited
- **Private repositories**: Free for up to 5 users

## Advanced Configuration

### Only review from specific contributors

Uncomment and customize in `claude-review.yml`:
```yaml
if: |
  github.event.pull_request.author_association == 'FIRST_TIME_CONTRIBUTOR' ||
  github.event.pull_request.user.login == 'external-contributor'
```

### Custom file patterns

Modify the `paths` filter in `claude-review.yml`:
```yaml
paths:
  - "src/**/*.py"
  - "tests/**/*.py"
  - "pyproject.toml"
  - "CLAUDE.md"
```

### Integration with other tools

The Claude Code action can be combined with other GitHub Actions:
- Code scanning tools (Snyk, SonarCloud)
- Dependency updates (Dependabot)
- Deployment pipelines
- Notification systems (Slack, Discord)

## References

- [Claude Code Documentation](https://docs.claude.com/docs/claude-code)
- [Claude Code GitHub Action](https://github.com/anthropics/claude-code-action)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [uv Package Manager](https://github.com/astral-sh/uv)
- [Codecov Documentation](https://docs.codecov.com/)
- [pytest Coverage](https://pytest-cov.readthedocs.io/)

## Support

For issues or questions:
- Claude Code issues: https://github.com/anthropics/claude-code-action/issues
- GitHub Actions: https://github.com/jawsbaek/Aisher/actions
- Aisher project: https://github.com/jawsbaek/Aisher/issues
