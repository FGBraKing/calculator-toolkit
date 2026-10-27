(() => {
  "use strict";

  const MAX_AMOUNT = 1e12;
  const MAX_YEARS = 50;
  const MIN_AGE = 40;
  const MAX_AGE = 70;
  const MAX_RATE = 20;
  const MIN_PENSION_YEARS = 15;

  const TRACK_FIELDS = {
    employee: [
      "paid_years",
      "remaining_years",
      "retirement_age",
      "base",
      "social",
      "growth",
      "balance",
      "rate",
    ],
    resident: ["years", "contribution", "subsidy", "base_pension", "rate"],
  };

  const FIELD_LABELS = {
    paid_years: "已缴费年限",
    remaining_years: "距退休年数",
    retirement_age: "退休年龄",
    base: "月缴费基数",
    social: "当地社平工资",
    growth: "社平工资年增长",
    balance: "个人账户现有余额",
    years: "缴费年限",
    contribution: "每年个人缴费",
    subsidy: "每年政府补贴",
    base_pension: "当地基础养老金",
    rate: "个人账户记账利率",
  };

  const INTEGER_FIELDS = ["paid_years", "remaining_years", "retirement_age", "years"];
  const RATE_FIELDS = ["growth", "rate"];

  const form = document.querySelector("#pension-form");
  const resultPanel = document.querySelector("#result-panel");
  const submitButton = document.querySelector("#submit-button");
  const statusEl = document.querySelector("#result-status");
  const pensionBlock = document.querySelector("#pension-block");
  const monthlyTotalEl = document.querySelector("#monthly-total");
  const accountBalanceEl = document.querySelector("#account-balance");
  const annuityNoteEl = document.querySelector("#annuity-note");
  const pensionLine = document.querySelector("#pension-line");
  const pensionText = document.querySelector("#pension-text");
  const basicPensionEl = document.querySelector("#basic-pension");
  const accountPensionEl = document.querySelector("#account-pension");
  const replacementRateEl = document.querySelector("#replacement-rate");
  const formulaEl = document.querySelector("#formula");
  const noteEl = document.querySelector("#pension-note");
  const resultErrorEl = document.querySelector("#result-error");
  const liveStatusEl = document.querySelector("#live-status");
  const trackButtons = Array.from(document.querySelectorAll("[data-track]"));
  const employeeFields = document.querySelector("#employee-fields");
  const residentFields = document.querySelector("#resident-fields");
  const employeeHint = document.querySelector("#employee-hint");
  const residentHint = document.querySelector("#resident-hint");
  const regionSelect = document.querySelector("#region");
  const regionHint = document.querySelector("#region-hint");
  const scheduleSection = document.querySelector("#schedule-section");
  const scheduleToggle = document.querySelector("#schedule-toggle");
  const scheduleBody = document.querySelector("#schedule-body");
  const scheduleMeta = document.querySelector("#schedule-meta");
  const scheduleRows = document.querySelector("#schedule-body-rows");
  const scheduleTableWrap = document.querySelector("#schedule-table-wrap");
  const scheduleColBase = document.querySelector("#schedule-col-base");
  const scheduleColContribution = document.querySelector("#schedule-col-contribution");
  const scheduleTotalPaid = document.querySelector("#schedule-total-paid");
  const scheduleTotalBalance = document.querySelector("#schedule-total-balance");
  const scheduleTotalYears = document.querySelector("#schedule-total-years");
  const fields = {
    paid_years: document.querySelector("#paid-years"),
    remaining_years: document.querySelector("#remaining-years"),
    retirement_age: document.querySelector("#retirement-age"),
    base: document.querySelector("#base"),
    social: document.querySelector("#social"),
    growth: document.querySelector("#growth"),
    balance: document.querySelector("#balance"),
    years: document.querySelector("#years"),
    contribution: document.querySelector("#contribution"),
    subsidy: document.querySelector("#subsidy"),
    base_pension: document.querySelector("#base-pension"),
    rate: document.querySelector("#rate"),
  };

  let track = "employee";
  let hasResult = false;
  const regionsByCode = {};
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

  function parseInteger(raw) {
    const text = cleanText(raw);
    if (!/^[0-9]+$/.test(text)) return null;
    return Number(text);
  }

  function fieldError(name) {
    const raw = fields[name].value;
    const text = cleanText(raw);
    const label = FIELD_LABELS[name];

    if (!text) return `请输入${label}`;

    if (INTEGER_FIELDS.includes(name)) {
      const value = parseInteger(raw);
      if (value === null) return `${label}必须为整数`;
      if (name === "retirement_age") {
        if (value < MIN_AGE || value > MAX_AGE) {
          return `退休年龄需在 ${MIN_AGE}–${MAX_AGE} 岁之间`;
        }
        return "";
      }
      if (name === "years" && value === 0) return "缴费年限必须大于 0";
      if (value > MAX_YEARS) return `${label}需在 0–${MAX_YEARS} 之间`;
      return "";
    }

    const value = parseAmount(raw);
    if (value === null) return `${label}格式不正确`;
    if (value < 0) return `${label}不能为负`;
    if (value > MAX_AMOUNT) return `${label}超出可计算范围`;

    if (RATE_FIELDS.includes(name) && value > MAX_RATE) {
      return `${label}需在 0–${MAX_RATE}% 之间`;
    }

    if (name === "base" || name === "social") {
      const other = name === "base" ? fields.social : fields.base;
      const counterpart = parseAmount(other.value);
      if (value <= 0) return `${label}必须大于 0`;
      if (name === "base" && counterpart !== null && counterpart > 0) {
        const index = value / counterpart;
        if (index < 0.6 || index > 3) {
          return "缴费基数应在社平工资的 60%–300% 之间";
        }
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

    for (const name of TRACK_FIELDS[track]) {
      const valid = validateField(name);
      if (!valid && firstInvalid === null) firstInvalid = fields[name];
    }

    if (firstInvalid) {
      window.setTimeout(() => firstInvalid.focus(), 0);
    }
    return firstInvalid === null;
  }

  function collectPayload() {
    const payload = { track };
    for (const name of TRACK_FIELDS[track]) {
      payload[name] = fields[name].value;
    }
    return payload;
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

  async function loadRegions() {
    try {
      const response = await fetch("../api/pension/regions");
      if (!response.ok) return;
      const data = await response.json();
      const options = [new Option("自定义（手动填写）", "")];
      for (const region of data.regions) {
        regionsByCode[region.code] = region;
        const amount = Number(region.base).toLocaleString("zh-CN", {
          maximumFractionDigits: 1,
        });
        const year = region.year === 2025 ? "" : `（${region.year} 年）`;
        options.push(new Option(`${region.name} · ${amount} 元/月${year}`, region.code));
      }
      regionSelect.replaceChildren(...options);
      regionHint.textContent = data.note || "";
    } catch {
      // 拉取失败时保留「自定义」，不影响手动填写
    }
  }

  function setTrack(next) {
    if (next === track) return;
    track = next;
    employeeFields.hidden = track !== "employee";
    residentFields.hidden = track !== "resident";
    employeeHint.hidden = track !== "employee";
    residentHint.hidden = track !== "resident";
    regionSelect.addEventListener("change", () => {
    const region = regionsByCode[regionSelect.value];
    if (!region) return;
    fields.social.value = String(region.base);
    validateField("social");
    syncStaleState();
  });

  fields.social.addEventListener("input", () => {
    if (regionSelect.value) regionSelect.value = "";
  });

  for (const button of trackButtons) {
      button.setAttribute("aria-pressed", String(button.dataset.track === track));
    }
    for (const name of Object.keys(fields)) setFieldError(name, "");
    syncStaleState();
  }

  function syncStaleState() {
    if (!hasResult) return;
    const isCurrent = signatureOf(collectPayload()) === lastSignature;
    resultPanel.classList.toggle("is-stale", !isCurrent);
    scheduleSection.classList.toggle("is-stale", !isCurrent);
    setStatus(isCurrent ? "已计算" : "参数已变更", !isCurrent);
  }

  function render(data) {
    monthlyTotalEl.textContent = data.monthly_total;
    accountBalanceEl.textContent = `${data.account_balance} 元`;
    annuityNoteEl.textContent = `计发月数 ${data.annuity_months}`;
    basicPensionEl.textContent = `${data.basic_pension} 元`;
    accountPensionEl.textContent = `${data.account_pension} 元`;
    replacementRateEl.textContent = data.replacement_rate_percent
      ? `${data.replacement_rate_percent}%`
      : "—";
    formulaEl.textContent = data.formula;
    noteEl.textContent = data.note;
    renderPensionLine(data);
    renderSchedule(data);

    pensionBlock.classList.remove("is-updated");
    void pensionBlock.offsetWidth;
    pensionBlock.classList.add("is-updated");
  }

  function renderPensionLine(data) {
    const parts = [`累计缴费 ${data.years} 年`];
    if (data.track === "employee") {
      parts.push(`退休年龄 ${data.retirement_age} 岁`);
    } else {
      parts.push("60 岁起领取");
    }
    if (data.track === "employee" && data.index) {
      parts.push(`平均缴费指数 ${data.index}`);
    }
    const warning = !data.eligible;
    if (warning) {
      parts.push(`不足 ${MIN_PENSION_YEARS} 年，暂不能按月领取`);
    }
    pensionLine.hidden = false;
    pensionLine.classList.toggle("is-warning", warning);
    pensionText.textContent = parts.join(" · ");
  }

  function renderSchedule(data) {
    const rows = Array.isArray(data.schedule) ? data.schedule : [];
    const totals = data.schedule_total || {};
    const employee = data.track === "employee";

    scheduleColBase.textContent = employee ? "缴费基数" : "个人缴费";
    scheduleColContribution.textContent = employee ? "当年划入" : "政府补贴";
    scheduleMeta.textContent = employee
      ? `共 ${rows.length} 年 · 退休时计发基数 ${data.social_at_retirement} 元/月`
      : `共 ${rows.length} 年 · 60 岁起领取`;
    scheduleTotalPaid.textContent = totals.paid || "—";
    scheduleTotalBalance.textContent = totals.balance || "—";
    scheduleTotalYears.textContent = `${totals.years || data.years} 年`;

    const fragment = document.createDocumentFragment();
    for (const row of rows) {
      const tr = document.createElement("tr");
      const cells = employee
        ? [row.year, row.base, row.contribution, row.balance]
        : [row.year, row.contribution, row.subsidy, row.balance];
      for (const value of cells) {
        const td = document.createElement("td");
        td.textContent = String(value);
        tr.append(td);
      }
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
      const response = await fetch("../api/pension/calculate", {
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
        `预计月养老金 ${data.monthly_total} 元，其中基础养老金 ${data.basic_pension} 元、` +
          `个人账户养老金 ${data.account_pension} 元；累计缴费 ${data.years} 年。`
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

  regionSelect.addEventListener("change", () => {
    const region = regionsByCode[regionSelect.value];
    if (!region) return;
    fields.social.value = String(region.base);
    validateField("social");
    syncStaleState();
  });

  fields.social.addEventListener("input", () => {
    if (regionSelect.value) regionSelect.value = "";
  });

  for (const button of trackButtons) {
    button.addEventListener("click", () => {
      setTrack(button.dataset.track === "resident" ? "resident" : "employee");
    });
  }

  scheduleToggle.addEventListener("click", () => {
    const expanded = scheduleToggle.getAttribute("aria-expanded") === "true";
    const next = !expanded;
    scheduleToggle.setAttribute("aria-expanded", String(next));
    scheduleToggle.textContent = next ? "收起明细" : "展开明细";
    scheduleBody.hidden = !next;
  });

  void loadRegions();
  void calculate();
})();
