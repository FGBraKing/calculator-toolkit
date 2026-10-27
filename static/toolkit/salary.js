(() => {
  "use strict";

  const select = document.querySelector("#region");
  const salaryInput = document.querySelector("#salary");
  const baseInput = document.querySelector("#base");
  const hint = document.querySelector("#tool-hint");
  if (!select || !salaryInput || !baseInput) return;

  const regions = {};
  let autoBase = null;

  const clean = (raw) => raw.replace(/[\s,，]/g, "");
  const format = (value) =>
    Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 2 });

  function readNumber(input) {
    const text = clean(input.value);
    if (!text || text.includes("/")) return null;
    const value = Number(text);
    return Number.isFinite(value) ? value : null;
  }

  function applyRegion(force) {
    const region = regions[select.value];
    if (!region) {
      if (hint) hint.hidden = true;
      return;
    }
    const salary = readNumber(salaryInput);
    if (salary === null || salary <= 0) return;
    const current = readNumber(baseInput);
    // 用户手动改过基数就不再覆盖，除非重新选择地区
    if (!force && autoBase !== null && current !== autoBase) return;

    const lower = Number(region.lower);
    const upper = Number(region.upper);
    const value = Math.min(Math.max(salary, lower), upper);
    baseInput.value = String(Number(value.toFixed(2)));
    autoBase = value;
    baseInput.dispatchEvent(new Event("input", { bubbles: true }));

    if (hint) {
      hint.hidden = false;
      hint.textContent =
        `${region.name} ${region.year} 年缴费基数 ${format(lower)}–${format(upper)} 元/月，` +
        `已按 ${format(value)} 填入${value === salary ? "" : "（按上下限调整）"}；可手动修改。`;
    }
  }

  select.addEventListener("change", () => applyRegion(true));
  salaryInput.addEventListener("input", () => applyRegion(false));

  fetch("../api/city-params")
    .then((response) => (response.ok ? response.json() : null))
    .then((data) => {
      if (!data) return;
      const options = [new Option("自定义（手动填写）", "")];
      for (const region of data.regions) {
        regions[region.code] = region;
        options.push(
          new Option(
            `${region.name} · 基数 ${format(region.lower)}–${format(region.upper)}`,
            region.code
          )
        );
      }
      select.replaceChildren(...options);
    })
    .catch(() => {
      // 拉取失败时保留「自定义」，不影响手动填写
    });
})();
