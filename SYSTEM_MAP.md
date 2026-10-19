# SYSTEM_MAP.md

## What this product is

Local B2B outreach by Silabs (Sacred Intelligence Labs). It finds businesses, drafts a personal email, waits for a manual review, sends through the mailbox you configure, and keeps the result in a local CRM. Google Sheets export is optional. The public guide is README.md.

## Agencies and potential clients

- Agencies: companies you may contact through the Gmail mailbox.
- Potential clients: local businesses you may contact through the custom mailbox. Places come from the first-run setup. A computer that never finished setup still falls back to the built-in example regions.

## How you use it

1. Start with `./start.sh` on Mac or Linux, or `start.bat` on Windows.
2. Open `http://127.0.0.1:8000`.
3. On a fresh install, finish Setup. On a computer that already has a mailbox password in `.env`, go to Settings.
4. Search Potential Clients on Google Maps, or scrape Agencies.
5. Generate drafts in AI Engine.
6. Read the drafts in Review Queue.
7. Approve or reject each one.
8. Send approved emails in Email Sender.
9. Track replies and follow-ups in CRM.
10. Export a CSV, or sync to Google Sheets when you want to.

## Modules

- `settings`: local configuration in `.env`
- `scraper`: agency search and client search
- `ai_engine`: email drafts
- `review_queue`: manual review
- `email_sender`: manual send and a test email
- `crm`: outreach status, manual follow-up, CSV, and Google Sheets
- `system_control`: local database status and a local stop
- `setup`: first-run assistant

## Screens

- Dashboard
- Potential Clients
- Agencies
- AI Engine
- Review Queue
- Email Sender
- CRM
- Settings
- Setup, on a fresh install

## Endpoints

### App

- `GET /`
- `GET /{full_path:path}`

### Setup

- `GET /api/setup/status`
- `POST /api/setup/progress`
- `POST /api/setup/suggest-places`
- `POST /api/setup/resolve-places`
- `POST /api/setup/places`
- `POST /api/setup`

### Settings

- `GET /api/settings`
- `POST /api/settings`
- `POST /api/settings/test/gmail-smtp`
- `POST /api/settings/test/custom-smtp`
- `POST /api/settings/test/claude`
- `POST /api/settings/test/google-maps`

### Scraper

- `POST /api/scraper/agencies/scrape`
- `GET /api/scraper/agencies/job/{job_id}`
- `GET /api/scraper/agencies`
- `DELETE /api/scraper/agencies/{company_id}`
- `GET /api/scraper/meta/agency-locations`
- `POST /api/scraper/clients/search`
- `GET /api/scraper/clients/job/{job_id}`
- `GET /api/scraper/clients`
- `DELETE /api/scraper/clients/{company_id}`
- `GET /api/scraper/meta/categories`
- `GET /api/scraper/meta/suburbs`

### AI Engine

- `POST /api/ai/generate/batch`
- `POST /api/ai/generate/{company_id}`
- `GET /api/ai/job/{job_id}`
- `GET /api/ai/companies`

### Review Queue

- `GET /api/review`
- `GET /api/review/all`
- `PATCH /api/review/{email_id}/approve`
- `PATCH /api/review/{email_id}/discard`
- `PATCH /api/review/{email_id}/edit`

### Email Sender

- `POST /api/send/batch`
- `GET /api/send/approved`
- `GET /api/send/resume`
- `POST /api/send/resume`
- `POST /api/send/test-email`
- `POST /api/send/{email_id}`
- `GET /api/send/sample`

### CRM

- `GET /api/crm`
- `PATCH /api/crm/{record_id}/status`
- `POST /api/crm/sync-sheets`
- `GET /api/crm/export-csv`
- `GET /api/crm/followups`
- `POST /api/crm/followups/{record_id}/send`

### Local system controls

- `GET /api/system/status`
- `POST /api/system/stop`

## Main files

- `main.py`: FastAPI app and routers
- `database.py`: engine, session, and database init
- `models.py`: `Company`, `Email`, `OutreachRecord`
- `start.py`: the launcher used by Mac, Linux, and Windows
- `start.sh`: Mac and Linux shortcut
- `start.bat`: Windows shortcut
- `routers/*.py`: endpoints for each module
- `services/*.py`: business logic and integrations
- `static/index.html`: the app shell
- `static/js/*.js`: each screen
- `.env`: local configuration, not published
- `outreach.db`: local SQLite database, not published
- `google-service-account.json`: optional Google Sheets credential, not published
- `static/assets/resume.pdf`: optional PDF attachment, not published

## Database

### `companies`

Stores agencies and potential clients. Main fields: `name`, `address`, `phone`, `website`, `email`, `category`, `rating`, `reviews_count`, `digital_score`, `source`, `company_type`, `stack_keywords`, `place_id`, `created_at`.

