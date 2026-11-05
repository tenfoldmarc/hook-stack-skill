---
name: hook-stack
description: "Turn one recorded body and a bunch of different hooks into a stack of finished video ads (every hook + the body, dead air cut, 9:16, burned-in captions, on-screen hook text), show a launch plan, and on approval upload and launch them all on Meta (Facebook + Instagram) in one go. Later, rank the hooks by hook rate and cost per result. Use for /hook-stack, 'edit and launch my hooks', 'I recorded a body and hooks', 'turn these clips into ads', 'launch these video ads', 'which hook won', 'hook stack results'."
---

# /hook-stack

The workflow: record ONE body (the main pitch) and a bunch of different hooks (the first 3 to 6 seconds), drop the
clips on the computer, and say "edit and launch them". This skill finds the clips, figures out which is the body and
which are hooks, edits every hook + body into its own ad, shows one launch plan, and after a yes launches every ad
on Meta. 12 hooks = 12 new video ads, all testing one thing: the hook.

`SKILL` below means this skill's folder (the one holding this file). `PY` means `SKILL/.venv/bin/python`
(Windows: `SKILL\.venv\Scripts\python.exe`). Scripts print plain progress; read their output, don't guess.

| Command | What happens |
|---|---|
| `/hook-stack` | Edit and launch: Steps 1 to 6 |
| `/hook-stack edit` | Edit only (no Meta needed): Steps 1 to 4 |
| `/hook-stack results` | Rank the hooks of the last launch (Step 7) |
| `/hook-stack setup` | Run or redo first-time setup (Step 0) |

## Hard rules
1. **Money moves only on a yes.** Nothing is uploaded to Meta or switched on until the user approves the launch plan
   in chat (Step 5). The plan states the daily budget in their currency, in plain numbers.
2. **Meta only through Meta's connector.** Every read and write on the ad account goes through the Meta Ads connector
   (Meta's official MCP, `references/meta-connector.md`). No tokens, no other upload routes. Read each tool's schema
   before calling it.
3. **Pause, never delete.** The skill never deletes a campaign, ad set, ad, video or file. It only touches what it
   created, plus the one existing ad set the user picks to add ads to.
4. **Same copy on every ad.** One primary text, one headline, one link for the whole stack, so the hook is the only
   thing being tested. Different bodies or offers = a separate stack.
5. **Captions and hook text say what was said.** Fix misheard brand words with `fixes`; never invent claims. Every
   number in the ad copy comes from the user.
6. **No em dashes** in any on-screen text or ad copy.
7. Original clips are never changed; everything is written to the project folder.

## Step 0. First-time setup (once)
Run `python3 SKILL/scripts/setup_skill.py --check`. If it says READY and `SKILL/config.json` exists with
`"setupComplete": true`, skip to Step 1. Otherwise:
1. Run `python3 SKILL/scripts/setup_skill.py` (no `--check`). It installs the skill's own Python environment with
   tested versions (1 to 3 minutes the first time). If it prints `fix:` lines (ffmpeg or Python missing), give the
   user those exact lines to run, one per code block, and stop until they say done. Then run it again.
2. Ask, in one message, only what the ads need (short answers are fine):
   - Brand or business name
   - Landing page link the ads should send people to
   - Goal: sales, leads, or traffic (and the price of the offer, if sales)
   - Daily budget for a hook test (suggest about 10 to 20 per hook per day in their currency, or what they already
     spend) and the countries to show ads in (default: United States)
   - Words the captions must spell right (brand, product, their name)
3. Save `SKILL/config.json` (format in `config.example.json`). The Meta part (ad account, Page, Instagram, pixel IDs)
   is filled in at the first launch (Step 5), so `/hook-stack edit` works before Meta is connected.

## Step 1. Find the clips
- The user names files or a folder: use those. Otherwise run `PY SKILL/scripts/scan.py list` (newest videos in
  Downloads). An AirDropped batch lands within a few minutes of each other; take the newest batch (stop at the first
  gap of 10+ minutes) and say in one line which files you took, then keep going.
- Make the project folder: `<projects_dir from config, default ~/hook-stack>/<YYYY-MM-DD>-<short-slug>/`.

## Step 2. Transcribe
`PY SKILL/scripts/scan.py transcribe <project> <clip1> <clip2> ...` (add `--vocab "Brand, Product"` from config).
It prints every clip with word times. Read all of it.

## Step 3. Sort the clips and write the plan
Decide from the transcripts (not from file order):
- **Body** = the clip(s) that explain the offer and end with the call to action, usually the longest. A body recorded
  in several clips becomes a list of segments in order.
- **Hooks** = short openers that each grab attention a different way. One clip can hold several hooks (split it by
  the pauses); one hook can have several takes (use the last complete clean take: people repeat a line until it
  lands). Drop false starts, "wait, let me redo that", and anything that is not a hook.
- In/out points: start about 0.1 s before the first word of the take, end about 0.15 s after its last word. Pauses
  inside get cut automatically (`max_gap`), so don't chop by hand unless a restart sits mid-take (use `cut`).
- **Hook text** per ad: the on-screen line for the first seconds, Instagram-native style. 3 to 8 words that carry
  the hook's promise in plain words, complementing (not repeating word for word) what is said. No em dashes.
- `fixes` for words the transcript gets wrong (for example `{"cloud": "Claude"}`).
Write `<project>/plan.json` (format: `references/plan.md`). Post a short table to the user: ad id, hook (what is
said), hook text, and keep going without waiting.

## Step 4. Edit and check
`PY SKILL/scripts/build_ads.py <project>`. It cuts each hook and the body once, renders every ad to `ads/H01.mp4`...,
writes thumbnails, `ads/manifest.json`, and `work/qa_sheet.jpg`, then re-transcribes every cut and prints a word
check.
- **Word check:** `ok` = the cut says what the plan expects. `CHECK` lines show what was heard, with times in the
  original clip. An extra word at the start (a restart like "then check, then check", or half a word) means move
  `start` to just before the clean take (use the printed times). A planned word not heard means a clipped word:
  start earlier or end later. Same meaning, different spelling ("got to" for "gotta") is fine. Fix `plan.json`, then
  rebuild only those ads with `--only H03,H05` and check again until every line is ok.
- **Look at `work/qa_sheet.jpg`** (Read it): hook text readable and not over the face, captions inside the frame and
  over the chest, not the face. If the face sits high or low, move `hook_text_y` / `caption_y` in plan `style`.
- `/hook-stack edit` ends here: send the user the ads folder path and a one-line summary per ad.

## Step 5. Launch plan (wait for approval)
1. **Meta connected?** Open `references/meta-connector.md` and follow it: check the Meta Ads connector's tools are
   there and `ads_get_ad_accounts` answers; if not, give the user the connect steps and stop until they say done.
   First launch: pick the ad account, Page, Instagram account and pixel with the connector's list tools (ask only
   when there is more than one) and save the IDs in `config.json` → `meta`.
