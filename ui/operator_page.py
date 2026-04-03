"""Static HTML for the PolyBot operator control surface."""

from __future__ import annotations

import html

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>__TITLE__</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #07111f;
      --panel: rgba(8, 20, 38, 0.88);
      --panel-border: rgba(124, 186, 255, 0.22);
      --text: #e8f1ff;
      --muted: #8ca8c7;
      --accent: #63c7ff;
      --danger: #ff7b7b;
      --success: #63f0b5;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Segoe UI", "Aptos", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top right, rgba(99, 199, 255, 0.18), transparent 32%),
        linear-gradient(160deg, #07111f 0%, #0c1a2f 52%, #06101d 100%);
    }
    main {
      width: min(1100px, calc(100vw - 32px));
      margin: 24px auto;
      display: grid;
      gap: 16px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--panel-border);
      border-radius: 18px;
      padding: 18px;
      backdrop-filter: blur(14px);
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.25);
    }
    .hero { display: grid; gap: 8px; }
    h1, h2 { margin: 0; }
    p { margin: 0; color: var(--muted); }
    .toolbar {
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      align-items: end;
    }
    label { display: grid; gap: 6px; font-size: 0.92rem; color: var(--muted); }
    input {
      width: 100%;
      border: 1px solid rgba(140, 168, 199, 0.28);
      border-radius: 12px;
      padding: 10px 12px;
      background: rgba(4, 10, 19, 0.75);
      color: var(--text);
    }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; }
    button {
      border: 0;
      border-radius: 999px;
      padding: 11px 15px;
      font-weight: 600;
      background: linear-gradient(135deg, #1d7cf0, var(--accent));
      color: #05111f;
      cursor: pointer;
    }
    button[data-kind="danger"] { background: linear-gradient(135deg, #ff9b7b, var(--danger)); }
    button[data-kind="neutral"] { background: linear-gradient(135deg, #7ca9d8, #d4e3f5); }
    pre {
      margin: 0;
      padding: 16px;
      border-radius: 14px;
      background: rgba(4, 10, 19, 0.88);
      overflow: auto;
      font-size: 0.86rem;
      line-height: 1.45;
    }
    #result.ok { color: var(--success); }
    #result.err { color: var(--danger); }
  </style>
</head>
<body>
  <main>
    <section class="panel hero">
      <h1>__TITLE__</h1>
      <p>Local operator surface for monitoring PolyBot and running guarded runtime actions.</p>
    </section>

    <section class="panel toolbar">
      <label>
        Operator token
        <input id="token" type="password" placeholder="Required for POST actions" />
      </label>
      <div class="actions">
        <button data-kind="neutral" onclick="refreshStatus()">Refresh Status</button>
        <button data-kind="danger" onclick="runAction('/api/actions/trading/pause', { reason: 'manual operator pause' })">Pause Trading</button>
        <button data-kind="neutral" onclick="runAction('/api/actions/trading/resume')">Resume Trading</button>
        <button onclick="runAction('/api/actions/reconciliation/start')">Start Reconciliation</button>
        <button data-kind="neutral" onclick="runAction('/api/actions/reconciliation/stop')">Stop Reconciliation</button>
        <button data-kind="danger" onclick="runAction('/api/actions/cancel-all')">Cancel All Orders</button>
      </div>
    </section>

    <section class="panel hero">
      <h2>Action Result</h2>
      <p id="result">No action yet.</p>
    </section>

    <section class="panel hero">
      <h2>Runtime Snapshot</h2>
      <pre id="status">Loading...</pre>
    </section>
  </main>

  <script>
    async function refreshStatus() {
      const response = await fetch('/api/status');
      const payload = await response.json();
      document.getElementById('status').textContent = JSON.stringify(payload, null, 2);
    }

    async function runAction(path, payload = {}) {
      const token = document.getElementById('token').value;
      const resultNode = document.getElementById('result');
      resultNode.className = '';

      const response = await fetch(path, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-PolyBot-Operator-Token': token,
        },
        body: JSON.stringify(payload)
      });

      const payload = await response.json();
      resultNode.textContent = payload.message || JSON.stringify(payload);
      resultNode.className = response.ok && payload.success !== false ? 'ok' : 'err';
      await refreshStatus();
    }

    refreshStatus();
    setInterval(refreshStatus, 3000);
  </script>
</body>
</html>
"""


def render_operator_page(title: str = "PolyBot Operator Console") -> str:
    """Return the static operator console HTML."""
    return _HTML_TEMPLATE.replace("__TITLE__", html.escape(title))
