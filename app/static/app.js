// Обновление таблицы целей каждые 5 секунд
const REFRESH_MS = 5000;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function statusBadge(target) {
  if (!target.enabled) {
    return '<span class="badge off">выключена</span>';
  }
  const last = target.last_check;
  if (!last) {
    return '<span class="badge unknown">нет данных</span>';
  }
  if (last.ok) {
    return '<span class="badge ok">работает</span>';
  }
  const reason = last.error ? escapeHtml(last.error) : "проверка не прошла";
  return `<span class="badge fail" title="${reason}">проблема</span>`;
}

function formatValue(value, suffix) {
  if (value === null || value === undefined) {
    return "—";
  }
  return `${value}${suffix}`;
}

function formatTime(isoString) {
  const date = new Date(isoString);
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function renderRows(targets) {
  const rows = targets
    .map((target) => {
      const last = target.last_check;
      return `<tr>
        <td><a href="/targets/${target.id}">${escapeHtml(target.name)}</a></td>
        <td>${escapeHtml(target.type)}</td>
        <td>${statusBadge(target)}</td>
        <td>${last ? formatValue(last.latency_ms, " мс") : "—"}</td>
        <td>${formatValue(target.uptime_24h, " %")}</td>
        <td>${target.checks_24h}</td>
        <td>${last ? formatTime(last.checked_at) : "—"}</td>
      </tr>`;
    })
    .join("");

  document.getElementById("rows").innerHTML = rows;
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
    updated.textContent = `обновлено ${new Date().toLocaleTimeString("ru-RU")}`;
  } catch (error) {
    updated.textContent = "не удалось получить данные";
  }
}

refresh();
setInterval(refresh, REFRESH_MS);
