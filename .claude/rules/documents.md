---
paths:
  - "**/*.md"
  - "docs/**"
  - ".claude/agents/**"
  - ".claude/rules/**"
  - ".claude/skills/**"
  - ".github/*.md"
---

# Documents and agent guidance

## Present tense

- **Documents describe the present.** They keep the reasons behind a choice and drop its history. How a decision came
  about lives in `.pm/`, whose notes are history by design and follow none of these rules.
- **What is not built says so.** A built component is described in the present tense, with no label. A planned one is
  labeled "(planned)".
- **An unsettled choice is a hypothesis,** written "(hypothesis: …)" with the test or the measurement that will settle
  it.

## Where a statement lives

Each statement has one home, so that it never drifts from a copy.

- **A rule about what the repository holds,** its code, tests, configuration and documents, lives in `.claude/rules/`,
  once and in full, in the file of its concern.
- **Session conduct** lives in `CLAUDE.md`: what a session reads first, its workflow, the commands, the language of the
  repository, and one index line per rules file. Every session loads all of `CLAUDE.md`, so it stays under 200 lines.
- **The design and its reasons** live in `docs/foundations.md`. It may say what a rule protects and why, but it does not
  restate the rule.
- **A procedure** lives in a skill, under `.claude/skills/`.
- **What a part of the system does and how,** for people and agents, lives in the references of `docs/`: the components,
  the data flow and the library's layout in `ARCHITECTURE.md`, the HTTP API in `API.md`, the sandbox protocol in
  `OCR_SANDBOX.md`, the threat model and the guarantees in `SECURITY.md`. They describe; the rules they follow from live
  in `.claude/rules/`.
- **Setup, usage and scripts for people** live in `README.md` (the api's own in `server/README.md`), and the credits in
  `CREDITS.md`.

## References

- **A reference names a file, and one of its headings when it points at a part:** `docs/foundations.md` > Layers and
  modules. Inside a document, it links the heading instead: `[References](#references)`. When a short section holds
  several rules, the reference adds the rule's bold name, in quotes: `CLAUDE.md` > Workflow, "A commit message says
  why".
- **Never a number:** no section, rule or step number of a document of this repository. A number says nothing about its
  target, and it shifts when something is inserted before it. An outside standard is cited as its authors number it,
  such as RFC 5545, section 3.8.5.3.
- **Every cited file and heading exists.** A change that renames or removes a heading updates every reference to it, in
  the documents, the agent guidance and the messages of the tools.

## Rules files

- **One file per concern.** A concern that spans several directories stays in one file. A `CLAUDE.md` per directory
  would scatter such a rule, or duplicate it.
- **A rules file is self-contained.** It states each rule in full, with enough of its reason to apply it, and never
  sends its reader to another document for a rule.
- **`paths` decide when a file loads.** Claude Code loads a file with `paths` when a session reads or edits a matching
  file, and a file without `paths` in every session and every subagent. Only what every session needs goes in a file
  without `paths`, kept short.
- **`paths` are kept by hand, per concern,** and so are the scopes of the expert reviewers that derive from them.
- **Each rules file has its line in `CLAUDE.md`,** which names its topics and when to read it, without restating its
  rules. A subagent in another worktree, or a compacted session, can miss a load by `paths`: the line tells it to read
  the file.

## Skills

- **A skill holds one procedure,** in `.claude/skills/<name>/SKILL.md`, and its `description` says when to use it.
- **It cites the rules it applies** by file and heading, and does not restate them.
