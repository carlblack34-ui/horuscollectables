# Horus Collectables

Private Flask portal for sealed products, singles, graded cards and accessories. Product inventory, dated purchases, moving weighted average cost, purchase/selling-price history, sales edits/voids, actual fees and seller shipping, giveaways/write-offs, date-filtered dashboard/reports, CSV exports and stock movement records are included. Amounts are AUD.

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
flask --app app:create_app create-user carl --admin
python app.py
```

The account command asks for a hidden password and confirmation. Use at least 12 characters. Open http://127.0.0.1:5000. There are no default credentials. The same command resets an account password. Never put passwords in chat, source code, command arguments or GitHub. Local sessions use a generated `.local-secret`; production requires an explicit secret.

## Admin: people and access

Admins have a **People & access** screen at `/admin/users`, reached from the Admin sidebar button. It provides user creation, Admin/Staff role selection, enable/disable, lockout clearing and password reset. Users are disabled rather than deleted, so their purchases, sales and audit history remain intact. Staff share live inventory but cannot manage users or read the admin audit export. You cannot disable your own account or remove the last enabled admin. Passwords are hashed and cannot be viewed or recovered.

### First admin on your existing Railway installation

Existing accounts keep their access to the shared business data and start as Staff. No arbitrary existing account is silently promoted. After deploying this upgrade, run this **once in the authenticated Railway app service terminal**, replacing `YOUR_USERNAME` with your existing username:

```text
flask --app app:create_app promote-admin YOUR_USERNAME
```

Sign in again. The Admin button now appears for that account. This command preserves the password and does not require putting credentials in chat. If setting up a fresh installation, `flask --app app:create_app create-user YOUR_USERNAME --admin` privately prompts for the first admin's password. The trusted CLI can also reset an existing account as an emergency recovery path; it revokes old sessions and re-enables the account.

Passwords set through the admin UI are temporary: the user must change them at their first/next sign-in before viewing or changing business data. The reset immediately invalidates their previous sessions and clears failed-login lockouts. Role changes and disabling/enabling accounts also invalidate previous sessions; enabling an account does not resurrect an old session. Own-password changes require the current password and matching confirmation, keep the current session and revoke other sessions. Use 12–256 characters. Give temporary credentials directly to the intended user through your trusted private channel, never through GitHub or this chat. Password values and hashes are excluded from account screens, exports and admin audit details.

For the live upgrade, back up PostgreSQL, upload the extracted code-only upgrade to the existing repository, and retain the current Railway database and secret variables. Schema version 6 adds account roles, status and session version fields without deleting accounts, passwords or stock data.

## Products, purchases and pricing history

Inventory shows one product card. Repeated purchases of the same product create dated purchase receipts underneath that card. Use **Restock** from the product card to preselect its details. **History** opens supplier/date/unit-price/landed-cost purchase history, sales, selling-price changes and the stock movement ledger. A selling price can be set per product and used to populate a sale total; changing it never changes purchase costs.

Automatic matching uses product name, game, era, set, product format, stock type, condition/grade, language and SKU. Case and repeated spaces are normalised. Dates, supplier, notes, quantity and cost are excluded from matching. Different languages, grades, SKUs or product variants remain separate. The existing Pack/Booster Pack, ETB/Elite Trainer Box, Single/Single Card and Slab/Graded Card category aliases are recognised. A different name or SKU remains separate deliberately: use Restock and keep the product details unchanged to avoid accidentally creating a new variant. Do not change a purchase's identity to move it into a different product.

**Moving weighted average landed cost** uses the stock currently on hand, not all purchases ever made:

```
New average = (current stock value + new purchase landed total)
              / (current available units + purchased units)
