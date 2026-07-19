---
name: cloudflare-deploy
description: Deploy and verify Cloudflare Pages sites and Cloudflare Workers in this studio. MUST be used for any task involving deployment, wrangler, environment variables/secrets, CORS, custom domains, staging vs production, or "it works locally but not deployed". Also use before changing anything in wrangler.toml or Pages build settings.
---

# Cloudflare deploy (Pages + Workers)

## Ground rules

- **Pages**: deploys are git-driven. Push to `main` → production; push to the staging
  branch → staging URL. Never deploy Pages manually when the repo is git-connected.
- **Workers**: deployed via `wrangler deploy` from the Worker repo. A shared Worker may
  serve multiple products via route prefixes — check AGENTS.md before touching routing;
  breaking another product's prefix is a production incident.
- **Secrets** live in `wrangler secret` (Workers) or the Pages dashboard env vars —
  NEVER in code, wrangler.toml plaintext, or git. Frontend gets only publishable keys
  (`VITE_*`).

## Worker deploy sequence

```bash
# from the worker repo root
npx wrangler deploy --dry-run     # 1. see what would ship
npx wrangler deploy               # 2. ship
# 3. verify: curl one known-good route AND one auth-guarded route
curl -s -o /dev/null -w "%{http_code}" https://<worker-host>/<product>/<route>   # expect 401/200 as appropriate
# 4. tail if anything is off
npx wrangler tail
```

## Change checklist for anything user-facing

- [ ] CORS allow-list still covers: prod domain, *.pages.dev preview, localhost dev ports
- [ ] Auth guard present on every user-scoped route (spot-check one)
- [ ] Staging verified BEFORE main, for any change to response shapes or streaming
      protocols (these break clients silently)
- [ ] Env vars/secrets referenced in code actually exist in the target environment

## Escalate, don't improvise

- DNS, custom domains, SSL settings → human
- Deleting/renaming Worker routes → human
- Anything in the Worker shared by multiple products where your task names only one → orchestrator
