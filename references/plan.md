# plan.json and launch.json

Both live in the project folder. Times are seconds in the ORIGINAL clip, taken from the `scan.py transcribe` output.

## plan.json (what build_ads.py edits)

```json
{
  "bodies": {
    "B1": {"clip": "c01", "start": 0.42, "end": 38.9}
  },
  "ads": [
    {"id": "H01", "name": "H01 | Stop paying editors | 2026-11-04",
     "hook": {"clip": "c02", "start": 0.31, "end": 4.12},
     "hook_text": "Stop paying editors", "body": "B1"},
    {"id": "H02", "name": "H02 | 12 ads in one take | 2026-11-04",
     "hook": {"clip": "c03", "start": 6.80, "end": 10.55, "cut": [[8.1, 8.6]]},
     "hook_text": "12 ads from one recording", "body": "B1"}
  ],
  "fixes": {"cloud": "Claude"},
  "style": {"caption_y": 1130, "hook_text_y": 300}
}
```

- **bodies**: one or more named bodies. A body recorded across several clips is a list, played in order:
  `"B1": [{"clip": "c01", "start": 0.4, "end": 20.1}, {"clip": "c04", "start": 1.2, "end": 18.0}]`
- **ads**: one per hook. `id` short and unique (H01, H02, ...), also the file name. `name` is what Ads Manager shows:
  keep the id first so results read at a glance. `body` names a body (or is a segment / list inline).
- **segment** fields: `clip` (id from clips.json), `start`, `end`, optional `tighten` (default true: pauses longer than
  `max_gap` are cut), optional `cut`: extra `[from, to]` ranges to remove (a restart in the middle of a take).
- **hook_text**: on-screen text for the first seconds (white rounded boxes, black text). Empty string = none.
- **fixes**: caption word replacements, matched as whole words, any case.
- **style** (all optional; config.json `style` sets your own defaults):

| key | default | what |
|---|---|---|
| `max_gap` | 0.35 | pauses longer than this get cut (seconds) |
| `silence_db` | -35 | how quiet counts as a pause; -30 in a noisy room, -40 in a very quiet one |
| `captions` | true | burned-in captions on or off |
| `caption_case` | `upper` | `upper` or `as_spoken` |
| `caption_size` | 82 | caption font size (px on a 1080x1920 frame) |
| `caption_y` | 1130 | caption centre line; Meta covers roughly the bottom 35% with its own buttons |
| `caption_max_words` | 3 | words per caption |
| `caption_color` / `caption_accent` | `#FFFFFF` / `#FFD60A` | text colour / colour of the word being said |
| `hook_text_y` | 300 | top of the hook text; Meta covers roughly the top 14% |
| `hook_text_size` | 64 | hook text font size |
| `hook_text_seconds` | auto | how long the hook text stays; auto = while the hook is spoken, at least 3 s |

## launch.json (the approved launch plan, what the connector calls are built from)

Written before the plan is shown, so what the user approves and what gets created are the same thing. The IDs come
from the Meta Ads connector (`references/meta-connector.md`).

```json
{
  "account_id": "act_1234567890",
  "page_id": "111111111111111",
  "instagram_user_id": "17841400000000000",
  "mode": "new_campaign",
  "campaign": {"name": "[HS] Offer | hook test | 2026-11-04", "objective": "OUTCOME_SALES", "daily_budget": 12000},
  "adset": {"name": "[HS] Broad | US", "optimization_goal": "OFFSITE_CONVERSIONS",
            "pixel_id": "222222222222222", "custom_event_type": "PURCHASE",
            "countries": ["US"], "age_min": 18, "age_max": 65},
  "copy": {"primary_text": "...", "headline": "...", "cta": "LEARN_MORE", "link": "https://...",
           "url_tags": "utm_source=facebook&utm_medium=paid&utm_campaign={{campaign.name}}&utm_content={{ad.name}}"},
  "go_live": true
}
```

- **Budgets are in the currency's minor unit**: 120.00 a day = `12000`. Always show the user the real amount.
- `mode`: `new_campaign` (campaign + ad set created, budget at the campaign level) or `existing_adset` with
  `"existing_adset_id": "..."` (ads added to an ad set the user already runs; no campaign/ad set is created and their
  status is left as it is; only the new ads are switched on).
- `instagram_user_id`: the Instagram account connected to the Page (`ads_get_ig_accounts`). Leave it out to run the
  ads under the Page only.
- Optional `ads`: `[{"id": "H01", "name": "..."}]` to launch only some of the built ads; default = every ad in
  `ads/manifest.json`.
- `go_live`: true switches everything on after it is all created; false leaves it paused.

| goal | objective | optimization_goal | needs |
|---|---|---|---|
| sales | `OUTCOME_SALES` | `OFFSITE_CONVERSIONS` | `pixel_id`, `custom_event_type: PURCHASE` |
| leads on a website | `OUTCOME_LEADS` | `OFFSITE_CONVERSIONS` | `pixel_id`, `custom_event_type: LEAD` (or `COMPLETE_REGISTRATION`) |
| booked calls | `OUTCOME_LEADS` | `OFFSITE_CONVERSIONS` | `pixel_id`, `custom_event_type: SCHEDULE` |
| traffic | `OUTCOME_TRAFFIC` | `LANDING_PAGE_VIEWS` | no pixel needed |

Conversion goals need a pixel that has fired recently (`ads_get_dataset_stats`). If it never
fired, say so before launching: a conversion campaign without working tracking spends money while Meta guesses.

CTA button values: `LEARN_MORE`, `SHOP_NOW`, `BUY_NOW`, `SIGN_UP`, `GET_OFFER`, `GET_QUOTE`, `APPLY_NOW`,
`CONTACT_US`, `SUBSCRIBE`, `DOWNLOAD`, `WATCH_MORE` (for booked calls, `LEARN_MORE` or `CONTACT_US`).
