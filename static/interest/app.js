(() => {
  "use strict";

  const MAX_AMOUNT = 1e15;
  const MAX_PERIODS = 1200;
  const MAX_PERIOD_YEARS = 100;
  const PERIOD_UNIT_YEARS = {
    year: 1,
    quarter: 1 / 4,
    month: 1 / 12,
    day: 1 / 365,
  };
  const MODE_LABELS = {
    equal_installment: "等额本息",
    equal_principal: "等额本金",
    interest_only: "先息后本",
    flat_rate: "等本等息",
    simple_bullet: "到期一次还本付息",
  };
  const RELATION_LABELS = {
    equal: "与合同口径一致",
    higher: "高于合同口径",
    lower: "低于合同口径",
  };
  const FIELD_LABELS = {
    principal: "总本金",
    interest: "总利息",
    periods: "总期数",
    period_value: "每期时长",
  };
  // Level-payment modes can be driven by either the total interest or the
  // per-period payment; the two convert into each other.
  const LEVEL_PAYMENT_MODES = ["equal_installment", "flat_rate"];
  const BASIS_LABELS = { interest: "总利息", payment: "每期还款" };
  const BASIS_UNITS = { interest: "元", payment: "元/期" };
  const CONCESSION_FIELDS = {
    first_periods: {
      label: "免息期数",
      unit: "期",
      placeholder: "1",
      hint: "前 N 期不计利息，本金仍按期归还。",
    },
    amount: {
      label: "减免金额",
      unit: "元",
      placeholder: "",
      hint: "按各期利息占比摊薄，减免额不会超过总利息。",
    },
    rate_discount: {
      label: "折扣",
      unit: "折",
      placeholder: "8",
      hint: "按折扣重算合同利率与每期利息；10 折即无优惠。",
    },
  };
  const CONCESSION_HINTS = {
    none: "减免类优惠不改变合同利率，只减少实际收取的利息。",
    full_waiver: "总利息全部免除，只按期归还本金。",
  };

  const form = document.querySelector("#calc-form");
  const resultPanel = document.querySelector("#result-panel");
  const submitButton = document.querySelector("#submit-button");
  const statusEl = document.querySelector("#result-status");
  const rateBlock = document.querySelector("#rate-block");
  const annualRateEl = document.querySelector("#annual-rate");
  const irrLine = document.querySelector("#irr-line");
  const irrRateEl = document.querySelector("#irr-rate");
  const irrRelationEl = document.querySelector("#irr-relation");
  const periodRateEl = document.querySelector("#period-rate");
  const totalYearsEl = document.querySelector("#total-years");
  const formulaEl = document.querySelector("#formula");
  const modeNoteEl = document.querySelector("#mode-note");
  const resultErrorEl = document.querySelector("#result-error");
  const liveStatusEl = document.querySelector("#live-status");
  const modeInputs = Array.from(document.querySelectorAll('input[name="mode"]'));
  const unitButtons = Array.from(document.querySelectorAll(".mini-button[data-unit]"));
  const basisButtons = Array.from(document.querySelectorAll(".mini-button[data-basis]"));
  const basisSwitch = document.querySelector("#basis-switch");
  const interestLabel = document.querySelector("#interest-label");
  const interestUnit = document.querySelector("#interest-unit");
  const scheduleSection = document.querySelector("#schedule-section");
  const scheduleToggle = document.querySelector("#schedule-toggle");
  const scheduleBody = document.querySelector("#schedule-body");
  const scheduleMeta = document.querySelector("#schedule-meta");
  const scheduleRows = document.querySelector("#schedule-body-rows");
  const scheduleTableWrap = document.querySelector("#schedule-table-wrap");
  const scheduleTotalPayment = document.querySelector("#schedule-total-payment");
  const scheduleTotalPrincipal = document.querySelector("#schedule-total-principal");
  const scheduleTotalInterest = document.querySelector("#schedule-total-interest");
  const concessionSelect = document.querySelector("#concession-type");
  const concessionValueRow = document.querySelector("#concession-value-row");
  const concessionValueLabel = document.querySelector("#concession-value-label");
  const concessionValueUnit = document.querySelector("#concession-value-unit");
  const concessionHint = document.querySelector("#concession-hint");
  const concessionLine = document.querySelector("#concession-line");
  const concessionText = document.querySelector("#concession-text");
  const fields = {
    principal: document.querySelector("#principal"),
    interest: document.querySelector("#interest"),
    periods: document.querySelector("#periods"),
    period_value: document.querySelector("#period-value"),
    concession_value: document.querySelector("#concession-value"),
  };

  let hasResult = false;
  let lastSignature = "";
  let lastMode = "";
  let busy = false;
  let periodUnit = "month";
  let amountBasis = "interest";

  function selectedMode() {
    const checked = modeInputs.find((input) => input.checked);
    return checked ? checked.value : "interest_only";
  }

  function cleanText(raw) {
    return raw.replace(/[\s,，]/g, "");
  }

  function parseNumeric(raw) {
    const text = cleanText(raw);
    if (!text) return null;

    const parts = text.split("/");
    if (parts.length > 2 || parts.some((part) => part === "")) return null;

    const numbers = parts.map(Number);
    if (numbers.some((value) => !Number.isFinite(value))) return null;

    if (parts.length === 2) {
      if (numbers[1] === 0) return null;
      return numbers[0] / numbers[1];
    }
    return numbers[0];
  }

  function parseAmount(raw) {
    if (cleanText(raw).includes("/")) return null;
    return parseNumeric(raw);
  }

  function concessionType() {
    return concessionSelect.value;
  }

  function concessionField() {
    return CONCESSION_FIELDS[concessionType()] || null;
  }

  function concessionValueError(raw) {
    const config = concessionField();
    const text = cleanText(raw);
    if (!text) return `请输入${config.label}`;

    const type = concessionType();
    if (type === "amount") {
      const value = parseAmount(raw);
      if (value === null) return "请输入有效金额";
      if (value <= 0) return "减免金额必须大于 0";
      if (value > MAX_AMOUNT) return "减免金额超出可计算范围";
      return "";
    }

    const value = parseNumeric(raw);
    if (value === null) return `请输入有效${config.label}`;

    if (type === "first_periods") {
      if (!Number.isInteger(value)) return "免息期数必须为正整数";
      if (value < 1) return "免息期数必须大于 0";
      const periods = parseNumeric(fields.periods.value);
      if (periods !== null && Number.isInteger(periods) && value > periods) {
        return `免息期数需在 1–${periods} 之间`;
      }
      return "";
    }

    if (value <= 0) return "折扣必须大于 0";
    if (value > 10) return "折扣需在 0–10 折之间";
    return "";
  }

  function paymentError(payment) {
    if (payment <= 0) return "每期还款必须大于 0";
    if (payment > MAX_AMOUNT) return "每期还款超出可计算范围";

    const principal = parseAmount(fields.principal.value);
    const periods = parseNumeric(fields.periods.value);
    if (principal === null || periods === null || periods < 1) return "";

    const interest = payment * periods - principal;
    if (interest < 0) return "每期还款低于平均本金，无法得到非负总利息";
    if (interest > MAX_AMOUNT) return "折算总利息超出可计算范围";
    return "";
  }

  function fieldError(name) {
    if (name === "concession_value") {
      return concessionValueRow.hidden ? "" : concessionValueError(fields[name].value);
    }

    const raw = fields[name].value;
    const text = cleanText(raw);

    if (!text) {
      if (name === "interest") {
        return amountBasis === "payment" ? "请输入每期还款" : "请输入总利息（可为 0）";
      }
      return `请输入${FIELD_LABELS[name]}`;
    }

    if (name === "periods") {
      if (!/^[0-9]+$/.test(text)) return "总期数必须为正整数";
      const value = Number(text);
      if (value < 1 || value > MAX_PERIODS) {
        return `总期数需在 1–${MAX_PERIODS} 之间`;
      }
      return "";
    }

    const value = name === "period_value" ? parseNumeric(raw) : parseAmount(raw);
    if (value === null) {
      return name === "period_value"
        ? "请输入有效数字或分数，如 1 或 1.5"
        : "请输入有效金额";
    }

    if (name === "period_value") {
      if (value <= 0) return "每期时长必须大于 0";
      if (value * PERIOD_UNIT_YEARS[periodUnit] > MAX_PERIOD_YEARS) {
        return `每期时长折合不能超过 ${MAX_PERIOD_YEARS} 年`;
      }
      return "";
    }

    if (name === "interest") {
      if (amountBasis === "payment") return paymentError(value);
      if (value < 0) return "总利息不能为负";
      if (value > MAX_AMOUNT) return "总利息超出可计算范围";
      return "";
    }

    if (value <= 0) return "总本金必须大于 0";
    if (value > MAX_AMOUNT) return "总本金超出可计算范围";
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
      if (name === "concession_value" && concessionValueRow.hidden) continue;
      const valid = validateField(name);
      if (!valid && firstInvalid === null) firstInvalid = fields[name];
    }

    if (firstInvalid) {
      window.setTimeout(() => firstInvalid.focus(), 0);
    }
    return firstInvalid === null;
  }

  function collectPayload() {
    const amount = fields.interest.value;
    const concession = concessionType();
    return {
      principal: fields.principal.value,
      interest: amountBasis === "interest" ? amount : null,
      payment: amountBasis === "payment" ? amount : null,
      periods: fields.periods.value,
      period_value: fields.period_value.value,
      period_unit: periodUnit,
      mode: selectedMode(),
      concession,
      concession_value: CONCESSION_FIELDS[concession] ? fields.concession_value.value : null,
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

  function setPeriodUnit(unit) {
    periodUnit = unit;
    for (const button of unitButtons) {
      button.setAttribute("aria-pressed", String(button.dataset.unit === unit));
    }
  }

  function applyBasisPresentation() {
    interestLabel.textContent = BASIS_LABELS[amountBasis];
    interestUnit.textContent = BASIS_UNITS[amountBasis];
    for (const button of basisButtons) {
      button.setAttribute("aria-pressed", String(button.dataset.basis === amountBasis));
    }
  }

  function convertAmount(to) {
    const from = amountBasis;
    if (from === to) return;

    const value = parseAmount(fields.interest.value);
    const principal = parseAmount(fields.principal.value);
    const periods = parseNumeric(fields.periods.value);
    if (value === null || principal === null || periods === null || periods < 1) return;

    const next = to === "payment" ? (principal + value) / periods : value * periods - principal;
    fields.interest.value = (next > 0 ? next : 0).toFixed(2);
  }

  function setAmountBasis(basis) {
    if (basis === amountBasis) return;
    convertAmount(basis);
    amountBasis = basis;
    applyBasisPresentation();
    validateField("interest");
  }

  function syncBasisControl() {
    const level = LEVEL_PAYMENT_MODES.includes(selectedMode());
    if (!level) setAmountBasis("interest");
    basisSwitch.hidden = !level;
  }

  function syncConcessionControl() {
    const config = concessionField();
    concessionValueRow.hidden = config === null;
    concessionHint.textContent = config
      ? config.hint
      : CONCESSION_HINTS[concessionType()] || CONCESSION_HINTS.none;

    if (config === null) {
      setFieldError("concession_value", "");
      return;
    }

    concessionValueLabel.textContent = config.label;
    concessionValueUnit.textContent = config.unit;
    fields.concession_value.value = config.placeholder;
  }

  function markStale() {
    if (!hasResult) return;
    resultPanel.classList.add("is-stale");
    if (!scheduleSection.hidden) scheduleSection.classList.add("is-stale");
  }

  function syncStaleState() {
    if (!hasResult) return;

    const isCurrent = signatureOf(collectPayload()) === lastSignature;
    resultPanel.classList.toggle("is-stale", !isCurrent);
    if (!scheduleSection.hidden) {
      scheduleSection.classList.toggle("is-stale", !isCurrent);
    }
    setStatus(isCurrent ? MODE_LABELS[lastMode] || "" : "参数已变更", !isCurrent);
  }

  function render(data) {
    annualRateEl.textContent = data.contract_annual_rate_percent;
    periodRateEl.textContent = `${data.contract_period_rate_percent}%`;
    irrRateEl.textContent = `${data.irr_annual_rate_percent}%`;
    irrRelationEl.textContent = RELATION_LABELS[data.irr_relation] || "—";
    irrLine.classList.toggle("is-higher", data.irr_relation === "higher");
    irrLine.classList.toggle("is-lower", data.irr_relation === "lower");
    irrLine.classList.toggle("is-equal", data.irr_relation === "equal");
    totalYearsEl.textContent = `${data.total_years} 年`;
    formulaEl.textContent = data.formula;
    modeNoteEl.textContent = data.note;
    renderSchedule(data);

    const concession = data.concession || {};
    const hasConcession = Boolean(concession.type) && concession.type !== "none";
    concessionLine.hidden = !hasConcession;
    concessionText.textContent = hasConcession
      ? `${concession.label} · ${concession.detail}`
      : "";

    rateBlock.classList.remove("is-updated");
    void rateBlock.offsetWidth;
    rateBlock.classList.add("is-updated");
  }

  function renderSchedule(data) {
    const rows = Array.isArray(data.schedule) ? data.schedule : [];
    const totals = data.schedule_total || {};

    scheduleMeta.textContent =
      `共 ${rows.length} 期，每期 ${data.period_label}` +
      (data.payment ? `，每期还款 ${data.payment} 元` : "") +
      "。";
    scheduleTotalPayment.textContent = totals.payment || "—";
    scheduleTotalPrincipal.textContent = totals.principal || "—";
    scheduleTotalInterest.textContent = totals.interest || "—";

    const fragment = document.createDocumentFragment();
    for (const row of rows) {
      const tr = document.createElement("tr");
      for (const key of ["period", "payment", "principal", "interest", "balance"]) {
        const td = document.createElement("td");
        if (key === "payment") td.className = "schedule-payment-cell";
        td.textContent = String(row[key]);
        tr.append(td);
      }
      fragment.append(tr);
    }
    scheduleRows.replaceChildren(fragment);
    scheduleTableWrap.classList.toggle("is-long", rows.length > 24);
    scheduleTableWrap.scrollTop = 0;
    scheduleTableWrap.scrollLeft = 0;
    scheduleSection.hidden = false;
  }

  async function calculate() {
    if (busy) return;

    if (!validateAll()) {
      markStale();
      setStatus("参数有误", true);
      announce("输入有误，请检查标出的字段。");
      return;
    }

    const payload = collectPayload();
    setBusy(true);
    setResultError("");
    setStatus("计算中");

    try {
      const response = await fetch("../api/calculate", {
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
        if (data && data.field) {
          // The payment amount shares the ledger row with the total interest.
          const name = data.field === "payment" ? "interest" : data.field;
          if (fields[name]) {
            setFieldError(name, message);
            fields[name].focus();
          }
        }
        setResultError(message);
        markStale();
        setStatus("计算失败", true);
        announce(`计算失败：${message}`);
        return;
      }

      if (!data) throw new SyntaxError("Invalid response body");

      for (const name of Object.keys(fields)) setFieldError(name, "");
      render(data);
      hasResult = true;
      lastSignature = signatureOf(payload);
      lastMode = data.mode;
      syncStaleState();
      announce(
        `${MODE_LABELS[data.mode] || ""}，合同年化单利 ${data.contract_annual_rate_percent}%，` +
          `实际年化 IRR ${data.irr_annual_rate_percent}%（${RELATION_LABELS[data.irr_relation] || "—"}），` +
          `每期利率 ${data.contract_period_rate_percent}%` +
          (data.payment ? `，每期还款 ${data.payment} 元` : "") +
          (data.concession && data.concession.type !== "none"
            ? `，优惠：${data.concession.label}`
            : "") +
          `，总期限 ${data.total_years} 年；每期明细共 ${data.schedule.length} 期。`
      );
    } catch (error) {
      const message =
        error instanceof TypeError
          ? "无法连接本地计算服务，请确认应用仍在运行。"
          : "计算失败，请稍后重试。";
      setResultError(message);
      markStale();
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
          if (hasResult) resultPanel.classList.add("is-stale");
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

  for (const input of modeInputs) {
    input.addEventListener("change", () => {
      syncBasisControl();
      syncStaleState();
    });
  }

  concessionSelect.addEventListener("change", () => {
    syncConcessionControl();
    validateField("concession_value");
    syncStaleState();
  });

  for (const button of basisButtons) {
    button.addEventListener("click", () => {
      const basis = button.dataset.basis === "payment" ? "payment" : "interest";
      setAmountBasis(basis);
      announce(`${BASIS_LABELS[amountBasis]}口径，输入框当前为 ${fields.interest.value}`);
      syncStaleState();
    });
  }

  for (const button of unitButtons) {
    button.addEventListener("click", () => {
      setPeriodUnit(button.dataset.unit || "month");
      if (fields.period_value.value.trim()) validateField("period_value");
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
  syncConcessionControl();
  void calculate();
})();
