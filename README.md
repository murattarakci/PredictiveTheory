# Predictive Theory: a lockbox for testing whether findings hold on new data

This repository holds the research tool behind our proposal *Predictive Testing in the Age of AI: A Tool for Separating Generalizable Theory from Noise*, submitted to the *Organization Science* special issue "AI-Enabled Frontiers in Organizational Science."

**Live instance:** https://academic.shinyapps.io/predictivetheorizing/

## Why we built it

A theory should hold on data it has not seen. A relationship that fits one sample and fails on the next has described that sample, not explained anything.

AI makes this harder. An AI agent can run hundreds of regressions in minutes. Ask it to find a significant link between corporate social performance and financial performance, and it will try one measure, then another, add and drop controls, and stop at the first result that clears p < .05. That result may reflect the pattern in the data or just its noise. From the sample alone, nobody can tell.

The field used to catch these results through replication: another team collects new data and tries again. That takes years. AI now produces new findings much faster than anyone can replicate them. We expect this to make two known problems worse: too many fragmented theories, and too many findings that do not replicate.

Our answer is to set new data aside before the first regression runs. We split the data, let the researcher build and choose a model on part of it, and keep the rest locked until the researcher commits. The locked part then shows whether the finding holds.

## What the tool does today

1. **Create a repository.** Sign in, name the project, and upload a dataset (CSV, Excel, Stata, or R).
2. **Choose the split.** Pick a ratio (60-20-20, 70-15-15, or 80-10-10) for training, test, and validation sets. You can name an ID column, such as a firm code, so that all rows of one firm land in the same set. A preview shows the size of each set before you commit.
3. **Download training and test sets.** These are available at once.
4. **Do your analysis.** Build and choose your model using only those two sets.
5. **Upload your write-up.** A PDF or Word file describing the analysis.
6. **Unlock the validation set.** It becomes available only after the write-up is uploaded.

The database records when each dataset and write-up was uploaded. Projects can be private, embargoed, or public. Visitors can download the training and test sets of public projects, and the validation set only after the owner has uploaded a write-up.

### How the split works

- With an ID column, the tool shuffles the unique IDs and assigns each one to a single set, so no firm (or person) appears in two sets.
- Without an ID column, it splits rows at random.
- The random seed is fixed, so the same data and settings give the same split.
- If a file has two columns with the same name, the tool keeps the version with the most non-missing and unique values.
- The interface lets you re-split a project until you upload a write-up. A server-side freeze is planned (see below).

Split logic lives in `utils/split.py`.

### What it does not do yet

- It does not score your model. It hands you the validation data, and you evaluate the model yourself.
- It has no programming interface, so an AI agent cannot use it directly.
- It does not yet keep a full record. Downloads are not logged, a new write-up replaces the old one, and re-splitting overwrites the earlier split.
- The lock is checked in the interface, not on the server. The combined download currently includes the validation set before a write-up exists.
- Every project uses the same random seed, so anyone holding the data can rebuild the split.
- It cannot stop someone who already holds the full dataset from looking. The lock only binds when someone else (a journal, a data provider, or our test harness) holds the full data and you receive only the training and test sets.

## What we are building next

These parts are planned and described in the proposal and its technical appendix.

- **A trustworthy record (first).** Log every upload and download with a fingerprint (SHA-256 hash) of each file. Keep every version of every write-up and split. Check the lock on the server for every download. Give each project its own secret random seed. Store passwords securely. Add tests that try to get the validation set early.

- **A scoring layer.** Instead of releasing the validation data, the tool will score the committed model on it. The score looks at the finding the researcher cares about (for example, the coefficient on social performance), not just how well the model predicts the outcome overall. It reports where that score falls among all reasonable alternative models.
- **A programming interface.** So that a script, an AI agent, or a person can upload data, receive training and test sets, commit a model, and receive a score, with every step logged.
- **Experiments.** We will give AI agents synthetic data, where we know the true answer, and open data from many-analysts studies. Each agent gets an instruction ("find a significant result" or "find the model most likely to hold on new firms") and a cap on how many models it may try. We then score what it commits. We compare the agents' choices with the published choices of the human teams in those studies. Licensed data, such as Compustat, never go to hosted AI models.

## The benchmark

We rebuilt the 2,208 between-firm specifications that Berchicci and King (2022, *Strategic Management Journal*) derived from six well-known studies of corporate social and financial performance, and scored each one on firms held out from estimation. The code and the scores are in [`benchmark/`](benchmark/). Compustat and KLD data are licensed and are not included.

In short: social performance is statistically significant in every return-on-assets specification. On firms the models have not seen, the effect shrinks to about half. For the 50 specifications that predict best, adding social performance does not detectably improve predictions for new firms.

## Run it on your own computer

You need Python 3.11 (3.10 or newer works).

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m db.init_db
python -m db.seed_users
shiny run --reload app --port 8500
```

Then open http://localhost:8500. If you change the database models, delete `db/poc.db` and run the two `db` commands again.

### With Docker

```bash
docker compose up --build
```

Then open http://localhost:8500. The compose file limits the app to 1 GB of memory and 2 CPUs to mimic the hosted setup.

### Optional: keep data in Dropbox

The hosted version stores its database and uploads in Dropbox so they survive restarts. To use this, copy `.env.example` to `.env` and fill in your own Dropbox app details. Never commit `.env`. Without it, the app keeps everything in local folders.

## What is where

| Path | Contents |
|---|---|
| `app.py` | Starts the app |
| `ui_layout.py` | Page layout |
| `server/` | App behavior: sign-in, project creation, uploads, downloads, dialogs |
| `utils/split.py` | Training, test, and validation split |
| `utils/dropbox_*.py` | Optional Dropbox storage |
| `db/` | Database models and setup |
| `paths.py` | Where the app writes files (local or hosted) |
| `Dockerfile`, `docker-compose.yml`, `docker/` | Container setup |

## Authors and contact

Murat Tarakci, Rotterdam School of Management, Erasmus University. Questions and suggestions are welcome through GitHub issues.

## References

Berchicci, L., & King, A. A. (2022). Building knowledge by mapping model uncertainty in six studies of social and financial performance. *Strategic Management Journal*, 43(7), 1319–1346.
