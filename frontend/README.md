# IDK Clips — frontend

Next.js (App Router) + React + TypeScript + Tailwind CSS. See the main
[README](../README.md) for full setup instructions.

| Command | What it does |
|---|---|
| `npm run dev` | Development server on http://localhost:3000 |
| `npm run build` / `npm start` | Production build and server |
| `npm run lint` | ESLint |
| `npm run typecheck` | Route type generation + `tsc --noEmit` |

Configuration: copy `.env.example` to `.env.local` and set `NEXT_PUBLIC_API_URL`
if the backend is not on `http://127.0.0.1:8000`.

Structure:

- `src/app/` — routes (`page.tsx` landing page, `(app)/` dashboard area)
- `src/components/` — UI, layout and feature components
- `src/lib/` — API client, types, hooks and helpers
