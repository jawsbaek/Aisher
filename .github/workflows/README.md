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

**What it does:**
- 🤖 Reviews Python code changes using Claude Sonnet 4.5
- 🔍 Checks for:
  - Security vulnerabilities
  - Code quality issues
  - Performance concerns
  - Missing test coverage
  - Documentation gaps
- 📋 Validates compliance with project standards (CLAUDE.md)
- 💬 Posts review comments on pull requests

**Two-stage review:**
1. **General Code Review** - Security, quality, performance, testing, docs
2. **Standards Check** - Compliance with CLAUDE.md conventions

## Setup Instructions

### Required Secrets

Configure these secrets in your GitHub repository settings (`Settings > Secrets and variables > Actions`):

#### Optional (for Codecov integration):
```
CODECOV_TOKEN=<your-codecov-token>
```
Get this from [codecov.io](https://codecov.io/) after connecting your repository.

#### Required (for Claude code review):
```
ANTHROPIC_API_KEY=<your-anthropic-api-key>
```
Get this from [Anthropic Console](https://console.anthropic.com/).

**Note:** If `ANTHROPIC_API_KEY` is not set, the Claude review workflow will skip gracefully.

### Repository Permissions

The Claude review workflow needs:
- ✅ `contents: read` - To read code
- ✅ `pull-requests: write` - To post comments

These are configured in the workflow file.

## Coverage Reporting

### Codecov (Optional)

1. Sign up at [codecov.io](https://codecov.io/)
2. Connect your GitHub repository
3. Copy the repository token
4. Add it as `CODECOV_TOKEN` secret in GitHub
5. Coverage will be uploaded automatically on each CI run

### PR Coverage Comments

The `python-coverage-comment-action` automatically posts coverage summaries on pull requests:
- 🟢 Green: ≥80% coverage
- 🟠 Orange: 60-79% coverage
- 🔴 Red: <60% coverage

## Local Testing

Test your workflows locally before pushing:

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

### Modify Claude review prompts

Edit `claude-review.yml` to customize the review criteria and focus areas in the API call body.

## Troubleshooting

### CI workflow fails with "uv: command not found"
- Ensure `astral-sh/setup-uv@v4` action is present
- Check uv installation step runs successfully

### Claude review doesn't post comments
- Verify `ANTHROPIC_API_KEY` secret is set correctly
- Check workflow has `pull-requests: write` permission
- Ensure PR contains Python file changes (`.py` files)

### Coverage not uploading to Codecov
- Verify `CODECOV_TOKEN` secret is set
- Check coverage.xml file is generated
- Review Codecov action logs for errors

### "Resource not accessible by integration" error
- Go to repository `Settings > Actions > General`
- Under "Workflow permissions", select "Read and write permissions"
- Check "Allow GitHub Actions to create and approve pull requests"

## Cost Considerations

### Claude API Usage
- Each PR review makes 2 API calls (general review + standards check)
- Claude Sonnet 4.5 pricing: ~$3 per million input tokens, ~$15 per million output tokens
- Typical review: ~2K input tokens + 1K output tokens = ~$0.02 per review
- Estimated cost: $1-2/month for active repositories

### GitHub Actions Minutes
- Free tier: 2,000 minutes/month for public repos
- CI workflow: ~3-5 minutes per run × 3 Python versions = ~15 minutes per push
- Claude review: ~1-2 minutes per PR
- Should stay within free tier for small-to-medium projects

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [uv Package Manager](https://github.com/astral-sh/uv)
- [Anthropic Claude API](https://docs.anthropic.com/)
- [Codecov Documentation](https://docs.codecov.com/)
- [pytest Coverage](https://pytest-cov.readthedocs.io/)
