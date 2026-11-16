// Дашборд: обновляем таблицу каждые 5 секунд
const REFRESH_MS = 5000;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function badge(kind, text, title) {
  const titleAttr = title ? ` title="${escapeHtml(title)}"` : "";
  return `<span class="badge ${kind}"${titleAttr}><i class="dot"></i>${text}</span>`;
}

function statusBadge(target) {
  if (!target.enabled) {
    return badge("off", "выключена");
  }
  const last = target.last_check;
  if (!last) {
    return badge("unknown", "нет данных");
  }
  if (last.ok) {
    return badge("ok", "работает");
  }
  return badge("fail", "проблема", last.error || "проверка не прошла");
}

function formatLatency(value) {
  if (value === null || value === undefined) {
    return "—";
  }
  return value < 1 ? "&lt; 1 мс" : `${value} мс`;
}

function formatUptime(value) {
  if (value === null || value === undefined) {
    return '<span class="muted">—</span>';
  }
  let kind = "uptime-good";
  if (value < 90) {
    kind = "uptime-bad";
  } else if (value < 99) {
    kind = "uptime-warn";
  }
  return `<span class="${kind}">${value} %</span>`;
}

function formatFull(isoString) {
  return new Date(isoString).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatAgo(isoString) {
  const seconds = Math.round((Date.now() - new Date(isoString).getTime()) / 1000);
  if (seconds < 5) {
    return "только что";
  }
  if (seconds < 60) {
    return `${seconds} с назад`;
  }
  if (seconds < 3600) {
    return `${Math.round(seconds / 60)} мин назад`;
  }
  if (seconds < 86400) {
    return `${Math.round(seconds / 3600)} ч назад`;
  }
  return `${Math.round(seconds / 86400)} дн назад`;
}

function lastCheckCell(last) {
  if (!last) {
    return '<span class="muted">—</span>';
  }
  return `<time datetime="${last.checked_at}" title="${formatFull(last.checked_at)}">${formatAgo(last.checked_at)}</time>`;
}

function renderRows(targets) {
  const rows = targets
    .map((target) => {
      const last = target.last_check;
      return `<tr>
        <td><a href="/targets/${target.id}">${escapeHtml(target.name)}</a></td>
        <td class="hide-sm">${escapeHtml(target.type)}</td>
        <td>${statusBadge(target)}</td>
        <td>${last ? formatLatency(last.latency_ms) : "—"}</td>
        <td>${formatUptime(target.uptime_24h)}</td>
        <td class="hide-sm">${target.checks_24h}</td>
        <td>${lastCheckCell(last)}</td>
      </tr>`;
    })
    .join("");

  document.getElementById("rows").innerHTML = rows;
  document.getElementById("table-wrap").classList.toggle("hidden", targets.length === 0);
  document.getElementById("empty").classList.toggle("hidden", targets.length > 0);
}

async function refresh() {
  const updated = document.getElementById("updated");
  try {
    const response = await fetch("/api/status");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    renderRows(await response.json());
    updated.classList.remove("error-text");
    updated.textContent = `обновлено ${new Date().toLocaleTimeString("ru-RU")}`;
  } catch (error) {
    updated.classList.add("error-text");
    updated.textContent = "нет связи с сервером";
  }
}

refresh();
setInterval(refresh, REFRESH_MS);