### `emails`

Stores drafts and sent emails. Main fields: `company_id`, `subject`, `body`, `from_address`, `status`, `created_at`, `reviewed_at`, `sent_at`, `review_notes`.

### `outreach_records`

Stores outreach history. Main fields: `company_id`, `email_id`, `status`, `sent_at`, `replied_at`, `follow_up_date`, `follow_up_sent`, `notes`, `sheets_row`, `created_at`.

## External services

- Gmail SMTP
- Custom SMTP mailbox
- Anthropic Claude
- Google Maps Places API
- Google Sheets API
- DuckDuckGo HTML
- Clutch
- TechBehemoths
- public websites of the leads

## First launch

- `GET /api/setup/status` says whether this install needs the assistant.
- An install that already has a mailbox password in `.env` opens the Dashboard.
- An empty install opens the assistant first.
- The assistant order is: you, Maps key, one chosen country, one chosen state, marked cities, audience and niches, Claude key, mailbox, review.
- Country, state, and city are not free text. A name that was only typed, and not chosen, is ignored. Google confirms the choice.
- After setup, country, state, and cities can be edited in Settings.
- `POST /api/setup/resolve-places` confirms the country and each city before you continue. Finish confirms them again and stores the address Google returned.
- Identity, country, cities, niches, and the sending route are stored in `profile.json`.
- Passwords and keys stay in `.env`.
- Saving the mailbox in the middle of the assistant does not close the assistant. Only an install that already had a password before the assistant skips it.
- With a completed profile, search uses the cities and niches from that profile.

## How it starts

- `./start.sh` on Mac and Linux, `start.bat` on Windows. Both call `start.py`.
- Requires Python 3.10 through 3.13.
- Creates `venv` in the layout of the current system (`bin` or `Scripts`).
- Installs `requirements.txt` only when it needs to.
- If port `8000` is busy, it explains that and does not stop the other process.
- Serves `http://127.0.0.1:8000`.

## Settings

- UI in `static/js/settings.js`
- Saved in `.env`
- Backend in `routers/settings.py`
- Logic in `services/settings_service.py`
- Sensitive values come back masked
- Covers SMTP, the Claude and Maps keys, Google Sheets, and scraper limits

## Search

### Agencies

- Google Places is the main source. DuckDuckGo, Clutch, and TechBehemoths are fallbacks.
- A completed profile uses the saved cities. Without one, the screen still offers the built-in example regions.
- Default cap is 25 new agencies per scrape.
- Reads the website and tries to detect the stack.
- Deduplicates by `place_id`, domain, and email.
- Saves `company_type=agency`.

### Potential clients

- Uses the Google Maps Places API.
- Searches by category and place.
- Loads place details and tries to read an email from the website.
- Computes `digital_score`.
- Deduplicates by `place_id`, domain, and email.
- Saves `company_type=client`.

## AI Engine

- Lists companies that can receive a draft.
- Skips a company with no email when you are choosing who to write to.
- Generates in a batch through Anthropic.
- Creates `emails` rows with `status=pending`.
- Sets the sender from the agency mailbox or the client mailbox.

## Review Queue

- Lists pending drafts and all emails.
- You can edit, approve, or discard.
- Only `approved` emails reach Email Sender.

## Email Sender

- Lists only `approved` emails.
- You send one email or a batch.
- `auto` routing sends an agency through Gmail and a potential client through the custom mailbox.
- Can attach `resume.pdf`.
- Creates an `outreach_records` row when a send succeeds.

## CRM

- Shows `outreach_records`.
- You update the status by hand.
- Shows follow-ups that are due.
- Sends a follow-up only when you ask.
- Exports a CSV.
- Can sync the Google Sheet.

## Google Sheets

- Uses `GOOGLE_SHEETS_ID` from Settings.
- Uses `google-service-account.json` in the project folder.
- Sync clears `Sheet1` and writes the records again.
- The local CRM works without it.

## Resume PDF

- Expected at `static/assets/resume.pdf`.
- Status: `GET /api/send/resume`.
- Upload: `POST /api/send/resume`.
- Only a valid PDF.
- Attached when you tick it in Email Sender or Test Email.

## Test email

- Lives on the Email Sender page.
- Sends a real email without creating a lead, a campaign, a draft, or a CRM row.
- You choose `gmail` or `custom`.
- Accepts subject, body, recipient, and an optional attachment.
- Has a preview that is separate from sending.

## Stop

- Shown under Local System Controls on the Dashboard.
- Uses `POST /api/system/stop`.
- Localhost only.
- Stops this process.
- Start again with `./start.sh` or `start.bat`.

## What stays manual

- Settings
- What to search
- Draft generation
- Review, approve, and reject
- Sending
- Follow-up
- CSV export
- Google Sheets sync
- Starting the app again with `./start.sh` or `start.bat`
