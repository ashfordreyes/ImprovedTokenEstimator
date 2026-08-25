A maintained version of Anthropic's token estimator Jupyter notebook.

**[Open it in Colab.](https://colab.research.google.com/github/ashfordreyes/ImprovedTokenEstimator/blob/main/improvedClaudeTokenEstimator.ipynb)** That link always opens the latest version.

The context feature is in: you can paste the conversation so far alongside the prompt you want to add, and the notebook prices the prompt as the next turn of a real conversation rather than in a vacuum. Because the Messages API is stateless, every prior turn is resent and re-billed on every request, so it also shows how much of each turn is just re-sending context, projects the cost of the next N turns as the conversation grows, and estimates what prompt caching would save.

## How it stays up to date

Colab has no version control, and no API that lets a running notebook rewrite its own cells — so a notebook that keeps its logic *in* its cells can never update itself. This one doesn't keep it there.

The estimator lives in a pip-installable package, [`tce-library`](https://github.com/ashfordreyes/tce-library), and the setup cell installs it straight from GitHub:

```python
!pip install -q git+https://github.com/ashfordreyes/tce-library@main
```

```python
import tcelibrary as tce

client = tce.connect()
tce.status()
```

A fresh Colab runtime is a clean VM, so that install clones `main` every session and you get the newest commit automatically. Fix a rate in the library and every notebook picks it up next time it runs — nobody copies cells between tabs. `tce.status()` reports which commit you're on and whether it's behind.

The cells that are left hold only *your* input: the prompt, the context, the system prompt, and the knobs.

Updating **mid-session** is the one case that needs a nudge — pip won't reinstall a version it already has, and Python holds the old module in memory. `tce.status()` prints the exact incantation when it notices you're behind.

## CI

`notebook-check.yml` runs `tools/check_notebook.py` in two jobs, split by what they depend on.

**`notebook`** needs nothing outside this repo, so nothing outside this repo can stop it running. It fails if a code cell stops parsing as Python, or if an Anthropic API key turns up in a cell source or a committed output.

**`drift`** installs `tcelibrary` from `main` and fails if the notebook calls a `tce.*` name the library no longer provides. The setup cell tracks `main` with no release in between, so this is what catches a rename before someone hits it in Colab. It also runs weekly, since the library can drift without this repo being touched.

While `tce-library` is private — or before the package reaches its `main` — the install can't succeed, so `drift` reports a warning instead of a red X rather than blocking the repo on something it can't reach. It starts enforcing on its own once the library installs, with no edit here.

`--skip-drift` narrows the check to the dependency-free half. It is not a way to silence a disagreement between the notebook and an installed library: with `tcelibrary` present, the full check is what runs, and it still fails on a leaked key or a syntax error either way.

## Still on the list

Supporting other AI providers.
