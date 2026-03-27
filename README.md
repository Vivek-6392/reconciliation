# ReconAI — Live Reconciliation Analyst

A payments reconciliation tool that detects 8 types of financial gaps in transaction and settlement data, powered by AI analysis via Groq.

**Live demo →** [reconciliation-tau.vercel.app](https://reconciliation-tau.vercel.app)

---

## What it does

Upload or paste two CSVs — your platform transactions and bank settlements — and ReconAI will:

- Detect 8 gap types algorithmically (client-side, instant)
- Stream an AI analyst report via Groq/LLaMA summarising risk, root causes, and recommended actions
- Show a static reconciliation dashboard with charts and gap breakdowns

---

## Gap types detected

| Gap | Severity |
|-----|----------|
| Next-month settlement | High |
| Rounding differences | Medium |
| Duplicate settlements | Critical |
| Orphan refunds | High |
| Ghost settlements | Critical |
| Late settlements (SLA breach) | Medium |
| Partial settlements | High |
| Velocity anomalies | High |

---

## Project structure

```
├── data/
│   ├── settlements.csv
│   └── transactions.csv
│
├── output/
│   ├── index.html              # Dashboard (entry point)
│   ├── recon_ai_tool.html      # ReconAI live analysis tool
│   ├── server.js               # Express backend (Groq API proxy)
│   ├── package.json
│   ├── package-lock.json
│   ├── report.json
│   ├── report_v2.json
│   └── node_modules/
│
├── src/
│   ├── generate_data.py
│   ├── reconcile.py
│   └── reconcile_v2.py
│
├── tests/
│   └── test_reconciliation.py
│
└── .gitignore
```

---

## Running locally

### 1. Install dependencies

```bash
cd output
npm install
```

### 2. Start the server

```bash
node server.js
```

### 3. Open the frontend

Open `index.html` in your browser, or serve it locally:

```bash
npx serve .
```

Then visit `http://localhost:3000`.

### 4. Enter your Groq API key

Get a free key at [console.groq.com](https://console.groq.com) and paste it into the **Settings** panel inside the ReconAI tool.

---

## Deployment

| Service | Purpose |
|---------|---------|
| Vercel | Hosts the static HTML frontend |
| Railway | Runs the Node.js backend (Groq proxy) |

The frontend calls the Railway backend URL directly. No API key is stored on the server — it is passed from the browser per request and never persisted.

---

## Tech stack

- **Frontend** — Vanilla HTML/CSS/JS, JetBrains Mono, Bricolage Grotesque
- **Backend** — Node.js, Express, groq-sdk
- **AI model** — `llama-3.3-70b-versatile` via Groq
- **Reconciliation engine** — Pure client-side JavaScript
- **Data generation** — Python (`src/generate_data.py`)

---

## Known limitations

1. **Timezone naïvety** — all timestamps treated as UTC; PST/EST transactions may be misclassified to wrong month
2. **Partial settlement batches** — 1:1 transaction matching only; split-capture settlements flagged as duplicates
3. **No FX support** — multi-currency data will generate false positives

---

## License

MIT
