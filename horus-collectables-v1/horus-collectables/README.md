# Horus Collectables — Website V1

A mobile-friendly, black-and-gold landing website ready for Railway. No paid website builder or database required.

## Deploy on Railway
1. Extract this folder and upload its contents to a new GitHub repository.
2. In Railway, create a **New Project** → **Deploy from GitHub repo**.
3. Choose the repository. Railway detects Node.js and runs `npm start`.
4. In Railway's service settings, open **Networking** → **Generate Domain** to get a `.up.railway.app` address.
5. Optional: add your purchased domain under **Custom Domain**, then add the DNS records Railway provides in your registrar's DNS settings.

## Edit
- `public/index.html`: website text, sections, links.
- `public/style.css`: colours, layout and fonts.
- `public/favicon.svg`: temporary Horus-inspired emblem. Replace this and the hero logo with your official Horus Collectables artwork when available.
- `public/script.js`: mobile menu and copyright year.

## Before publishing
- Replace the placeholder email (`hello@horuscollectables.com.au`) with a real contact address or remove the contact button.
- Add your real Whatnot/social links when ready.
- Review the introductory copy and collection categories.
- Note that there is no checkout, login, product management, or database in V1.

## Local test
Run `npm start`, then visit http://localhost:3000.

## Hosting costs
The site has no external paid dependencies. Railway hosting is billed according to your plan and resource usage.
