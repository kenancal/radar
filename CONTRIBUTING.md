# Contributing to RADAR

Thank you for your interest in contributing to RADAR.

RADAR is an open-source, automated technology, startup, artificial intelligence, and investment intelligence workflow. Contributions that improve its reliability, configurability, documentation, regional adaptability, and maintainability are welcome.

## Ways to contribute

You can contribute by:

* reporting bugs;
* proposing new RSS sources;
* improving feed parsing and duplicate detection;
* adding tests;
* improving documentation;
* improving HTML and email rendering;
* adding localization or regional evaluation profiles;
* improving LLM output validation and fallback behavior;
* reviewing security, privacy, and GitHub Actions configuration;
* fixing compatibility problems caused by external feeds or model providers.

## Before starting

For significant changes, please open an issue first and describe:

* the problem you want to solve;
* the proposed approach;
* any compatibility or security implications;
* whether the change affects existing configuration.

Small documentation fixes and clearly scoped bug fixes may be submitted directly as pull requests.

## Development setup

Clone the repository and install the dependencies:

```bash
git clone https://github.com/kenancal/radar.git
cd radar
pip install -r requirements.txt
```

Copy the example environment file:

```bash
cp .env.example .env
```

Add only the credentials required for your local test environment.

Never commit API keys, email passwords, access tokens, private email addresses, or other secrets.

Run RADAR locally with:

```bash
python radar.py
```

The command may generate or update:

* `archive/`
* `index.html`

Review generated files before including them in a pull request.

## Pull request guidelines

Please keep pull requests focused on one problem or feature.

A pull request should include:

* a clear explanation of the problem;
* a summary of the proposed solution;
* relevant test or verification steps;
* documentation updates when behavior or configuration changes;
* screenshots when the generated HTML interface changes.

Avoid unrelated formatting changes or large refactors inside narrowly scoped pull requests.

## Code quality

Contributions should:

* preserve existing functionality unless a breaking change has been discussed;
* handle malformed or unavailable feeds gracefully;
* validate external and LLM-generated data;
* avoid unnecessary dependencies;
* keep provider-specific logic isolated where possible;
* avoid embedding personal credentials or environment-specific values;
* remain understandable for contributors with limited project context.

## RSS sources

New sources should be:

* relevant to technology, startups, artificial intelligence, investment, or entrepreneurship;
* accessible through a stable feed;
* properly attributed;
* unlikely to produce excessive duplicate or low-quality entries.

Please explain why the source is useful when proposing it.

## AI-generated contributions

AI-assisted contributions are allowed, but contributors remain responsible for reviewing and testing the submitted code.

Do not submit unreviewed generated code, fabricated test results, or changes whose behavior you cannot explain.

## Security issues

Do not publish sensitive security vulnerabilities, exposed credentials, or exploitable configuration details in a public issue.

For non-sensitive bugs, use the GitHub issue tracker.

## License

By contributing to RADAR, you agree that your contributions will be licensed under the MIT License used by the project.
