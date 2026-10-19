# GitHub setup and releases

## One-time setup

1. Use the public `hackroid/camera2-crop-fix` repository and default branch `main`.
2. Under **Settings → Actions → General**, allow GitHub Actions. If an organization restricts third-party actions, allow `actions/checkout` and `actions/upload-artifact`.
3. Keep default workflow permissions read-only. The release job alone requests `contents: write`; a personal access token or repository secret is not required.
4. Protect `main` with an active ruleset requiring PRs, the GitHub Actions `verify` and `conventions` checks, an up-to-date branch, resolved review threads and linear history. Block force pushes and deletion; configure no bypass actors. The current sole-maintainer setup requires zero approvals.
5. Allow squash merging only, use `PR_TITLE` for the squash title and `BLANK` for its message body, and enable automatic topic-branch deletion. The required `conventions` check validates PR titles and every proposed commit header. See [CONTRIBUTING.md](../.github/CONTRIBUTING.md) for title and branch conventions.

Fork PRs run with a read-only token. A first-time contributor may require an Actions approval in GitHub; do not use `pull_request_target` to execute contributor code.

## Cost

This configuration uses standard GitHub-hosted Ubuntu runners in a public repository; their compute usage is free. It does not need a paid runner or third-party build service. Temporary CI artifacts are small and retained for three days; account storage/billing policies still apply.

References: [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [workflow security](https://docs.github.com/en/actions/reference/security/secure-use).

## Publish a pre-release

1. Update `version` and the monotonically increasing `versionCode` in `module/module.prop`; update `doc/release-notes.md`. Keep new device support gated by exact identities.
2. Open/review/merge the changes. CI runs tests, builds the module and uploads a temporary artifact.
3. Tag the reviewed commit already merged into `main` with the exact module version, prefixed by `v`:

   ```sh
   git tag v0.4.0-beta.1
   git push origin v0.4.0-beta.1
   ```

4. The release workflow checks tag/version agreement and requires the tagged commit to belong to `main` history, runs tests, builds the ZIP and creates a **draft** release with its assets. Versions containing `-` are marked pre-release.
5. Download and test that exact draft ZIP on the supported device. Review its checksums and release notes, then publish the draft in GitHub's Releases UI.

A workflow failure publishes nothing automatically. It does not force-push tags or overwrite an existing release. Source code stays the current implementation; build products, private images and previous test results are ignored.

## Stable automatic updates

Pre-release modules intentionally omit `updateJson`: beta users install ZIPs manually. Stable versions receive:

```text
https://github.com/hackroid/camera2-crop-fix/releases/latest/download/update.json
```

The workflow uploads the matching JSON and changelog with every release. GitHub's `latest` download route follows stable releases, not pre-releases. Beta users must manually install the first stable version to start following that update channel. Publishing a draft is the final step that makes a stable release and its update metadata public.

The stable channel uses GitHub Releases directly; Pages, a custom server and a separate update branch are unnecessary. See [Magisk's module update format](https://topjohnwu.github.io/Magisk/guides.html#moduleprop).
