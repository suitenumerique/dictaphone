# Agent instructions

Read [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

## Git conventions

```text
<gitmoji>(scope) lowercase title

Mandatory description explaining why.
```

- No space between the emoji and `(`; one space after `)`.
- Use component scopes such as `backend`, `frontend`, `mobile`, `audio-extractor`,
  `ci`, `docker`, `dev`, or `chart`. Join multiple scopes with `/`.
- Sign commits (`-S`) and include a sign-off (`--signoff`).
- Keep each commit focused on one concern, including its tests and documentation.

## Changelog requests

- Group entries into sections such as Added, Fixed, and Maintenance.
- Write each entry as `<gitmoji>(scope) lowercase summary`, using the component
  scopes and spacing from the git conventions above.
- Summarize related commits into concise, user-facing entries rather than
  reproducing the commit log. Preserve important upgrade notes separately.
- When given a starting commit, cover changes after that commit through HEAD
  unless another endpoint is specified, and state the range or release versions.
- Provide the changelog in the response unless asked to update a file.
