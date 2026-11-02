# SEO + AEO Site Audit → Content Strategy (n8n workflow)

You type in a brand's website. The workflow checks the site and AI writes an audit and a content plan. You correct the AI, and you get a report page you can show the client.

```
Brand inputs → site checks (code) → page checks (code) → AI Auditor → YOU review → AI Strategist → AI Translator → Report
```

The big idea, and a good line for your video: **code collects facts, AI makes judgments, a human makes the final call.** Code can't make things up, so all the facts come from code. AI is good at ranking and writing, so it gets those jobs. You catch what the AI gets wrong.

Tested on n8n 2.45.7.

---

## Step 0: Get n8n (pick one)

**Option A, easiest:** sign up for an n8n Cloud free trial at n8n.io. Nothing to install.

**Option B, free on your laptop:**
1. Install Node.js **version 24 or newer** from nodejs.org. Current n8n will not start on older Node.
2. Open a terminal and run:

```bash
npx n8n
```

3. Open http://localhost:5678 in your browser and create a local account.

**Option C, with Docker:**

```bash
docker run -it --rm -p 5678:5678 -v n8n_data:/home/node/.n8n docker.n8n.io/n8nio/n8n
```

---

## Step 1: Get two free keys

1. **Gemini API key (required).** Go to aistudio.google.com, click **Get API key**, then **Create API key**. Copy it.
   - Gemini's free tier may use your prompts to improve Google's products. Use public website data only, nothing confidential from a client.
2. **PageSpeed API key (recommended).** Go to developers.google.com/speed/docs/insights/v5/get-started and click **Get a Key**. Without a key, the speed check often fails with "quota exceeded". The workflow keeps going, but the report won't have speed data.

---

## Step 2: Import the workflow

1. Download `workflow.json` from this folder. On GitHub, open the file and click the **Download raw file** button.
2. In n8n, click **Create workflow**.
3. Open the **⋯** menu (top right), choose **Import from File…** and pick `workflow.json`.

You'll see 4 coloured boxes (Parts 1–4) and a yellow **START HERE** note.

---

## Step 3: Connect Gemini (one time)

1. Double-click **Gemini (Auditor)** (the small node under "12. AI Auditor").
2. Under **Credential**, choose **Create new credential**, paste your Gemini key and click **Save**. Leave "Host" as it is.
3. Open **Gemini (Strategist)** and **Gemini (Translator)** and pick the same credential.
4. **Model:** leave the default, or open the list and pick the newest **Flash** model. If you later get "model not found", pick a different model from the list.

> Want Claude or ChatGPT instead? Delete a Gemini node, click the **+** under "Model" on that AI step and choose *Anthropic Chat Model* or *OpenAI Chat Model*. These need a paid key. Nothing else changes, and that model-swap is worth showing in the video.

---

## Step 4: Fill in the brand

Double-click **1. Brand Inputs (EDIT ME)** and replace the example values:

| Field | What to type | Example |
|---|---|---|
| `siteUrl` | The brand's website | `https://www.brand.com` |
| `brandName` | Brand name | `Smile Dental Care` |
| `businessType` | What they are | `dental clinic chain` |
| `market` | Where they sell | `Chennai, India` |
| `businessGoal` | What the owner wants | `More appointment bookings` |
| `competitors` | 2–3 competitor websites, comma separated | `a.com, b.com` |
| `customerQuestions` | 5–8 real questions, **one per line** | `How much does a root canal cost in Chennai?` |
| `aiVisibilityNotes` | What AI tools say today (see below) | `ChatGPT named X and Y, not us...` |
| `maxPages` | How many pages to check | `25` (max 100) |
| `pagespeedApiKey` | Your PageSpeed key | (paste it) |

**Where to find customer questions:** Google's "People also ask" box, Reddit, the brand's Google reviews, and competitor FAQ pages.

**How to fill `aiVisibilityNotes` (about 10 minutes, by hand):**
Ask each customer question in ChatGPT, Perplexity and Google (look at the AI Overview at the top). Write down which brands they mention and whether your brand appears. AI answers change from one try to the next, so ask each one twice. Doing this by hand is a constraint worth naming in the video.

---

## Step 5: Run it

Click **Execute workflow** at the bottom of the canvas. Each node gets a green tick as it finishes. A run takes 1–3 minutes.

Click any node to see what it found. That's the best part to show on video.

---

## Step 6: Your judgment (the human checkpoint)

