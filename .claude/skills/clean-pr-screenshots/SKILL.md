---
name: clean-pr-screenshots
description: Deletes the pr-screenshots branch of ScanMyLib's origin, where the pull-request skill publishes the screenshots of pull requests, after listing the open pull requests whose pictures the deletion would break. Use when the maintainer wants to clean up or prune the published screenshots, or when a publication warned that the branch is heavy.
disable-model-invocation: true
---

# Clean the screenshots of pull requests

The pull-request skill publishes the screenshots of pull requests on the `pr-screenshots` branch of origin
(`.claude/skills/pull-request/SKILL.md` > Show a visible change), which grows with each publication. The cleanup
deletes the whole branch: the pictures that descriptions link then break once GitHub drops their commits, so it first
says which open pull requests still link one, and deletes only on the user's word.

1. From any checkout of the repository, with `gh` logged in, run `${CLAUDE_SKILL_DIR}/scripts/clean_screenshots.py`. It
   deletes nothing: it says whether the branch exists, and lists the open pull requests whose description links one of
   its pictures.
2. Show the user what it printed, and ask whether to delete the branch: an open pull request in the list loses its
   pictures, which its author can publish again afterwards.
3. Only on the user's yes, run `${CLAUDE_SKILL_DIR}/scripts/clean_screenshots.py --delete`, and report what it printed.
