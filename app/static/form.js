// 1. Показываем только поля, относящиеся к выбранному типу проверки
const typeSelect = document.getElementById("target-type");

function updateFieldsets() {
  if (!typeSelect) {
    return;
  }
  const activeType = typeSelect.value;
  document.querySelectorAll("[data-for]").forEach((element) => {
    element.classList.toggle("hidden", element.dataset.for !== activeType);
  });
}

// 2. Поле «ожидаемый код» нужно только при точном сравнении
const statusModeSelect = document.getElementById("status-mode");

function updateStatusModeFields() {
  if (!statusModeSelect) {
    return;
  }
  const mode = statusModeSelect.value;
  document.querySelectorAll("[data-mode]").forEach((element) => {
    element.classList.toggle("hidden", element.dataset.mode !== mode);
  });
}

if (typeSelect) {
  typeSelect.addEventListener("change", updateFieldsets);
  updateFieldsets();
}

if (statusModeSelect) {
  statusModeSelect.addEventListener("change", updateStatusModeFields);
  updateStatusModeFields();
}
