# Launching through the Meta Ads connector

hook-stack launches with **Meta's official Meta Ads connector** (Meta's MCP server at `https://mcp.facebook.com/ads`).
The user logs in with Facebook once; no developer app, no token, nothing secret stored by this skill.

## Connect it (once)
Check first: list the tools available in this session whose names contain `ads_` and come from the Meta Ads server
(for example `mcp__meta-ads__ads_get_ad_accounts`). Found and `ads_get_ad_accounts` answers: connected, move on.

Not there: give the user these steps and stop until they say done.
- **Claude Code (terminal or the desktop app's Code tab):** run once in a terminal
  `claude mcp add --transport http meta-ads https://mcp.facebook.com/ads`, then open Claude Code, type `/mcp`, pick
  `meta-ads` and log in with Facebook (pick the business portfolio that owns the ad account). Start a new session
  afterwards so the tools load.
- **Already added but "needs authentication":** `/mcp`, pick `meta-ads`, log in.
- Login asks which business portfolios to share: pick the one with the ad account, Page and Instagram account.

## Rules for every call
- **Read each tool's schema before calling it.** Meta adds and renames tools while the connector is in beta; never
  assume a parameter name. The names below are the ones Meta documents (Nov 2026).
- **Budgets are usually in the currency's minor unit** (cents for USD: 120.00 a day = `12000`). Confirm from the
  schema's description, and always show the user the real amount.
- **Everything is created paused.** Nothing spends until `ads_activate_entity` runs, and that only happens after the
  user approved the launch plan in chat.
- **Record every ID the moment it comes back** in `<project>/work/launch_state.json` (format below). If anything
  fails, nothing is lost and a re-run continues from the state file instead of creating duplicates.
- Never delete anything. Pausing (`ads_update_entity` status PAUSED) is the user's call, never automatic.

Documented tools this skill uses:

| Job | Tool |
|---|---|
| ad accounts / Pages / Instagram | `ads_get_ad_accounts`, `ads_get_ad_account_pages`, `ads_get_ig_accounts` |
| pixel (dataset) and whether it fires | `ads_get_datasets`, `ads_get_dataset_stats` |
| existing campaigns and ad sets | `ads_get_ad_entities` |
| media already in the ad account | `ads_get_ad_videos`, `ads_get_ad_images` |
| create | `ads_create_campaign`, `ads_create_ad_set`, `ads_create_creative`, `ads_create_ad` |
| switch on | `ads_activate_entity` |
| preview | `ads_get_ad_preview` |
| results | `ads_get_ad_entities` (insights fields, date range) |

## Getting the videos into the ad account
Meta's documentation (Nov 2026) lists no tool that uploads a local file, and marks video in `ads_create_creative` as
"limited availability" (rolling out by account). So, in this order:
1. **The connector can take the file.** If any tool's schema accepts a video file, local path, bytes or upload
   (for example an upload tool, or a `video` / `file` field in `ads_create_creative`), use it for each ad, plus the
   thumbnail (`ads/<id>-thumb.jpg`) if the schema takes one.
2. **Otherwise: one drag and drop.** Open the ads folder for the user (Mac: `open "<project>/ads"`, Windows:
   `explorer "<project>\ads"`) and ask them to drag every `H*.mp4` and `H*-thumb.jpg` into Meta's media library:
   Ads Manager, the menu, **Media** (or https://business.facebook.com/asset_library), pick the same ad account,
   **Upload**. About a minute for 12 ads. When they say done, `ads_get_ad_videos` and `ads_get_ad_images` list them:
   match each by file name (H01.mp4 = ad H01) and save the video ID and image hash/ID in the state file. Videos must
   show as ready (Meta processes them for a minute or two) before the creative is made.
3. **The account has no video creatives through the connector yet** (`ads_create_creative` refuses a video): tell
   the user plainly, keep everything that was made paused, and offer the hand-off: the ads, thumbnails and the copy
   are ready, and in Ads Manager they duplicate one ad per video. Do not switch to any other way of uploading.

## Creating the stack
For a new hook test (the default):
1. `ads_create_campaign`: name `[HS] <offer> | hook test | <date>`, the objective for the goal (sales
   `OUTCOME_SALES`, leads `OUTCOME_LEADS`, traffic `OUTCOME_TRAFFIC`), the daily budget at the campaign level
   (Advantage campaign budget), no special ad category unless the offer is credit, jobs, housing or politics.
2. `ads_create_ad_set`: name `[HS] Broad | <countries>`, the countries, ages 18 to 65, Advantage+ audience on,
   automatic placements, optimization for the goal (sales/leads: conversions on the pixel's PURCHASE / LEAD /
   SCHEDULE event; traffic: landing page views). Conversion goals need a pixel that fired in the last 7 days
   (`ads_get_dataset_stats`); if it has not, say so before launching.
3. For each ad, in order: `ads_create_creative` (Page, Instagram account, the video, the thumbnail, the one primary
   text, headline, CTA button, link with the UTM tags) then `ads_create_ad` (name = the ad's name from plan.json, the
   ad set, the creative). Save each ID as it returns.
4. Only when every ad exists: `ads_activate_entity` for each ad, then the ad set, then the campaign (skip if the user
   said keep it paused). Then read them back with `ads_get_ad_entities` and report each status (new ads show
   In review for minutes to hours; normal).

Adding to an ad set the user already runs (`mode: existing_adset`): skip 1 and 2, create the creatives and ads in
that ad set, and activate only the new ads. Never change that ad set's budget or status.

UTM tags for every link: `utm_source=facebook&utm_medium=paid&utm_campaign={{campaign.name}}&utm_content={{ad.name}}`.

## launch_state.json
```json
{"account_id": "act_...", "mode": "new_campaign", "campaign_id": "...", "adset_id": "...",
 "ads": {"H01": {"video_id": "...", "image": "...", "creative_id": "...", "ad_id": "...", "status": "ACTIVE"}},
 "live": "2026-11-05 09:12"}
```

## Results
`ads_get_ad_entities` at ad level for the project's ad IDs, with a date range (complete days only, ad account time
zone): spend, impressions, 3-second video views, ThruPlays, link clicks, and the goal's result count. Write them to
`<project>/work/results_raw.json` (format in `scripts/rank_hooks.py`) and run `python3 SKILL/scripts/rank_hooks.py
<project>`.