2. **Where the ads go:** default is a new hook-test campaign (one campaign with the daily budget, one broad ad set,
   all the ads in it). If the user already runs a campaign they like, offer to add the ads to one of its ad sets
   instead (`mode: existing_adset`; no new budget is created, the ad set's own budget is used).
3. **Copy:** write one primary text (hook-free: the body's promise in 1 to 3 short sentences, first 125 characters
   carry it), one headline (under 40 characters), CTA button, link with UTM tags. Use the user's own words from the
   body transcript; no invented numbers or claims; no em dashes.
4. Write `<project>/launch.json` (format: `references/plan.md`) and read it back for mistakes (budget in minor
   units: 50.00 = 5000; for a conversion goal, the pixel fired in the last 7 days).
5. Show the plan in one message and wait:

> **Launch plan: [n] video ads, one hook each, same body**
> | Ad | Hook (said) | Hook text | Length |
> |---|---|---|---|
> | H01 | ... | ... | 0:34 |
> - Campaign: [name], [goal], optimizing for [event] · Budget: [amount]/day at the campaign level
> - Audience: [countries], ages [x to y], broad (Meta finds the buyers) · Placements: Facebook + Instagram, automatic
> - Copy (every ad): "[primary text]" · Headline "[headline]" · Button [CTA] · Link [url]
> - Ads go live as soon as you approve (or say "approve but keep them paused").
>
> Approve?

Send the user 2 or 3 of the ads (SendUserFile when available, else the paths) with the plan so they can watch them.

## Step 6. Launch
On approve: set `go_live` (false if they said keep paused) and launch with the Meta Ads connector exactly as
`references/meta-connector.md` lays out:
1. Get the videos and thumbnails into the ad account (the connector's own upload if it has one, otherwise the
   one-time drag into Meta's media library, then match them by file name).
2. Create the campaign and ad set (or use the existing ad set), then a creative and an ad for every hook, all paused,
   saving every ID to `work/launch_state.json` as it comes back.
3. Only once every ad exists, switch on the ads, then the ad set, then the campaign.
A failure stops with everything still paused: tell the user what failed in plain words, fix it, and continue from
`launch_state.json` (never recreate what already exists). Then read the ads back and report: how many are live or in
review (new ads sit in review for minutes to hours, which is normal), the Ads Manager link
(`https://adsmanager.facebook.com/adsmanager/manage/ads?act=<number>&selected_campaign_ids=<id>`), and when to check
results (after about 3 days or 1,000+ impressions per ad).

## Step 7. Results
Pull ad-level numbers for the project's ads with the connector's reporting tool (latest project unless the user
names one; complete days only), write `work/results_raw.json`, and run `python3 SKILL/scripts/rank_hooks.py
<project>` (format and maths in that script). It ranks every hook and saves `work/results.json`. Explain it in plain
words:
- **Hook rate** (3-second views / impressions) is the hook's own score. Above about 30% is strong, under 20% weak.
- Cost per result decides the winner once there are a few results; before that, lean on hook rate and CTR.
- Recommend: keep the top 2 or 3, pause the clear losers (only after the user says so: pausing is their call), and
  record new hooks in the style of the winner. Never change budgets without a yes.

## Files
- `scripts/setup_skill.py` setup and health check · `scripts/scan.py` find and transcribe · `scripts/build_ads.py`
  edit, captions, word check, QA sheet · `scripts/rank_hooks.py` hook ranking from the connector's numbers
- `references/plan.md` plan.json and launch.json formats · `references/meta-connector.md` connecting Meta's
  connector, getting the videos in, creating and switching on the stack, results
- `fonts/` Inter Tight (SIL Open Font License, `fonts/OFL.txt`)

---
Built by [@tenfoldmarc](https://instagram.com/tenfoldmarc). Follow for daily AI automation builds. Real systems, not theory.
