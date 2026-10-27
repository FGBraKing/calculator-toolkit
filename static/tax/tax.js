(() => {
  "use strict";

  const MAX_AMOUNT = 1e12;

  const FIELD_LABELS = {
    income: "收入",
    bonus: "年终奖",
    social: "三险一金",
    child_education: "子女教育",
    infant_care: "婴幼儿照护",
    continuing_education: "继续教育",
    mortgage_interest: "住房贷款利息",
    housing_rent: "住房租金",
    elderly_support: "赡养老人",
    serious_illness: "大病医疗自付",
    pension: "个人养老金",
  };

  const SPECIAL_CAPS = {
    continuing_education: 400,
    mortgage_interest: 1000,
    housing_rent: 1500,
    elderly_support: 3000,
  };

  const BASIS_LABELS = { month: "月收入", year: "年收入" };
  const BASIS_UNITS = { month: "元/月", year: "元/年" };

  const form = document.querySelector("#tax-form");
  const resultPanel = document.querySelector("#result-panel");
  const submitButton = document.querySelector("#submit-button");
  const statusEl = document.querySelector("#result-status");
  const taxBlock = document.querySelector("#tax-block");
  const totalTaxEl = document.querySelector("#total-tax");
  const netIncomeEl = document.querySelector("#net-income");
  const effectiveLabelEl = document.querySelector("#effective-rate-label");
  const bonusLine = document.querySelector("#bonus-line");
  const bonusText = document.querySelector("#bonus-text");
  const taxableEl = document.querySelector("#taxable-income");
  const marginalEl = document.querySelector("#marginal-rate");
  const formulaEl = document.querySelector("#formula");
  const noteEl = document.querySelector("#tax-note");
  const resultErrorEl = document.querySelector("#result-error");
  const liveStatusEl = document.querySelector("#live-status");
  const basisSwitch = document.querySelector("#basis-switch");
  const basisButtons = Array.from(document.querySelectorAll("#basis-switch .mini-button"));
  const bonusModeButtons = Array.from(document.querySelectorAll("[data-bonus-mode]"));
  const incomeLabel = document.querySelector("#income-label");
  const incomeUnit = document.querySelector("#income-unit");
  const scheduleSection = document.querySelector("#schedule-section");
  const scheduleToggle = document.querySelector("#schedule-toggle");
  const scheduleBody = document.querySelector("#schedule-body");
  const scheduleMeta = document.querySelector("#schedule-meta");
  const scheduleRows = document.querySelector("#schedule-body-rows");
  const scheduleTableWrap = document.querySelector("#schedule-table-wrap");
  const scheduleTotalTax = document.querySelector("#schedule-total-tax");
  const scheduleTotalIncome = document.querySelector("#schedule-total-income");
  const scheduleTotalDeduction = document.querySelector("#schedule-total-deduction");
  const fields = {
    income: document.querySelector("#income"),
    bonus: document.querySelector("#bonus"),
    social: document.querySelector("#social"),
    child_education: document.querySelector("#child-education"),
    infant_care: document.querySelector("#infant-care"),
    continuing_education: document.querySelector("#continuing-education"),
    mortgage_interest: document.querySelector("#mortgage-interest"),
    housing_rent: document.querySelector("#housing-rent"),
    elderly_support: document.querySelector("#elderly-support"),
    serious_illness: document.querySelector("#serious-illness"),
    pension: document.querySelector("#pension"),
  };

  let incomeBasis = "month";
  let bonusMode = "separate";
  let hasResult = false;
  let lastSignature = "";
  let busy = false;

  function cleanText(raw) {
    return raw.replace(/[\s,，]/g, "");
  }

  function parseAmount(raw) {
    const text = cleanText(raw);
    if (!text || text.includes("/")) return null;
    const value = Number(text);
    return Number.isFinite(value) ? value : null;
  }

  function formatMoney(value) {
    return value.toLocaleString("zh-CN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function fieldError(name) {
    const raw = fields[name].value;
    const text = cleanText(raw);
    const label = FIELD_LABELS[name];

    if (!text) return `请输入${label}`;

    const value = parseAmount(raw);
    if (value === null) return `${label}格式不正确`;
    if (value < 0) return `${label}不能为负`;
    if (value > MAX_AMOUNT) return `${label}超出可计算范围`;

    const cap = SPECIAL_CAPS[name];
    if (cap && value > cap) {
      return `${label}每月最多 ${formatMoney(cap)} 元`;
    }

    if (name === "housing_rent" || name === "mortgage_interest") {
      const other =
        name === "housing_rent" ? fields.mortgage_interest : fields.housing_rent;
      const counterpart = parseAmount(other.value);
      if (counterpart !== null && counterpart > 0 && value > 0) {
        return "住房贷款利息与住房租金不能同时享受";
      }
    }

    if (name === "social") {
      const income = parseAmount(fields.income.value);
      if (income !== null) {
        const annual = incomeBasis === "month" ? income * 12 : income;
        if (value * 12 > annual + 1e-6) return "三险一金合计不能超过年收入";
      }
    }

    return "";
  }

  function setFieldError(name, message) {
    const input = fields[name];
    const row = input.closest(".ledger-row");
    const error = row.querySelector(".field-error");

    row.classList.toggle("is-invalid", Boolean(message));
    if (message) {
      input.setAttribute("aria-invalid", "true");
    } else {
      input.removeAttribute("aria-invalid");
    }
    error.textContent = message;
  }

  function validateField(name) {
    const message = fieldError(name);
    setFieldError(name, message);
    return message === "";
  }

  function validateAll() {
    let firstInvalid = null;

    for (const name of Object.keys(fields)) {
      const valid = validateField(name);
      if (!valid && firstInvalid === null) firstInvalid = fields[name];
    }

    if (firstInvalid) {
      window.setTimeout(() => firstInvalid.focus(), 0);
    }
    return firstInvalid === null;
  }

  function specialPayload() {
    return {
      child_education: fields.child_education.value,
      infant_care: fields.infant_care.value,
      continuing_education: fields.continuing_education.value,
      mortgage_interest: fields.mortgage_interest.value,
      housing_rent: fields.housing_rent.value,
      elderly_support: fields.elderly_support.value,
    };
  }

  function collectPayload() {
    return {
      income: fields.income.value,
      income_basis: incomeBasis,
      bonus: fields.bonus.value,
      bonus_mode: bonusMode,
      social: fields.social.value,
      special: specialPayload(),
      serious_illness: fields.serious_illness.value,
      pension: fields.pension.value,
    };
  }

  function signatureOf(payload) {
    return JSON.stringify(payload);
  }

  function setStatus(text, alert = false) {
    statusEl.textContent = text;
    statusEl.classList.toggle("is-alert", alert);
  }

  function setResultError(message) {
    resultErrorEl.textContent = message;
    resultErrorEl.classList.toggle("is-visible", Boolean(message));
  }

  function setBusy(value) {
    busy = value;
    submitButton.disabled = value;
    resultPanel.setAttribute("aria-busy", value ? "true" : "false");
  }

  function announce(message) {
    liveStatusEl.textContent = "";
    window.requestAnimationFrame(() => {
      liveStatusEl.textContent = message;
    });
  }

  function syncBasisControl() {
    incomeLabel.textContent = BASIS_LABELS[incomeBasis];
    incomeUnit.textContent = BASIS_UNITS[incomeBasis];
    for (const button of basisButtons) {
      button.setAttribute("aria-pressed", String(button.dataset.basis === incomeBasis));
    }
  }

  function convertIncome(next) {
    if (next === incomeBasis) return;
    const value = parseAmount(fields.income.value);
    if (value !== null && value >= 0) {
      const converted = next === "year" ? value * 12 : value / 12;
      fields.income.value = String(Number(converted.toFixed(2)));
    }
    incomeBasis = next;
    syncBasisControl();
    validateField("income");
  }

  function syncBonusMode() {
    for (const button of bonusModeButtons) {
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.bonusMode === bonusMode)
      );
    }
  }

  function syncStaleState() {
    if (!hasResult) return;
    const isCurrent = signatureOf(collectPayload()) === lastSignature;
    resultPanel.classList.toggle("is-stale", !isCurrent);
    scheduleSection.classList.toggle("is-stale", !isCurrent);
    setStatus(isCurrent ? "已计算" : "参数已变更", !isCurrent);
  }

  function render(data) {
    totalTaxEl.textContent = data.total_tax;
    netIncomeEl.textContent = `${data.net_income} 元`;
    effectiveLabelEl.textContent = `实际税负 ${data.effective_rate_percent}%`;
    taxableEl.textContent = `${data.taxable_income} 元`;
    marginalEl.textContent = `${data.marginal_rate_percent}%`;
    formulaEl.textContent = data.formula;
    noteEl.textContent = data.note;
    renderBonusLine(data);
    renderSchedule(data);

    taxBlock.classList.remove("is-updated");
    void taxBlock.offsetWidth;
    taxBlock.classList.add("is-updated");
  }

  function renderBonusLine(data) {
    const bonus = Number(cleanText(data.bonus));
    if (!bonus) {
      bonusLine.hidden = true;
      bonusText.textContent = "";
      return;
    }
    const comparison = data.bonus_comparison;
    bonusLine.hidden = false;
    bonusText.textContent =
      `单独计税合计 ${comparison.separate_tax} 元 · 并入综合所得 ${comparison.combined_tax} 元 · ` +
      comparison.note;
  }

  function renderSchedule(data) {
    const rows = Array.isArray(data.schedule) ? data.schedule : [];
    const totals = data.schedule_total || {};

    scheduleMeta.textContent = `共 ${rows.length} 个月，每月收入 ${data.monthly_income} 元。`;
    scheduleTotalTax.textContent = totals.tax || "—";
    scheduleTotalIncome.textContent = totals.income || "—";
    scheduleTotalDeduction.textContent = totals.deduction || "—";

    const fragment = document.createDocumentFragment();
    for (const row of rows) {
      const tr = document.createElement("tr");
      const cells = [
        row.month,
        row.income,
        row.deduction,
        row.taxable,
        row.tax,
        row.cumulative_tax,
      ];
      const classes = ["", "tax-col-income", "tax-col-deduction", "", "", ""];
      cells.forEach((value, index) => {
        const td = document.createElement("td");
        if (classes[index]) td.className = classes[index];
        td.textContent = String(value);
        tr.append(td);
      });
      fragment.append(tr);
    }
    scheduleRows.replaceChildren(fragment);
    scheduleTableWrap.scrollTop = 0;
    scheduleTableWrap.scrollLeft = 0;
  }

  async function calculate() {
    if (busy) return;

    if (!validateAll()) {
      setStatus("参数有误", true);
      announce("输入有误，请检查标出的字段。");
      return;
    }

    const payload = collectPayload();
    setBusy(true);
    setResultError("");
    setStatus("计算中");

    try {
      const response = await fetch("../api/tax/calculate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const message =
          data && typeof data.detail === "string"
            ? data.detail
            : "计算失败，请检查输入后重试。";
        if (data && data.field && fields[data.field]) {
          setFieldError(data.field, message);
          fields[data.field].focus();
        }
        setResultError(message);
        resultPanel.classList.add("is-stale");
        scheduleSection.classList.add("is-stale");
        setStatus("计算失败", true);
        announce(`计算失败：${message}`);
        return;
      }

      if (!data) throw new SyntaxError("Invalid response body");

      for (const name of Object.keys(fields)) setFieldError(name, "");
      render(data);
      hasResult = true;
      lastSignature = signatureOf(payload);
      syncStaleState();
      announce(
        `全年应纳税额 ${data.total_tax} 元，税后收入 ${data.net_income} 元，` +
          `实际税负 ${data.effective_rate_percent}%，边际税率 ${data.marginal_rate_percent}%；` +
          `预扣明细共 ${data.schedule.length} 个月。`
      );
    } catch (error) {
      const message =
        error instanceof TypeError
          ? "无法连接本地计算服务，请确认应用仍在运行。"
          : "计算失败，请稍后重试。";
      setResultError(message);
      resultPanel.classList.add("is-stale");
      scheduleSection.classList.add("is-stale");
      setStatus("连接失败", true);
      announce(message);
    } finally {
      setBusy(false);
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void calculate();
  });

  for (const [name, input] of Object.entries(fields)) {
    input.addEventListener("input", () => {
      const row = input.closest(".ledger-row");
      if (row.classList.contains("is-invalid")) {
        const valid = validateField(name);
        if (!valid) {
          setStatus("参数有误", true);
          return;
        }
      }
      syncStaleState();
    });

    input.addEventListener("blur", () => {
      validateField(name);
    });
  }

  for (const button of basisButtons) {
    button.addEventListener("click", () => {
      convertIncome(button.dataset.basis === "year" ? "year" : "month");
      syncStaleState();
    });
  }

  for (const button of bonusModeButtons) {
    button.addEventListener("click", () => {
      bonusMode = button.dataset.bonusMode === "combined" ? "combined" : "separate";
      syncBonusMode();
      syncStaleState();
    });
  }

  scheduleToggle.addEventListener("click", () => {
    const expanded = scheduleToggle.getAttribute("aria-expanded") === "true";
    const next = !expanded;
    scheduleToggle.setAttribute("aria-expanded", String(next));
    scheduleToggle.textContent = next ? "收起明细" : "展开明细";
    scheduleBody.hidden = !next;
  });

  syncBasisControl();
  syncBonusMode();
  void calculate();
})();