1. Click **12. AI Auditor** and read what it says.
2. Find something you disagree with. There is usually something. For example, the AI marks "missing meta descriptions" as important, but Google rewrites most of them anyway.
3. Double-click **13. Your Review (Human Checkpoint)** and write your correction in `reviewerNotes`.
4. Run the workflow again. The Strategist and Translator treat your notes as more important than the AI's audit.

Tip: in node 12's output, click the **pin** icon. The audit then stays the same between runs, and only your corrections change the plan.

Until you write notes, the report says **"human review not done yet"**. It won't claim a review that didn't happen.

---

## Step 7: Get the report

- Open **19. Report File (download me)** and click **Download**, then open the `.html` file in your browser. It contains the owner summary, the audit, your notes, the content plan, and the raw facts as proof.
- **Page Table (CSV download)** gives you every page's facts as a spreadsheet.

---

## What each node does (cheat sheet for your video)

| Node | What it does | What to say |
|---|---|---|
| 1. Brand Inputs | Your client brief | "Everything brand-specific lives here, so the same flow works for any client." |
| 2. Prepare Inputs | Cleans up what you typed | |
| 3. robots.txt | Who is allowed to read the site | "I check AI crawlers separately: blocking GPTBot (training) is a choice, blocking OAI-SearchBot hides you from ChatGPT search." |
| 4. sitemap.xml | The list of pages | |
| 5. llms.txt | Checked, but **info only** | "No major AI engine has confirmed it uses llms.txt, so I don't score it. Signal vs noise." |
| 6. Homepage | Its menu links = pages the brand cares about | |
| 7. PageSpeed | Mobile speed, real-user data first | "Google ranks on real-user Core Web Vitals, not the lab score. Speed is a tie-breaker." |
| 8. Build Page List | Picks which pages to check | "It's a sample, not a full crawl. For a full crawl I'd use Screaming Frog." |
| 9. Fetch Pages | Downloads each page politely (5 at a time) | |
| 10. Extract Page Signals | Title, H1, words, noindex, canonical, schema, question headings, alt text | "Code, not AI. Code can't make things up." |
| 11. Rule-Based Checks | Turns facts into issues with a starting severity, plus a list of things deliberately ignored | "Meta keywords, keyword density and Domain Authority aren't in here on purpose." |
| 12. AI Auditor | Re-ranks issues, names the noise, says what it couldn't check | |
| 13. Your Review | **You** correct the AI | "This is where my judgment steps in." |
| 14. AI Strategist | Audit + customer questions → fixes, answer pages, topic clusters, 90-day plan | "Every recommendation has to trace back to a finding or a real question." |
| 15. AI Translator | Rewrites it for an owner who doesn't speak SEO | This covers the 20% client-communication score. |
| 16–19 | Builds the report page | |

---

## Assumptions and constraints (say these out loud)

- **Sample, not full crawl.** It checks up to `maxPages` pages.
- **No Google Search Console access**, so no real traffic, clicks or ranking data. This is the biggest gap.
- **No paid keyword tool**, so no search volumes. The AI is told not to guess numbers.
- **The AI visibility check is manual**, and AI answers change every time.
- **JavaScript-heavy sites:** the workflow reads raw HTML, like most AI crawlers do. Google can render JavaScript, so a page flagged "loads with JavaScript" may still rank on Google but be invisible to AI tools.
- **Some sites block bots** (for example behind Cloudflare). You'll see status 403 or 0 words. Pick another brand, or crawl with Screaming Frog.
- **AI can be wrong.** That's why node 13 exists.

## What I'd build next with more time

- Make the human checkpoint a real pause: n8n's "send and wait for approval" over Gmail or Slack, so the client lead approves before the strategy runs.
- Pull real data from the Google Search Console API.
- Automate the AI visibility check through the Perplexity or OpenAI APIs, run it weekly, and track how often the brand is named.
- Run the same flow on each competitor and compare.
- Feed in a full Screaming Frog crawl export instead of the sample.

## Troubleshooting

| Problem | Fix |
|---|---|
| Every page shows status 403 or 0 words | The site blocks bots. Try another brand. |
| "PageSpeed check failed: Quota exceeded" | Add a PageSpeed key in node 1. |
| Gemini says "model not found" | Pick another model in the Gemini node's list. |
| Gemini error 429 | Free-tier rate limit. Wait a minute and run again. |
| "Credentials not found" | Pick your Gemini credential in all 3 Gemini nodes. |
| Node 2 error "Please type the website address" | Fill in `siteUrl` in node 1. |
