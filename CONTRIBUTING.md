# Contributing

## Required workflow

1. Read the relevant documentation and existing implementation.
2. Analyze the change and its security impact.
3. Make the smallest necessary change.
4. Run relevant tests and validation.
5. Review the complete diff and audit the result.
6. Submit changes through a pull request for review.

## Repository safety

- Do not commit credentials, private keys, or personal data.
- Do not rewrite shared Git history or force-push over existing work.
- Do not enable inherited workflows without reviewing their permissions,
  triggers, secrets, runners, and deployment effects.
- Do not claim tests passed unless their results are available.
- Document new configuration using placeholders, never real secrets.
