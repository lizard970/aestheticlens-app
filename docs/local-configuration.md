# Local-only configuration

The public repository contains application source, tests, migrations and public technical documentation.
Private product reports, handoff notes, launch shortcuts and model policy JSON files are intentionally not distributed.

To run the configured semantic provider or its configuration-dependent tests, supply these files locally from your authorized private source:

- `backend/config/semantic_prompt.json`
- `backend/config/semantic_prompt_zero_shot.json`
- `backend/config/semantic_reasoning_boundary.json`
- `backend/config/style_vocabulary.json`

Keep their existing schemas and paths. They are ignored by Git; do not force-add them. Credentials remain in local environment variables / `.env`, using `.env.example` as a template. No runtime fallback or analysis behavior has been changed.

Public layout: `app/`, `components/`, `hooks/`, `lib/`, `public/` for the frontend; `backend/` for Python source, tests and migrations; `docs/` for technical documentation. Local datasets and generated build artifacts are not public project content.
