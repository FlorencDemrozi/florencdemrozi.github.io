# Florenc Demrozi — Personal Academic Website

Jekyll-based personal academic website. All content lives in **`_data/cv.yml`** and **`_data/publications.yml`** — no HTML editing required.

## Quick Start (Local Development)

### Prerequisites
- **Ruby ≥ 3.0** — [ruby-lang.org](https://www.ruby-lang.org/en/downloads/)
- **Bundler** — `gem install bundler`
- **Python ≥ 3.9** (for the publication fetcher) — [python.org](https://www.python.org/)

### macOS / Linux
```bash
# 1. Clone and enter project
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO

# 2. Install Ruby gems
bundle install

# 3. Start local server
bundle exec jekyll serve

# 4. Open browser at http://localhost:4000
```

### Windows
```bash
# Install Ruby via RubyInstaller (https://rubyinstaller.org) — choose "Ruby+Devkit"
# Then in a terminal:
bundle install
bundle exec jekyll serve --livereload
```

The site rebuilds automatically when you save a file. Refresh the browser to see changes.

---

## Project Structure

```
fd-jekyll/
├── _config.yml              ← Site-wide settings (title, URL, plugins)
├── Gemfile                  ← Ruby dependencies
│
├── _data/
│   ├── cv.yml               ← ALL personal data (bio, positions, teaching…)
│   └── publications.yml     ← Publication list (auto-updated weekly)
│
├── _layouts/
│   ├── default.html         ← Base HTML shell (nav + footer)
│   └── page.html            ← Inner page wrapper (hero + content)
│
├── _includes/
│   ├── nav.html             ← Navigation bar (reads from _data/cv.yml)
│   ├── footer.html          ← Footer
│   └── icon.html            ← SVG icon helper
│
├── _pages/
│   ├── bio.html             ← Biography page
│   ├── projects.html        ← Projects & datasets
│   ├── network.html         ← Collaboration map & co-author network
│   ├── publications.html    ← Publications page (filterable)
│   ├── activities.html      ← Teaching, supervision, service
│   └── contact.html         ← Contact & social links
│
├── index.html               ← Homepage
│
├── assets/
│   ├── css/main.css         ← All styles
│   ├── js/main.js           ← Filter, mobile nav, colour theme switch
│   ├── js/collab.js         ← Collaboration map & network (d3)
│   └── img/
│       └── florenc-demrozi.jpg  ← Place your photo here
│       └── files/
│           └── CV_Demrozi.pdf   ← Place your CV PDF here
│
├── scripts/
│   ├── fetch_publications.py    ← OpenAlex updater (weekly)
│   └── collab.py                ← Builds collaboration data
│
└── .github/workflows/
    ├── deploy.yml               ← Auto-deploy on push to main
    └── update_publications.yml  ← Weekly OpenAlex fetch (Mon 06:00 UTC)
```

---

## Updating Content

**All content is in `_data/cv.yml`**. Edit that file and run `bundle exec jekyll serve` to preview.

| What to change | Where in cv.yml |
|---|---|
| Name, email, ORCID | `personal:` |
| Profile links (Scholar, LinkedIn…) | `personal.profiles:` |
| Summary paragraph | `summary:` |
| Research interests | `research_interests:` |
| Employment positions | `employment:` |
| Education | `education:` |
| Visiting experiences | `visiting:` |
| Current teaching | `teaching_current:` |
| Past teaching | `teaching_past:` |
| Awards & competitions | `awards:` |
| Funded projects | `projects:` |
| Journal/conference chair roles | `service.conference_chair:` |
| Journal reviewer list | `service.journal_reviewer:` |
| Ph.D. thesis committees | `service.phd_committees:` |
| Referees | `referees:` |

Publications are in **`_data/publications.yml`** and are auto-updated weekly. You can also edit them manually.

---

## Adding Your Photo

Place your photo at `assets/img/florenc-demrozi.jpg`. It will appear automatically in the hero section. Recommended: portrait crop, minimum 600×800px.

## Adding Your CV PDF

Place `CV_Demrozi.pdf` at `assets/files/CV_Demrozi.pdf`. The Bio page links to it automatically.

---

## Publications & Collaborations Update

Everything comes from [OpenAlex](https://openalex.org) (free, no API key), using the ORCID.

GitHub Actions runs `scripts/fetch_publications.py --collaborations` every Monday at 06:00 UTC.
It updates `_data/publications.yml` and `_data/collaborations.json` (map, partner institutions,
co-authors, co-author network, citations, h-index), then the site redeploys.
Hand-curated entries (`C`, `J`, `B`, `P`, `T` ids) are never overwritten.
Trigger it manually under **Actions → Update Publications from OpenAlex → Run workflow**,
or run it yourself:

```powershell
pip install pyyaml
python scripts/fetch_publications.py --collaborations
```

Partner cities without coordinates are geocoded once with OpenStreetMap and cached in
`scripts/geo_cache.json`.

### Notes
- Hand-added fields (`award`, `url`) survive every update.
- Papers with more than 50 authors are left out of the collaboration statistics.

---

## GitHub Pages Deployment

### Step 1 — Create repository
Create a new GitHub repository (public or private with Pages enabled).

### Step 2 — Push code
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### Step 3 — Enable GitHub Pages
Go to **Settings → Pages → Source → GitHub Actions**.

The `.github/workflows/deploy.yml` workflow runs automatically on every push and deploys `_site/` to GitHub Pages.

### Step 4 — Custom domain (optional)
Add a `CNAME` file at the repo root:
```
florencdemrozi.com
```
Then in GitHub: **Settings → Pages → Custom domain → florencdemrozi.com**.

DNS records at your registrar:
```
A    @    185.199.108.153
A    @    185.199.109.153
A    @    185.199.110.153
A    @    185.199.111.153
CNAME www  YOUR_USERNAME.github.io
```

Also set `url` in `_config.yml` to your domain.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `bundle install` fails | Make sure Ruby ≥ 3.0 is installed. On macOS use `brew install ruby`. |
| `jekyll serve` gives port error | Use `jekyll serve --port 4001` |
| Photo not showing | Check file is at `assets/img/florenc-demrozi.jpg` (case-sensitive on Linux) |
| Publications not updating | Trigger the OpenAlex workflow in GitHub Actions, or run `scripts/fetch_publications.py --collaborations` |
| Liquid syntax error | Check `_data/cv.yml` for correct YAML indentation (use spaces, not tabs) |