```

20 units at $8 plus 10 at $9 gives 30 units, $250 value and $8.33 displayed average. If 10 of the first units were sold before the $9 purchase, the restock averages 10 remaining at $8 plus 10 at $9: $8.50. Calculations retain more precision than the displayed two decimals; full depletion consumes the exact remaining value.

All four purchase cost fields remain **per unit**. Shared order freight, grading and supplies should be allocated across the units purchased. Sale price, platform/payment fees and seller shipping are **whole-line totals**. Seller shipping is an expense; buyer shipping revenue belongs in gross only if paid to you and not already included there.

Each new sale/giveaway/write-off removes units and saves the weighted average cost and total cost at the time it is entered. Report dates filter transactions; entering a backdated purchase does not replay or rewrite earlier recorded costs. Historical sale snapshots are never recalculated when restocking or changing selling prices. Giveaway/write-off loss = recorded total stock cost + extra expense, counted once. Do not also record it as a zero-price sale.

Voids restore the transaction's recorded quantity and total cost exactly once. A same-product sale edit retains the sale's recorded unit cost; moving it to another product uses that product's current average. Corrections that would leave negative inventory value or value without stock are refused: void and re-record the transaction at the current average instead. Failed changes roll back both balances and movement records. Purchase quantities/costs can be corrected before the product has any sales or adjustments. After that, financial purchase fields are locked; receipt date, supplier and notes can still be corrected. Add new purchases using Restock.

The movement ledger records receipts, corrections, issues and reversals with actor, quantities, value and resulting balance/average. Selling-price history records who changed a price and when. Times are UTC. Exports: `/export/stock` gives current products and averages, `/export/purchases` all original receipts, and separate exports provide sales, adjustments, movements, selling-price history and audit records. Exports include voided transactions; downstream reports must exclude them from active totals.

Contribution = gross − fees − seller shipping − recorded cost of sales − adjustment losses. GST, overhead, refunds and platform reconciliation are not automated. Correct sales through edit/void. Every account shares this business inventory.

### Upgrading your live Railway app

Take a PostgreSQL backup first and pause data entry while deploying. Upload the **extracted code-only upgrade files** to the existing GitHub repository. Keep the same Railway database service and DATABASE_URL; never replace or delete it. Let Railway redeploy the existing app service. Schema version 5 automatically groups matching existing purchase lots and sets the opening balance to their combined remaining quantities and original landed values. All original purchase, sale and adjustment rows remain, and existing sale cost/profit snapshots are preserved. From that point, new receipts and issues use moving weighted average costing. Historical moving averages cannot be reconstructed, so migration opening movements are labelled explicitly. Check your product counts, total available units and inventory value after deployment before resuming entry. Both logins continue using the same data.

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
4. Before creating an account, import the local database into the empty PostgreSQL database. Then use Railway's authenticated service shell to run `flask --app app:create_app create-user carl --admin`; enter the password at its hidden prompt. This command must run in the deployed service environment, not just locally.
5. Enable the Railway HTTPS domain. Check health, login, inventory quantities, exports and dashboard totals. Perform a test sale and void it to verify stock restoration. Keep `APP_ENV=production` so cookies require HTTPS. Flask debug mode is disabled.
6. Enable database backups and periodically test restoring them. Take an explicit backup before changing database schema. Deploys from GitHub will update code; they must not overwrite the database.

Railway references: [Flask deployment](https://docs.railway.com/guides/flask) and [PostgreSQL service configuration](https://docs.railway.com/databases/postgresql).

## Verification

```powershell
python -m unittest -v
```

Tests use temporary databases and verify legacy data preservation, product grouping, remaining-stock weighted averages, buying/selling across receipts, full depletion, migration profit preservation, selling-price history, concurrent receipts/sales, reversals, rollback and ledger reconciliation, plus authentication/CSRF, password hashing, lockout and templates. PostgreSQL import and Railway deployment require a real service and must be verified there; this delivery does not claim a live deployment. The earlier spreadsheet was not available in the referenced attachments and is not imported.

Security: password hashing with Werkzeug scrypt, CSRF on every POST, secure/HttpOnly/SameSite production cookies, eight-hour sessions, generic login errors and persisted per-account lockouts after five failed attempts. Use Railway/network rate limiting for broad request floods. Password resets, account disablement and role changes revoke the affected user’s existing sessions. Own-password changes retain the current session and revoke other sessions. This is a single-business portal: Staff can manage stock, sales and reports; Admins also manage users and export the administration audit log. Audit entries capture actor/action/record references, not complete before/after revisions.
