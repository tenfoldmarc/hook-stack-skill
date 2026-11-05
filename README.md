# Hook Stack
### A Claude Code Skill by [@tenfoldmarc](https://www.instagram.com/tenfoldmarc)

The Claude way to scale your ads. Everybody knows that to scale your ads you have to test more video creatives, and
making dozens of videos used to be a huge pain. Now you record ONE body and a bunch of different hooks, drop the
clips on your computer, and tell Claude "edit and launch them". Claude edits every hook onto your body, shows you a
launch plan, and once you approve, launches every one of them as its own Facebook + Instagram ad. 12 hooks = 12 new
video ads, without opening an editor or Ads Manager.

---

## What It Does

1. **Finds your clips.** The batch you just AirDropped (or any files or folder you point it to).
2. **Sorts them.** Listens to every clip and works out which one is the body and which ones are hooks, and picks the
   clean take when you said a line twice.
3. **Edits every ad.** Hook + body, dead air cut, vertical 9:16, burned-in captions (the word being said lights up),
   a native-looking text hook on top for the first seconds, audio levelled for social.
4. **Checks its own work.** Re-listens to every cut and flags a clipped word or a restart before you ever see it.
5. **Shows you the launch plan.** Every hook, the copy, the audience, the daily budget. Nothing is uploaded and no
   money moves until you say approve.
6. **Launches them all.** Uploads the videos, creates the campaign, ad set and every ad, and switches them on. Or
   adds them to an ad set you already run.
7. **Tells you which hook won.** `/hook-stack results` ranks every hook by hook rate (how many people stopped
   scrolling), click rate and cost per result, so you know what to record next.

---

## Requirements

- A Mac, Windows or Linux computer (built and tested on a Mac)
- [Claude Desktop](https://claude.ai/download) or [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
- ffmpeg and Python 3.11 to 3.14 (the skill checks and tells you the one line to install anything missing)
- To launch: a Meta ad account, a Facebook Page (and Instagram account, if you run ads there), and Meta's official
  **Meta Ads connector** (free; you log in with Facebook, no developer app or keys). Editing works without it.

Don't worry about connecting these manually. The skill walks you through everything on first run.

---

## Install

No terminal needed.

### Step 1: Open Claude

Open the Claude Desktop app (or Claude Code, if you already use it).

### Step 2: Paste this message

Copy-paste this into the chat and hit Enter:

```
Install this skill for me: https://github.com/tenfoldmarc/hook-stack-skill
```

Claude downloads the skill into your skills folder and tells you when it's ready. Takes a few seconds.

### Step 3: Run the skill

Type:

```
/hook-stack
```

Hit Enter. On your first run, it sets itself up (about 2 minutes) and asks a few quick questions: your landing
page, your goal, your daily budget and countries.

<details>
<summary>Prefer the terminal? Manual install</summary>

Open Terminal (Mac: `Command + Space`, type Terminal. Windows: `Win + R`, type cmd). Paste this one line and hit Enter:

```bash
git clone https://github.com/tenfoldmarc/hook-stack-skill ~/.claude/skills/hook-stack
```

Then type `claude` to open Claude Code and run `/hook-stack`.
</details>

---

## Usage

**Record.** One body (your pitch, 20 to 60 seconds, ending with what to do next) and as many hooks as you want (the
first 3 to 6 seconds, each grabbing attention a different way). Separate clips are easiest, but a few hooks in one
clip works too.

**Edit and launch:**
```
/hook-stack
```
"I just AirDropped a body and 12 hooks, edit and launch them." Claude edits all 12, sends you a few to watch, and
shows the launch plan. Say approve and they go live.

**Just the edits (no Meta needed):**
```
/hook-stack edit
```

**Which hook won:**
```
/hook-stack results
```
Run it after about 3 days. Keep the winners, cut the losers, and record your next hooks in the style of the winner.

**Good to know**
- Every ad gets the same copy and the same body, so the hook is the only thing being tested.
- New ads sit "In review" at Meta for minutes to a few hours. That's normal.
- Nothing is ever deleted, and nothing is launched or changed without your OK.
- Everything on Meta goes through Meta's own connector, logged in as you. The skill stores no passwords or keys.
- Video ads through Meta's connector are still rolling out to accounts. If yours can't upload the videos yet, the
  skill asks you to drag the finished ads into Meta's media library once (about a minute) and does the rest.

---

## Updating

Paste this into Claude:

```
Update the hook-stack skill from https://github.com/tenfoldmarc/hook-stack-skill
```

Or in Terminal: `cd ~/.claude/skills/hook-stack && git pull`

---

## Built By

[@tenfoldmarc](https://www.instagram.com/tenfoldmarc). Follow for daily AI automation walkthroughs. Real systems, not
theory.

Captions use Inter Tight by The Inter Project Authors, under the SIL Open Font License (`fonts/OFL.txt`).
