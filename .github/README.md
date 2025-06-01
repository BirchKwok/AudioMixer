# GitHub Actions Workflows

This directory contains GitHub Actions workflows for continuous integration and deployment of the AudioMixer project.

## Workflows Overview

### 1. `test.yml` - Quick Tests
**Triggers:** Push to main/develop, Pull Requests
- Runs basic tests on Python 3.8 and 3.11
- Fast feedback for development
- Tests imports and core functionality

### 2. `ci-cd.yml` - Comprehensive CI/CD Pipeline
**Triggers:** Push to main/develop, Pull Requests, Releases
- **Multi-platform testing:** Ubuntu, Windows, macOS
- **Multi-version testing:** Python 3.8-3.12
- **Code quality checks:** flake8, mypy, safety, bandit
- **Security scanning:** Dependencies and code analysis
- **Package building and validation**
- **Automatic publishing to Test PyPI (main branch)**
- **Automatic publishing to PyPI (releases)**

### 3. `release.yml` - Release Management
**Triggers:** Version tags (v*.*.*), Manual dispatch
- Pre-release testing
- Build and publish to PyPI
- Create GitHub releases with auto-generated notes
- Verify PyPI installation
- Support for manual releases via GitHub UI

## Setup Instructions

### 1. Repository Secrets

Set up the following secrets in your GitHub repository (`Settings > Secrets and variables > Actions`):

#### Required for PyPI Publishing:
- `PYPI_API_TOKEN` - Your PyPI API token
- `TEST_PYPI_API_TOKEN` - Your Test PyPI API token

#### Optional for enhanced features:
- `CODECOV_TOKEN` - For code coverage reporting

### 2. PyPI API Tokens

1. **Create PyPI Account:**
   - Register at https://pypi.org/
   - Register at https://test.pypi.org/

2. **Generate API Tokens:**
   ```bash
   # Go to Account Settings > API tokens
   # Create a token for the audiomixer project
   ```

3. **Add tokens to GitHub Secrets:**
   - `PYPI_API_TOKEN`: Your production PyPI token
   - `TEST_PYPI_API_TOKEN`: Your test PyPI token

### 3. Environment Setup (Optional)

For additional security, create environments in your repository:
- `test-pypi` - For Test PyPI publishing
- `pypi-release` - For production PyPI publishing

## Usage

### Development Workflow

1. **Create feature branch:**
   ```bash
   git checkout -b feature/new-feature
   ```

2. **Make changes and push:**
   ```bash
   git add .
   git commit -m "feat: add new feature"
   git push origin feature/new-feature
   ```

3. **Create Pull Request:**
   - The `test.yml` workflow will run automatically
   - All tests must pass before merging

### Release Workflow

#### Option 1: Tag-based Release (Recommended)
```bash
# Update version in pyproject.toml
# Commit changes
git add pyproject.toml
git commit -m "bump: version to 1.0.1"

# Create and push tag
git tag v1.0.1
git push origin v1.0.1
```

#### Option 2: Manual Release
1. Go to GitHub Actions tab
2. Select "Release to PyPI" workflow
3. Click "Run workflow"
4. Enter version number
5. Click "Run workflow"

### Monitoring Releases

1. **Check workflow status** in GitHub Actions tab
2. **Verify Test PyPI** at https://test.pypi.org/project/audiomixer/
3. **Verify PyPI** at https://pypi.org/project/audiomixer/
4. **Test installation:**
   ```bash
   pip install audiomixer==1.0.1
   ```

## Workflow Features

### Security
- ✅ Dependency vulnerability scanning
- ✅ Code security analysis with bandit
- ✅ Package integrity verification
- ✅ Environment-based deployment protection

### Quality Assurance
- ✅ Multi-platform testing
- ✅ Multi-version Python support
- ✅ Code style checking (flake8)
- ✅ Type checking (mypy)
- ✅ Test coverage reporting
- ✅ Package installation testing

### Automation
- ✅ Automatic Test PyPI publishing on main branch
- ✅ Automatic PyPI publishing on release
- ✅ GitHub release creation with notes
- ✅ Build artifact preservation
- ✅ Post-release verification

## Troubleshooting

### Common Issues

1. **Test failures on audio-related code:**
   - Some CI environments don't have audio devices
   - Tests should be designed to handle headless environments

2. **PyPI publishing fails:**
   - Check API token validity
   - Ensure version number is incremented
   - Verify package name availability

3. **Build failures:**
   - Check system dependencies installation
   - Verify Python version compatibility
   - Review error logs in Actions tab

### Getting Help

- Check the Actions tab for detailed logs
- Review failed steps and error messages
- Ensure all required secrets are configured
- Verify environment setup if using protected environments 