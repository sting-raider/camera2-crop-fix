# Development workflow

Please fork and PR if you want to contribute.

Use GitHub Flow: branch from `main`, make a focused change, open a pull request,
and delete the topic branch after squash merging. There is no `develop` branch.
Use short branch names such as `fix/crop-rounding` or `docs/install`.
Update a topic branch by rebasing onto `origin/main`; start a new branch after
each squash merge.

## Titles and commits

PR titles must use this format, with a scope:

```text
type(scope): subject
```

Examples:

```text
fix(native): preserve crop geometry at 10x
feat(module): support a newly verified firmware profile
ci(release): validate release metadata
```

Every ordinary commit must follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).
Its scope is optional: `fix: correct rounding` is also valid. Allowed types are
`build`, `chore`, `ci`, `docs`, `feat`, `fix`, `perf`, `refactor`, `revert`,
`style` and `test`. Scopes use lowercase letters, digits and hyphens, starting
with a letter. Use `!` before `:` for a breaking change. Keep headers within
100 characters, with no trailing whitespace.

CI checks the current PR title and every commit proposed by the PR. Title edits
rerun the convention check. Existing commits on `main` are outside that range.

## Merge policy

`main` requires a PR, passing `verify` and `conventions` checks, an up-to-date
branch and resolved review conversations. Direct pushes, force pushes and
deletion are blocked, with no configured bypass actors.

Only **Squash and merge** is enabled. Keep the squash subject equal to the PR
title; the default message body is blank. One merged PR produces one commit
on `main`, and GitHub deletes its topic branch afterward. Required approvals
are currently zero so a sole maintainer can merge their own PR after checks.

## Validation

Run `python3 tools/test.py` and build the module as described in
[building.md](../doc/building.md). Device support changes need validation on
the exact target firmware. Do not remove compatibility checks to make an
unsupported build install. Follow [releasing.md](../doc/releasing.md) for
tags, draft releases and device validation of release artifacts.
