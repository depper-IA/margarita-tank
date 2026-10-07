---
name: releasing
description: Cuts a new versioned release of the Margarita Tank desktop apps (macOS DMG + Windows installer). Use when the user asks to release, cut a release, publish a release, ship a version, or bump the version. The release is fully automated by a GitHub Actions workflow that triggers on a vX.Y.Z tag push — do NOT build or zip the app manually.
---

# Releasing Margarita Tank

The release is **fully automated by CI**. `.github/workflows/release.yml`
triggers on any `v*` tag push and builds, in parallel:

- macOS: static simulator → py2app → simulator bundled into
  `Margarita Tank.app` → `Margarita-Tank.dmg`
- Windows: static simulator → PyInstaller (`host/windows/margarita_tank.spec`)
  → Inno Setup (`host/windows/installer.iss`) → `Margarita-Tank-Setup.exe`

then creates the GitHub release with both assets attached. Asset names are
unversioned on purpose: the README links to
`https://github.com/depper-IA/margarita-tank/releases/latest/download/<asset>`.
Publishing a release from the GitHub UI runs the same workflow and attaches the
assets to it.

**The only manual steps are: merge to main, tag `vX.Y.Z`, push the tag.**

## Critical: do NOT build or zip manually

`host/build.sh`, PyInstaller/ISCC and `ditto`/`zip` are for **local installs only**. Running them
to produce a release artifact is wasted work — the workflow rebuilds everything
on the runner. Pushing the tag is the entire release trigger.

## How versioning works

There is **no hardcoded version string to edit**. `host/setup.py`'s
`_bake_version()` runs `git describe --tags --exact-match HEAD` at build time:

- HEAD on a clean `vX.Y.Z` tag → baked version is `vX.Y.Z`.
- Otherwise → `<branch>+<N>@<sha>[-dirty]`.

The Windows spec bakes it the same way. `host/clawd_tank_menubar/version.py` only *reads* this (`_version_info.py` is
generated and gitignored). So **"bump the version" = create the git tag.**

Tags are semver `vX.Y.Z`, published as GitHub releases. Decide patch vs minor by
what landed since the last tag — bugfixes only → patch; new user-facing features
→ minor. Confirm the number with the user if unsure:

```bash
git log "$(git describe --tags --abbrev=0)"..main --oneline
```

## Release workflow

```
- [ ] 1. Merge the PR to main (merge commit — matches repo convention)
- [ ] 2. Sync local main
- [ ] 3. Confirm the version number (patch vs minor)
- [ ] 4. Verify the tree is clean (so the baked version isn't "-dirty")
- [ ] 5. Tag vX.Y.Z on main HEAD and push the tag (this triggers CI)
- [ ] 6. Watch the Release workflow finish
- [ ] 7. Edit the release to add a title + notes (CI leaves them blank)
- [ ] 8. Verify the release + asset
```

**1–2. Merge and sync** (the repo uses merge commits, not squash):
```bash
gh pr merge <N> --merge --delete-branch
git checkout main && git pull --ff-only
```

**4. Clean-tree check.** `_version_info.py`, `host/dist/`, `host/build/`, and
`simulator/build-static/` are gitignored, so they don't dirty the tree:
```bash
git status --porcelain   # must print nothing
```

**5. Tag and push** — pushing the tag is what triggers the release:
```bash
git tag -a vX.Y.Z -m "Margarita Tank vX.Y.Z — <one-line summary>"
git push origin vX.Y.Z
```

**6. Watch CI** (~5–10 min; the Windows job is the slow one):
```bash
gh run watch "$(gh run list --workflow=release.yml --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status
```

**7. Add release notes.** The workflow creates the release with a bare `vX.Y.Z`
title and an empty body. Give it a real title and notes, and include a changelog
compare link:
```bash
gh release edit vX.Y.Z \
  --title "vX.Y.Z — <theme>" \
  --notes "## Highlights
...
**Full changelog:** https://github.com/depper-IA/margarita-tank/compare/<prevtag>...vX.Y.Z"
```

**8. Verify:**
```bash
gh release view vX.Y.Z --json tagName,isDraft,assets
# expect: isDraft false, assets Margarita-Tank.dmg and Margarita-Tank-Setup.exe present
```

## Optional: update your own machine

To run the released build locally (not part of publishing):
```bash
cd host && ./build.sh --install   # rebuilds at the tag, bakes the clean version, copies to /Applications
```
Then kill and relaunch the app so it picks up the new bundle.
