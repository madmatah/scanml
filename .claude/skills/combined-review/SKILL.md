---
name: combined-review
description: Reviews a diff of ScanMyLib before it reaches main, the current branch by default, or a pull request, a branch or a commit range, with the project's expert reviewers, against its plan when given one, and returns one verified report with severities, for less than one agent per expert, by giving the experts to two agents, one on Sonnet for those that check written rules or the plan and one on Opus for those that judge. Use before pushing a branch or opening a pull request, or when the user asks for a review, a combined review or a second opinion on a diff of the project's own work; someone else's pull request goes to expert-review. Free text after the target is a focus passed to every expert. It changes no code.
argument-hint: "[<pr#>|<branch>|<range>] [--plan <file>] [--mock <file>] [--fixes <file>] [--post] [focus]"
context: fork
model: opus
effort: high
---

# Combined review

This review follows the procedure of the expert review, with its experts, its contract and its report, but gives the
experts to two `review-panel` agents rather than one agent each. An expert's run pays for reading its rules, the diff
and the code around it before it checks anything; a panel pays for that once for all its experts. The price is that one
agent holds several checklists, which the panel's definition guards against, but which makes a miss likelier than with
one expert per agent, a risk the workflow takes for the cost: it reviews every branch with this review, and
`/expert-review`, one agent per expert, runs on someone else's pull request and when the user asks for it.

Read `${CLAUDE_SKILL_DIR}/../expert-review/SKILL.md` whole, and follow it with the arguments in `$ARGUMENTS`, apart from
its Classify and its Run the experts, which [Classify](#classify) and [Run the panels](#run-the-panels) below replace:
spawn no agent per expert. That file writes its own directory as the variable `CLAUDE_SKILL_DIR`: read each path it
gives through that variable, such as the contract's and the commit rules', as one under
`${CLAUDE_SKILL_DIR}/../expert-review/`, never under this skill's directory.

## Classify

**A small diff of the current branch needs no panel.** Under about 100 changed lines of the default target, review it
yourself, as `${CLAUDE_SKILL_DIR}/../expert-review/SKILL.md` > Classify, "A small diff of the current branch needs no
subagent", says, but apply every expert, each through its own scope gate, rather than the experts that the paths pick,
then go on to its Verify.

**Otherwise, each panel gets every expert of its model,** whatever the paths pick, and no triage runs. The triage of the
expert review drops the experts with nothing to check, and adds those whose scope a diff falls in by what it holds
rather than by its paths, such as a changed citation of a document in a tool's message; each expert's scope gate does
both, and a panel applies it to the whole diff, which it reads once for all its experts. So every expert reads every
hunk, and `goal-reviewer` joins only with `--plan`, as the expert review picks it.

**A check of fixes** gives each panel the `--fixes` file, and, for each expert, the findings of its domain that the
fixes answer, which it checks. `correctness-reviewer` reviews every fix, and `security-reviewer` and `sandbox-reviewer`
every fix of a file in their scope. Every other expert reviews only a concern that the fixes newly touch, as
`${CLAUDE_SKILL_DIR}/../expert-review/SKILL.md` > Classify, "A check of fixes picks by finding, not by path.", names
them, and otherwise replies "No concern newly touched by the fixes.". Quote that rule in the prompt of each panel and of
each expert that runs alone, without its words on the experts that the paths pick, since every expert of a panel reads
the fixes whatever its paths, and no triage's `Fixes:` lines narrow what an expert alone reads.

**Group the experts by their definition's frontmatter:** one group for `model: sonnet`, one for `model: opus`. A panel
runs at one model and at its own `high` effort, so an expert whose frontmatter names another model, or none, or another
effort runs alone, as the expert review runs it. In each group, order the experts by what a miss costs, so that those
that matter most get the panel's fresh attention: `correctness-reviewer`, `security-reviewer`, `sandbox-reviewer`,
`architecture-reviewer`, `android-reviewer`, `performance-reviewer` on Opus, and `goal-reviewer`, `tests-reviewer`,
`conventions-reviewer`, `documentation-reviewer` on Sonnet. An expert that this order does not name comes last in its
panel.

Tell the user in one line: the target, the size, as the expert review measures it, each panel with its experts, the
experts that run alone, and the focus.

## Run the panels

Spawn all at once, in one message, in parallel, with the Agent tool:

- one `review-panel` per group, with `subagent_type` set to `review-panel` and `model` set to the group's model,
  `sonnet` or `opus`;
- each expert that runs alone, as `${CLAUDE_SKILL_DIR}/../expert-review/SKILL.md` > Run the experts says, with
  `subagent_type` set to its name, except that its prompt says that it reads every hunk of `scope.diff` and applies its
  own scope gate to the whole diff, in place of the hunks that the expert review's Classify gives.

Each panel's prompt holds:

- the absolute paths of the contract, `${CLAUDE_SKILL_DIR}/../expert-review/expert-contract.md`, and of its experts'
  definitions, in `${CLAUDE_SKILL_DIR}/../../agents/`, in the order of [Classify](#classify), each written without `..`;
- the root of the checkout under review, the path of `scope.diff`, the changed files with their status, the files moved
  without a change with their old paths, and what is under review: the branch, the commit range, or the pull request's
  number, as the expert review gives it, never its title or other text of it;
- that every expert reads every hunk of `scope.diff`, and applies its own scope gate to the whole diff;
- in a check of fixes, what [Classify](#classify) gives it;
- with `--plan`, the paths of the plan and of its mock, for `goal-reviewer`;
- the user's focus, word for word, if there is one.

Wait for every panel as the expert review waits for its experts, its cache kept warm included. If a panel's report
comes back partial, or lacks one of its experts, resume the panel once; an expert still missing has no report, which
the report says under "Not reviewed".

Then verify and write the report as the expert review does. Its verdict line says that the review was combined; "Not
reviewed" lists each expert that replied its line for a diff outside its scope, or that no fix concerns, with that
line; and its Cost lists each panel with its experts.
