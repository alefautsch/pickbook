# Pickbook — https://github.com/alefautsch/pickbook

set dotenv-load := true

default:
    @just --list

# Install / update dependencies
install:
    uv sync

# Run the Streamlit UI (reloads when you edit Python files)
app:
    uv run streamlit run dynasty_draft/app.py

# Alias for `just app`
run: app

# Use polling file watcher if auto-reload doesn't pick up saves (e.g. some network drives)
app-poll:
    uv run streamlit run dynasty_draft/app.py --server.fileWatcherType poll

# CLI: one-shot draft sync
sync:
    uv run dynasty-draft sync

# CLI: poll Sleeper draft in terminal
watch:
    uv run dynasty-draft watch

# CLI: static strategy notes from war.csv
insights:
    uv run dynasty-draft insights
