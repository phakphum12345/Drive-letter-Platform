# Security Policy

## Reporting a vulnerability

Do not publish credentials, exploit instructions, or sensitive evidence
in public issues. Report security concerns privately to the repository
maintainer using an authorized private channel.

## Security requirements

- Keep credentials in environment variables or an approved secret store.
- Never commit .env files, private keys, access tokens, or production secrets.
- Validate authorization and security-sensitive operations on the server.
- Fail closed when authentication, authorization, or validation fails.
- Do not bypass device locks, access controls, MDM, or authorization.
- Review workflows and permissions before enabling CI or deployment.
- Do not expose secrets in logs, API responses, test output, or artifacts.
