# Data

This folder is gitignored — nothing here is committed. Re-download sources using
the commands below.

## `raw/`

Exactly what you downloaded, untouched. One subfolder per source, e.g.:

```
data/raw/kubernetes-docs/
data/raw/aws-whitepapers/
data/raw/stackoverflow-dump/
```

Never hand-edit files in here — if a file is broken/corrupt, that's a real scenario
your `ingest/pipeline.py` needs to detect and log, not something you fix by hand.

Quick way to pull the recommended starter combo:

```bash
# Kubernetes docs (markdown)
git clone --depth 1 --filter=blob:none --sparse https://github.com/kubernetes/website.git /tmp/k8s-website
cd /tmp/k8s-website && git sparse-checkout set content/en/docs
mv content/en/docs ../../data/raw/kubernetes-docs   # adjust path as needed

# AWS whitepapers (PDF) — download 3-5 manually from
# https://aws.amazon.com/whitepapers/ into data/raw/aws-whitepapers/

# Stack Exchange Q&A dump — grab one small tag-specific archive from
# https://archive.org/details/stackexchange (e.g. docker.stackexchange.com)
# and extract into data/raw/stackoverflow-dump/
```

## `processed/`

Left empty. This is where `ingest/pipeline.py` writes cleaned, chunked `Document`
objects (as JSONL) — the thing that actually gets embedded. Don't put files here
by hand.
