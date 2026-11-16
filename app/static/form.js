// Показываем только поля, относящиеся к выбранному типу проверки
const typeSelect = document.getElementById("target-type");

function updateFieldsets() {
  const activeType = typeSelect.value;
  document.querySelectorAll("[data-for]").forEach((element) => {
    element.classList.toggle("hidden", element.dataset.for !== activeType);
  });
}

if (typeSelect) {
  typeSelect.addEventListener("change", updateFieldsets);
  updateFieldsets();
}
