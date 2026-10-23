# Runner GitHub account and repository selection

The GitHub Control Center uses the existing Research OS API. It selects credentials and repositories for the read-only GitHub dashboard; it does not dispatch workflows or grant execution/release authority.

Set server-side `RESEARCH_OS_GITHUB_ACCOUNTS_JSON` to a JSON array with a stable unique ID, display label, and token for each account:

```json
[
  {"id":"primary","label":"Primary GitHub account","token":"<secret configured outside source control>"},
  {"id":"legacy","label":"Legacy GitHub account","token":"<secret configured outside source control>"}
]
```

Never put real tokens in source, commits, screenshots, logs, or this document. Configure secrets in the service environment and restart the API. If absent, legacy `RESEARCH_OS_GITHUB_TOKEN` or `GITHUB_TOKEN` remains supported as a single account named `default`.

Account identities are resolved from GitHub's `/user` endpoint. Repository options use the selected credential; tokens are never returned. Listing is read-only and paginated. The Universal Runner lifecycle and Unified Final Gate remain unchanged.
