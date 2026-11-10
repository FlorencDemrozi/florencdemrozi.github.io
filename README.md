# Florenc Demrozi — Personal Academic Website

Jekyll site published at **https://florencdemrozi.github.io** (repository
`FlorencDemrozi/florencdemrozi.github.io`, branch `main`).

Content lives in data files, so most updates need no HTML editing:

| File | What it holds |
|---|---|
| `_data/cv.yml` | Profile, links, summary, employment, education, teaching, awards, funded projects, service, **news** |
| `_data/projects.yml` | Projects, datasets, lab and tools (Projects page and Home page list) |
| `_data/publications.yml` | Publication list (updated weekly from OpenAlex) |
| `_data/collaborations.json` | Map, partner institutions, co-authors, co-author network (updated weekly from OpenAlex) |

---

## Local preview

Requirements: **Ruby 3.x** with Bundler, and **Python 3.9+** (only for the update script).

```bash
git clone https://github.com/FlorencDemrozi/florencdemrozi.github.io.git
cd florencdemrozi.github.io
bundle install
bundle exec jekyll serve      # open http://localhost:4000
```

On Windows install Ruby with [RubyInstaller](https://rubyinstaller.org) ("Ruby+Devkit").
`Gemfile.lock` lists Linux and macOS builds; on Windows the first `bundle install`
adds the Windows platform to it automatically. Do not commit that change unless you
also check that the GitHub build still passes.

---

## Project structure

```
_config.yml                 Site settings (title, URL, plugins)
_data/                      Content (see table above)
_includes/nav.html          Menu and colour-theme switch
_includes/footer.html       Footer
_includes/icon.html         Icons for profile links
_layouts/default.html       Page shell (fonts, favicon, SEO tags)
_layouts/page.html          Inner-page header
index.html                  Home page
_pages/                     bio, publications, projects, network, activities, contact
assets/css/main.css         All styles (light / dark / paper themes)
assets/js/main.js           Mobile menu, theme switch, publication filter
assets/js/collab.js         Collaboration map and co-author network (d3)
assets/img/                 Photo (florenc-demrozi.jpg original, -640.jpg used on the site), favicons
assets/files/CV_Demrozi.pdf CV linked from the Bio page
scripts/fetch_publications.py  Weekly OpenAlex updater
scripts/telegram_news.py    News updates sent through Telegram
scripts/collab.py           Builds collaborations.json
scripts/geo_cache.json      Cached city coordinates
.github/workflows/          deploy.yml (build + publish), update_publications.yml (weekly update),
                            telegram_news.yml (News from Telegram, every 10 min)
```

---

## Updating content

| What to change | Where |
|---|---|
| Name, title, email, ORCID, photo | `cv.yml` → `personal:` |
| Profile links (Scholar, LinkedIn…) | `cv.yml` → `personal.profiles:` |
| Summary and research interests | `cv.yml` → `summary:`, `research_interests:` |
| News on the Home page | `cv.yml` → `news:` (newest first) |
| Employment, education, visiting | `cv.yml` → `employment:`, `education:`, `visiting:` |
| Teaching | `cv.yml` → `teaching_current:`, `teaching_past:` |
| Awards, funded projects | `cv.yml` → `awards:`, `projects:` |
| Editor, chair, reviewer, committee roles | `cv.yml` → `service:` |
| Projects and datasets | `_data/projects.yml` |
| "Upcoming" chair roles on Home | `index.html` (Upcoming section) |
| UiS supervised students | automatic weekly from NVA (`scripts/fetch_students.py` → `_data/students_nva.yml`); programmes, name spellings and students missing from NVA in `_data/students_uis.yml` |
| Verona supervised students | `_pages/activities.html` |

**Photo:** replace `assets/img/florenc-demrozi.jpg` and make a 640 px copy named
`florenc-demrozi-640.jpg` (that small copy is what the pages load).
**CV:** replace `assets/files/CV_Demrozi.pdf`.

Push to `main` and the site rebuilds in about two minutes.

---

## Publications and collaborations (automatic)

Everything comes from [OpenAlex](https://openalex.org) (free, no API key), using the ORCID.

Every Monday at 06:00 UTC, GitHub Actions runs
`scripts/fetch_publications.py --collaborations`, which:

- adds new papers to `_data/publications.yml` and refreshes auto-generated entries
  (`W…` ids). Hand-curated entries (`C`, `J`, `B`, `P`, `T` ids) are never overwritten,
  only a missing DOI is filled in; hand-added `award` and `url` fields are kept;
- rebuilds `_data/collaborations.json`. The same person under several OpenAlex ids is
  merged by name; papers with more than 50 authors are left out;
- writes files only when something changed. If OpenAlex is unreachable or returns no
  papers, it stops with an error and changes nothing;
- commits the changes and starts the deploy workflow. The run summary lists what changed.

Run it by hand under **Actions → Update Publications from OpenAlex → Run workflow**, or locally:

```bash
pip install pyyaml
python scripts/fetch_publications.py --collaborations
```

To fix a publication permanently, edit it in `publications.yml` and give it a curated id
(for example `J20`), so the updater leaves it alone.

Partner cities without coordinates are geocoded once with OpenStreetMap and cached in
`scripts/geo_cache.json`.

---

## News from Telegram

The Home page News list can be edited by messaging a private Telegram bot.
Every 10 minutes `.github/workflows/telegram_news.yml` runs `scripts/telegram_news.py`,
which reads new messages, edits `news:` in `_data/cv.yml`, commits, redeploys and replies.

| Message | Effect |
|---|---|
| `/news Title \| detail \| https://link \| 2027` | Adds an item, placed by year (newest first). Only the title is required; parts can be in any order; a new line also works as separator; the year defaults to the current year |
| `/list` | Shows the news, numbered |
| `/delete N` | Removes item N |
| `/undo` | Removes the top item |
| `/help` | Shows the commands |

Only messages from the Telegram account in `TELEGRAM_USER_ID` are accepted.

**Setup (once):**
1. In Telegram, message **@BotFather**, send `/newbot`, pick a name; copy the token.
2. Message **@userinfobot** to get your numeric user id.
3. On GitHub: **Settings → Secrets and variables → Actions → New repository secret**:
   `TELEGRAM_BOT_TOKEN` (the token) and `TELEGRAM_USER_ID` (the id).
4. Open your new bot in Telegram and send `/help`. The reply comes within ~10 minutes.

Telegram keeps unread bot messages for 24 hours, so if the workflow is ever disabled for
longer, messages sent in that time are lost; send them again.

---

## Deployment

GitHub Pages is set to **Settings → Pages → Source → GitHub Actions**.
`.github/workflows/deploy.yml` builds the site on every push to `main` (and when the weekly
updater starts it) and publishes `_site/`.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| Change not visible | Wait for the deploy run in **Actions**, then hard-refresh (Ctrl+F5) |
| Weekly update failed | Open the run in **Actions**; the log says whether OpenAlex was unreachable. Nothing is committed on failure, so just run it again later |
| A publication looks wrong | Edit it in `publications.yml` and give it a curated id (see above) |
| `bundle install` fails | Install Ruby 3.x with the Devkit (Windows) or `brew install ruby` (macOS) |
| Port already in use | `bundle exec jekyll serve --port 4001` |
| Liquid / YAML error | Check indentation in the `_data` files (spaces, not tabs) |
