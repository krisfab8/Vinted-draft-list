# Private OCR/review test deployment

Updated 2 October 2026. Target: existing Flask app, privately accessible from a phone/computer. Prepared configuration is not a verified deployment.

## Included

- `app.hosted:create_app()` requires a randomly generated password of at least 24 characters. Access uses browser HTTP Basic authentication over the hosting provider's HTTPS endpoint.
- All app pages/data/actions require that password except `GET /health`, which reports only health.
- Hosting guards reject invalid/escaping item folders and cross-site write requests and remove client tracebacks for unhandled errors.
- Vinted draft, browser login and tracker-refresh actions return a clear local-browser-required error. The UI displays a private-test banner.
- The Docker startup attaches items, data/index/logs/profile/memory and the cost CSV to `/var/data/vinted` on a durable disk. Do not deploy the file-based app on a disposable filesystem and expect persistence.
- Hosted configuration selects `openai` for both vision and listing writing, with `gpt-6-luna`. Haiku remains the local default.

This is a single-operator test. Do not give one password to unrelated sellers as a substitute for multi-user ownership/isolation. Full audit fixes and spending limits remain tracked work. Some existing route-specific errors still need normalization. Old Claude cost omissions and stats deduplication remain; do not use Stats as an authoritative whole-account invoice.

## Render setup

Connect the Render integration so the service can be created and inspected from this project. Alternatively, use the Render dashboard's Blueprint flow with this GitHub repository and the prepared branch `work/vinted-revival-plan`.

1. Review `render.yaml`: a Docker web service on a paid plan, 1 GB disk at `/var/data`, auto-deploy disabled and `/health` health check. Review the actual account quote before provisioning; no hosting cost is included in the penny-per-item target.
2. Authorize access to the GitHub repository/branch. The blueprint references the prepared branch; update it intentionally if the work is merged or renamed.
3. Add `OPENAI_API_KEY` directly in Render's secret/environment settings. Do not put it in this file, GitHub or the browser.
4. Let Render generate `APP_PASSWORD`. Retrieve it privately through the hosting dashboard. Username defaults to `kristian`. Change both if desired, keeping a long random password.
5. Deploy and wait for health. Open the actual HTTPS URL, sign in and confirm the private-test banner shows the intended model.
6. Upload one clear labeled garment. Check fields against the actual photos, correct a field, reload and inspect saved state.
7. Check OpenAI usage/billing for the real extraction and writer calls. The adapter has no automatic retries/cross-provider fallbacks; refused/incomplete responses fail for review. Failed billable responses are not yet fully ledgered.
8. Restart/redeploy the service and confirm that the same item, edit and cost CSV remain.

Do not publish a public URL with this protection removed. No private user items or auth sessions are embedded in the image; migrate real existing items through a deliberate backup/restore step if needed.

## Testing Haiku against Luna

Use the same source photos and recorded ground truth. For the Haiku baseline, set `VISION_PROVIDER=claude-haiku`, `LISTING_PROVIDER=claude-haiku` and add `ANTHROPIC_API_KEY` in hosting settings. Redeploy, record the configuration/version and collect a separate run. For Luna, set both providers to `openai`. Mixed provider runs are valid experiments but must be labeled; they do not measure an all-Luna pipeline.

`OPENAI_VISION_MODEL` and `OPENAI_LISTING_MODEL` independently select `gpt-6-luna` or `gpt-6.1-sol` in this adapter. Other names are rejected until their capabilities and cost handling are implemented. An OpenAI subscription/model selection in Codex does not supply this app's API key or cover its runtime billing.

No blind model upgrade: compare exact label reading, false premium claims, missing damage, correction time and cost per successful item. The OpenAI path deliberately does not invoke Claude-specific rereads/escalation; unresolved uncertainty remains review work.

## Local alternatives

For your existing visible-browser Vinted flow, keep using:

```powershell
.\.venv\Scripts\python.exe -m flask --app app.web run --host 127.0.0.1 --port 5000
```

For a local password-protected simulation of the hosted entry point, set `APP_PASSWORD` privately and use `--app 'app.hosted:create_app()'`. Do not expose a development server to the internet. Chrome is needed for existing local Vinted operations; it is not installed in the OCR-only Docker image.

## Verification boundaries and next steps

Automated tests use mocked provider responses. Local server checks verify routing and access behavior. A real Docker build, deployed persistence, provider model access/response compatibility and actual OCR quality need live verification. HOST-02 and MODEL-02 remain blocked until that happens.

Render documentation: [Docker](https://render.com/docs/docker), [persistent disks](https://render.com/docs/disks), [Blueprint reference](https://render.com/docs/blueprint-spec).
