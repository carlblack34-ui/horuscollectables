# Horus Collectables

Private Flask portal for sealed products, singles, graded cards and accessories. Inventory/purchase lots, edits, archived empty lots, sales edits/voids, actual fees and seller shipping, giveaways/write-offs, date-filtered dashboard/reports, CSV exports and audit records are included. Amounts are AUD.

## Guided stock entry update

The current app design uses a desktop sidebar, mobile bottom navigation, dashboard quick actions and inventory cards with Edit/Sell buttons. Adding stock is a four-step flow: Game → Set → Product → Purchase, using clickable tiles for games, eras, sets and products. Set search narrows the expansion tiles; optional shipping/grading/supplies fields expand when needed. Numeric cost entry still uses ordinary inputs.

Stock entry now uses clickable TCG buttons and linked dropdowns: **Pokémon → Sun & Moon → Sun & Moon Base → Booster Box / Booster Pack / ETB**. Product suggestions change with the game and stock type. Game, era, set, language, product, condition and purchase details are saved with each lot. Inventory can be filtered by TCG. Manage catalogue lets you add and reuse any missing game, era or set. See [catalogue coverage and references](CATALOGUE.md) for the starter lists and regional limitations.

### Updating an existing installation

Stop the running app first and back up your current database. Extract `Horus-Collectables-Upgrade.zip` over your **existing project folder**. This archive contains code and templates and excludes databases, original uploads and local secrets, so your current account and stock remain in place. Restart the app with `python app.py` and reload your browser. The next start adds catalogue fields and tables. If using the full project archive instead, copy only code, templates, static files and documentation; **do not replace your current `whatnot_stock.db` or `.local-secret` with files from a fresh archive**.

## Start locally (Windows)

Use Python 3.12 or 3.13. Extract this whole folder, including templates and static assets.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
flask --app app:create_app create-user carl
python app.py
```

The account command asks for a hidden password and confirmation. Use at least 12 characters. Open http://127.0.0.1:5000. There are no default credentials. The same command resets an account password. Never put passwords in chat, source code, command arguments or GitHub. Local sessions use a generated `.local-secret`; production requires an explicit secret.

## Cost and stock rules

Each stock row is a purchase lot. Quantity is units originally purchased, not units remaining. All purchase cost fields are **per unit**. Split a supplier order into lots and allocate shared freight fairly across them; enter new purchases as new lots. Sales gross, fees and seller shipping are **whole-line totals**, matching the original app's meanings. Seller shipping is an expense, not buyer shipping revenue. Include buyer shipping revenue in gross only if it is paid to you and not already included in the platform total. Graded details belong in condition; SKU can hold card/certificate numbers. Custom categories, sets and conditions remain supported.

Available = purchased − active sales − active giveaways/write-offs. Voiding returns units; voided entries stay visible but are excluded from totals. Giveaway/write-off loss = units × recorded cost + extra expense. Do not also enter a giveaway as a zero-value sale. Expenses already included in landed cost must not be entered again as an extra adjustment expense.

Transactions retain landed cost and category snapshots when purchase lots are edited. Editing quantity updates total transaction cost using that snapshot; moving a transaction to another lot takes that lot's cost. Historical costs absent from the old database are initialized from its current stock costs: older edits cannot be reconstructed. Contribution = gross − fees − seller shipping − cost of sales − adjustment losses. This is operational tracking, not a tax ledger; GST, general overhead, refunds and platform reconciliation are not automated. Record corrections by editing/voiding the relevant sale. CSV exports include voided rows; downstream analysis must filter `voided=0`.

## Existing data and migration

The supplied `whatnot_stock.db` is included for local use. `originals/` preserves all received source files and an untouched database. First startup adds new columns/tables without deleting or replacing original records. It classifies Single/Bulk as singles and Slab as graded; review other categories manually. Original shipping/grading/supplies values retain the original per-unit interpretation.

Before upgrades, stop the app and back up the database (including a consistent SQLite backup if it is in use). Never edit the original backup. For PostgreSQL, copy the SQLite database to a working file and run the importer below. Target must be empty; transfer is one transaction, preserves IDs and checks row counts, resets sequences, and refuses existing target data. Run while both applications are stopped. Back up PostgreSQL before each deployment. No automatic database rollback is provided; restore a backup if necessary.

```powershell
Copy-Item whatnot_stock.db migration-copy.db
# Set DATABASE_URL privately in this terminal using your secret manager / secure env flow.
python migrate_to_postgres.py migration-copy.db
```

The public connection string is needed when importing from your computer; use Railway's private service reference for the deployed app. Do not log or commit either string. Validate inventory and sale counts, totals, and sampled records before enabling the public domain.

## GitHub and Railway deployment

1. Create a private GitHub repository. Commit application files, templates, static assets, requirements, config, tests and this README. `.gitignore` excludes all databases, original uploads, passwords and local secrets. Check the staged files before pushing. **Do not upload the supplied business database to GitHub.**
2. In Railway, deploy from that repository and add a PostgreSQL service. In the app service Variables set `DATABASE_URL` to the PostgreSQL service's `DATABASE_URL` reference, `APP_ENV=production`, and `SECRET_KEY` to a randomly generated secret of at least 32 bytes. Enter these through Railway's private Variables interface. A local generator is `python -c "import secrets; print(secrets.token_hex(32))"`; keep the result private.
3. Railway config starts Gunicorn with two workers, binds Railway's `PORT` and probes `/health`. Schema updates run under a database migration lock. Use PostgreSQL for production: Railway's default application filesystem is ephemeral. Set the service's Python version to 3.13 if required by your build settings.
4. Before creating an account, import the local database into the empty PostgreSQL database. Then use Railway's authenticated service shell to run `flask --app app:create_app create-user carl`; enter the password at its hidden prompt. This command must run in the deployed service environment, not just locally.
5. Enable the Railway HTTPS domain. Check health, login, inventory quantities, exports and dashboard totals. Perform a test sale and void it to verify stock restoration. Keep `APP_ENV=production` so cookies require HTTPS. Flask debug mode is disabled.
6. Enable database backups and periodically test restoring them. Take an explicit backup before changing database schema. Deploys from GitHub will update code; they must not overwrite the database.

Railway references: [Flask deployment](https://docs.railway.com/guides/flask) and [PostgreSQL service configuration](https://docs.railway.com/databases/postgresql).

## Verification

```powershell
python -m unittest -v
```

Tests use temporary databases and verify legacy data preservation, authentication/CSRF, password hashing and lockout, templates, malformed amounts/quantities, overselling (including simultaneous SQLite requests), edits, voids and cost snapshots. PostgreSQL import and Railway deployment require a real service and must be verified there; this delivery does not claim a live deployment. The earlier spreadsheet was not available in the referenced attachments and is not imported.

Security: password hashing with Werkzeug scrypt, CSRF on every POST, secure/HttpOnly/SameSite production cookies, eight-hour sessions, generic login errors and persisted per-account lockouts after five failed attempts. Use Railway/network rate limiting for broad request floods. Resetting a user's password does not revoke their already signed-in sessions; rotate SECRET_KEY to sign out everyone after an incident. This is a single-business portal: every created user can manage all stock and reports. Audit entries capture actor/action/record references, not complete before/after revisions.
