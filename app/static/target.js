// Страница цели: время в поясе браузера и кнопка «Проверить сейчас»

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

document.querySelectorAll("time[data-format='full']").forEach((element) => {
  const iso = element.getAttribute("datetime");
  if (!iso) {
    return;
  }
  element.textContent = formatFull(iso);
});

const button = document.getElementById("check-now");

if (button) {
  button.addEventListener("click", async () => {
    const targetId = button.dataset.targetId;
    button.disabled = true;
    button.textContent = "Проверяю…";

    try {
      const response = await fetch(`/api/targets/${targetId}/check`, {
        method: "POST",
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      // Перезагружаем страницу, чтобы увидеть новую запись в истории
      window.location.reload();
    } catch (error) {
      button.disabled = false;
      button.textContent = "Проверить сейчас";
      alert("Не удалось выполнить проверку: " + error.message);
    }
  });
}
