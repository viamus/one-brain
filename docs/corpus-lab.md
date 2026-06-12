# OneBrain Corpus Lab

This runbook prepares a clean local OneBrain lab for large corpus ingestion and graph correlation
experiments.

The lab keeps two paths separate:

- **Training corpus**: used to train the memory classifier. It does not create memories.
- **Knowledge corpus**: ingested into OneBrain so graph correlations and context composition can be
  evaluated.

## 1. Reset Local Knowledge

Preview the reset:

```powershell
.\scripts\onebrain-lab-reset.ps1
```

Apply the reset:

```powershell
.\scripts\onebrain-lab-reset.ps1 -Apply
```

The reset removes:

- `onebrain_postgres_data`
- `onebrain_qdrant_storage`
- `onebrain_job_status`

The reset preserves:

- `onebrain_ml_artifacts`

## 2. Clone Candidate Corpora

Clone or update repositories into `C:\DoxieOS\training-corpora` for host-side classifier
experiments. The default Docker stack intentionally mounts only the private Doxie catalog.

```powershell
.\scripts\onebrain-lab-clone-corpus.ps1 `
  -RepoUrl https://github.com/ciembor/agent-rules-books.git `
  -Update
```

For catalog repositories such as `VoltAgent/awesome-agent-skills`, first clone the catalog and then
expand its GitHub links into a controlled batch of real repositories:

```powershell
.\scripts\onebrain-lab-clone-corpus.ps1 `
  -RepoUrl https://github.com/VoltAgent/awesome-agent-skills.git `
  -Update

.\scripts\onebrain-lab-expand-awesome-skills.ps1 `
  -MaxRepos 20 `
  -Update
```

Preview the expansion without cloning:

```powershell
.\scripts\onebrain-lab-expand-awesome-skills.ps1 `
  -MaxRepos 20 `
  -DryRun
```

## 3. Train The Classifier From Corpus

Use external repositories as training data without ingesting them into OneBrain:

```powershell
uv run onebrain-jobs train_memory_classifier `
  --training-docs C:\DoxieOS\training-corpora\agent-rules-books `
  --training-docs-source-ref-prefix github://ciembor/agent-rules-books `
  --model-out .\artifacts\memory-classifier.json `
  --max-examples-per-type 80 `
  --folds 3 `
  --json
```

Train with both the rule-book corpus and the expanded skill corpus:

```powershell
uv run onebrain-jobs train_memory_classifier `
  --training-docs C:\DoxieOS\training-corpora\agent-rules-books `
  --training-docs-source-ref-prefix github://ciembor/agent-rules-books `
  --training-docs C:\DoxieOS\training-corpora\awesome-agent-skills-expanded `
  --training-docs-source-ref-prefix github://VoltAgent/awesome-agent-skills-expanded `
  --model-out .\artifacts\memory-classifier.json `
  --max-examples-per-type 160 `
  --folds 3 `
  --json
```

## 4. Ingest Knowledge Corpus

Only ingest repositories that should become OneBrain memories. Give each corpus explicit scope and
source metadata.

For the private Doxie catalog mounted by Docker:

```powershell
$env:ONEBRAIN_IMPORT_SCOPE_JSON = '{"organization":"abinbev","catalog":"private-engineering-catalog","source":"github-private-catalog","batch":"github-private-catalog-only-001"}'

docker compose run --rm -e ONEBRAIN_API_KEY -e ONEBRAIN_IMPORT_SCOPE_JSON onebrain-jobs `
  onebrain-local-import `
  --docs /mnt/github-private-catalog `
  --api-path /mnt/github-private-catalog `
  --api-url http://onebrain-api:8000/api/v1 `
  --source-type github-private-catalog `
  --source-ref-prefix catalog://github-private-catalog `
  --include-extension .md `
  --include-extension .json `
  --include-extension .yaml `
  --include-extension .yml `
  --exclude-dir .git `
  --exclude-dir .vs `
  --exclude-dir run-inputs `
  --exclude-dir index `
  --exclude-dir build-check-release `
  --exclude-examples `
  --skip-codex
```

```powershell
$env:ONEBRAIN_IMPORT_SCOPE_JSON = '{"lab":"corpus-correlation","source":"github","repo":"ciembor/agent-rules-books","batch":"baseline-001"}'

uv run onebrain-local-import `
  --docs C:\DoxieOS\training-corpora\agent-rules-books `
  --api-url http://localhost:8088/api/v1 `
  --source-type github-corpus `
  --source-ref-prefix github://ciembor/agent-rules-books `
  --skip-codex
```

Use `--analyze-only` first when checking a new corpus:

```powershell
uv run onebrain-local-import `
  --docs C:\DoxieOS\training-corpora\agent-rules-books `
  --api-url http://localhost:8088/api/v1 `
  --source-type github-corpus `
  --source-ref-prefix github://ciembor/agent-rules-books `
  --skip-codex `
  --analyze-only
```

Analyze an expanded batch before ingestion:

```powershell
$env:ONEBRAIN_IMPORT_SCOPE_JSON = '{"lab":"corpus-correlation","source":"github","repo":"VoltAgent/awesome-agent-skills-expanded","batch":"skills-001"}'

uv run onebrain-local-import `
  --docs C:\DoxieOS\training-corpora\awesome-agent-skills-expanded `
  --api-url http://localhost:8088/api/v1 `
  --source-type github-corpus `
  --source-ref-prefix github://VoltAgent/awesome-agent-skills-expanded `
  --include-extension .md `
  --max-files 1000 `
  --skip-codex `
  --analyze-only
```

Start with Markdown for catalog expansions. The raw expanded repositories contain a lot of
operational files (`.github`, JSON/YAML configs, changelogs, generated metadata) that are useful for
repo development but noisy for OneBrain knowledge correlation.

## 5. Materialize Graph Aggregates

```powershell
docker compose run --rm onebrain-jobs `
  onebrain-jobs aggregate_graph_memories `
  --scope-json '{"lab":"corpus-correlation"}' `
  --grouping-limit 25 `
  --correlation-limit 1000
```

## 6. Inspect

Open:

```text
http://localhost:8089/graph
```

Useful checks after each batch:

- memory count by type
- source distribution by repo
- graph grouping opportunities
- noisy generic `context` memories
- duplicated source refs
- correlations that connect unrelated repos
