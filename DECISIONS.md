# DECISIONS.md

## Decisions already made

- The system runs locally.
- The system is single-user.
- There is no login.
- There is no automatic scheduler.
- Follow-up is manual.
- An in-app restart will not be added.
- `start.sh` is the Mac and Linux launcher. Windows uses `start.bat`. Both call `start.py`.
- Gmail is the mailbox for agencies.
- The custom SMTP mailbox is the mailbox for potential clients.
- `resume.pdf` can be attached to agency emails.
- Potential clients are local businesses.
- Agencies are companies that may take overflow work.

## What that means for later changes

- Keep the manual flow.
- Do not add authentication unless it is asked for.
- Do not turn the launcher into a system service unless it is asked for.
- Routing between Gmail and the custom mailbox is expected behavior.
