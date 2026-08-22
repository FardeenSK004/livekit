# Documentation Agent

## Guidelines for updating this vault

This is the **source of truth** for the project. Every code change must be reflected here.

### When to update

| Code change | Vault update required |
|-------------|----------------------|
| Architecture changes | Update `Architecture/Overview.md` + `Architecture/Design Decisions.md` |
| New feature | Update `Features/Feature Index.md` + create feature page |
| Modified feature | Update relevant feature page + `Home.md` stats |
| Bug fix | Update `Development/Bugs.md` |
| Work completed | Update `Development/Changelog.md` + `Development/Current Sprint.md` |
| New conventions | Update `Knowledge/Conventions.md` |
| New env vars | Update `Knowledge/Environment.md` |
| Line count changes | Update `Context/Repository Map.md` + `Home.md` |

### Conventions

- Use `[[WikiLink]]` format for internal links
- Use `` `code` `` for file paths, class names, variables
- Use `file:line` format for source references (e.g. `agent.py:279-378`)
- Keep the Feature Index table up to date with all features
- After `git pull` or `git merge`, check for stale docs and update
