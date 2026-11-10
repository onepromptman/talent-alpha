# Security

Please report a security problem privately, not in a public issue.

1. Open the repository's **Security** tab and choose **Report a vulnerability**. GitHub
   keeps the report private between you and the maintainers.
2. Say what you found, how to reproduce it, and what it could expose. Use made-up data:
   never paste real candidate or employee details into a report.
3. If that button is missing, open an issue that says only "security contact, please"
   and a maintainer will reach out privately.

You can expect a first reply within seven days.

## What counts

- A way to make a kit send, post or write to another system without a person approving
  it first.
- An n8n workflow or webhook that accepts a request without its credential.
- Untrusted content that injects scripts or remote resources into a rendered document.
  The shipped template contains its own chart script and uses local system fonts.
  Opening a card does not load remote fonts or scripts. Source links open when clicked.
- A secret, an API key or personal data committed to a repository.

## Where fixes land

Fixes for this standalone edition land in this repository. Only the latest version
on `main` is supported.
