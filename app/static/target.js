// Кнопка «Проверить сейчас» на странице цели
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
