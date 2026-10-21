# The repository

The repository is public, and the user's library holds private documents: what is committed, and what is written in a
pull request, is published.

## What belongs in the repository

- **The repository holds the current state of the project, and nothing else.** Never commit project-management material,
  which lives in `.pm/`, a separate private repository:
  - status or tracking files;
  - decision records;
  - roadmaps;
  - plans;
  - handoffs;
  - meeting or research notes;
  - the task markers `TODO`, `FIXME`, `XXX` and `HACK`, in a comment or a document.
- **No secret, credential, `.env` file or personal data,** as [No personal information](#no-personal-information)
  details: a stack's `.env`, the access token, the signing key and its password belong to one machine, and live outside
  the repository.
- **No file committed by accident:** build output, logs, temporary captures, an APK.
- **A change updates every document that describes what it changes, in the same change:** the rules file of a rule,
  `docs/foundations.md` for the design and its reasons, the references of `docs/` (`ARCHITECTURE.md`, `API.md`,
  `OCR_SANDBOX.md`, `SECURITY.md`) for what they describe, the skill of a procedure, `README.md` for setup, usage and
  scripts, and `CLAUDE.md` for how a session works.

## No real document names

- **No real document or book is named anywhere in the repository:** not in code, tests, fixtures, examples,
  documentation or commit messages. This covers titles, authors, file and folder names, and excerpts, and above all
  anything seen in the user's library. Use invented placeholders, such as `Example Book` and `Jane Doe`, so that no
  contributor leaks the user's private data.

## No personal information

- **Nothing personal about the maintainer, a contributor or a user is committed or written in a pull request,** apart
  from the author name and email of the commits and the copyright holder in `LICENSE` (the maintainer's GitHub handle).
  This covers usernames, the paths of an installation (`/home/<name>`, `/data/<name>`), IP and MAC addresses, hostnames,
  other projects found on a machine, devices tied to someone (naming the GPU a measurement was made on is fine), and
  anything that locates a person, such as a time zone or a city.
- **Write placeholders instead:** `/home/user`, `/data/USER/scanmylib`, `~/Dev/scanmylib`, `192.168.1.10`,
  `example.invalid`, a fixed offset (`+02:00`) or `UTC` for a time zone.
- **A value read on the machine never becomes a default or an example:** a path, an address or a time zone found there
  stays there. Documents address any reader, never the maintainer's own setup.

## External work

- **Credit every external work the project reuses in `CREDITS.md`, in the same change that brings it in.** This covers
  code or algorithms ported or adapted from another project, data taken from someone else's work, models, assets such as
  fonts or images, and libraries shipped in a build: the api's image, the app, the web UI or the OCR sandbox.
- **Each entry says** what is reused, where it lives in the repository or where the project installs it, where it comes
  from and under which terms. When a license asks for its notice to be kept, copy the notice verbatim.
- **The works the design comes from are named,** with their links, in `docs/foundations.md` > References.
