(() => {
  "use strict";

  const slug = document.body.dataset.tool;
  const form = document.querySelector("#tool-form");
  const resultPanel = document.querySelector("#result-panel");
  const submitButton = document.querySelector("#submit-button");
  const statusEl = document.querySelector("#result-status");
  const primaryBlock = document.querySelector("#primary-block");
  const primaryEl = document.querySelector("#primary");
  const unitEl = document.querySelector("#primary-unit");
  const factLine = document.querySelector("#fact-line");
  const factText = document.querySelector("#fact-text");
  const metricsEl = document.querySelector("#metrics");
  const formulaEl = document.querySelector("#formula");
  const noteEl = document.querySelector("#note");
  const resultErrorEl = document.querySelector("#result-error");
  const liveStatusEl = document.querySelector("#live-status");
  const scheduleSection = document.querySelector("#schedule-section");
  const scheduleToggle = document.querySelector("#schedule-toggle");
  const scheduleBody = document.querySelector("#schedule-body");
  const scheduleMeta = document.querySelector("#schedule-meta");
  const scheduleHeadRow = document.querySelector("#schedule-head-row");
  const scheduleRows = document.querySelector("#schedule-body-rows");
  const scheduleTotals = document.querySelector("#schedule-totals");
  const scheduleTableWrap = document.querySelector("#schedule-table-wrap");
  const scheduleNote = document.querySelector("#schedule-note");
  const fieldInputs = Array.from(document.querySelectorAll("input[data-kind]"));
  const switchGroups = Array.from(document.querySelectorAll("[data-switch]"));
  const conditionalRows = Array.from(document.querySelectorAll("[data-show-when]"));

  const defaultUnit = unitEl.textContent;
  let hasResult = false;
  let lastSignature = "";
  let busy = false;

  function cleanText(raw) {
    return raw.replace(/[\s,，]/g, "");
  }

  function pressedValue(name) {
    const group = document.querySelector(`[data-switch="${name}"]`);
    const button = group && group.querySelector('button[aria-pressed="true"]');
    return button ? button.dataset.value : "";
  }

  function syncVisibility() {
    for (const row of conditionalRows) {
      const [name, value] = row.dataset.showWhen.split("=");
      row.hidden = pressedValue(name) !== value;
    }
  }

  function fieldError(input) {
    const label = input.dataset.label || input.name;
    const kind = input.dataset.kind;
    const raw = input.value;

    if (!raw.trim()) return kind === "date" ? `请选择${label}` : `请输入${label}`;
    if (kind === "date") return "";

    const text = cleanText(raw);
    if (kind === "int" && !/^[0-9]+$/.test(text)) return `${label}必须为整数`;
    if (kind !== "int" && text.includes("/")) return `${label}格式不正确`;

    const value = Number(text);
    if (!Number.isFinite(value)) return `${label}格式不正确`;
    if (value < 0) return `${label}不能为负`;

    const min = input.dataset.min === undefined ? null : Number(input.dataset.min);
    const max = input.dataset.max === undefined ? null : Number(input.dataset.max);
    if (min !== null && value < min) {
      return max === null ? `${label}不能小于 ${min}` : `${label}需在 ${min}–${max} 之间`;
    }
    if (max !== null && value > max) {
      return min === null ? `${label}不能大于 ${max}` : `${label}需在 ${min}–${max} 之间`;
    }
    return "";
  }

  function setFieldError(input, message) {
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

  function validateField(input) {
    const message = fieldError(input);
    setFieldError(input, message);
    return message === "";
  }

  function visibleInputs() {
    return fieldInputs.filter((input) => !input.closest(".ledger-row").hidden);
  }

  function validateAll() {
    let firstInvalid = null;
    for (const input of visibleInputs()) {
      const valid = validateField(input);
      if (!valid && firstInvalid === null) firstInvalid = input;
    }
    if (firstInvalid) window.setTimeout(() => firstInvalid.focus(), 0);
    return firstInvalid === null;
  }

  function collectPayload() {
    const payload = {};
    for (const input of visibleInputs()) payload[input.name] = input.value;
    for (const group of switchGroups) {
      payload[group.dataset.switch] = pressedValue(group.dataset.switch);
    }
    return payload;
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

  function syncStaleState() {
    if (!hasResult) return;
    const isCurrent = JSON.stringify(collectPayload()) === lastSignature;
    resultPanel.classList.toggle("is-stale", !isCurrent);
    if (!scheduleSection.hidden) {
      scheduleSection.classList.toggle("is-stale", !isCurrent);
    }
    setStatus(isCurrent ? "已计算" : "参数已变更", !isCurrent);
  }

  function render(data) {
    primaryEl.textContent = data.primary;
    unitEl.textContent = data.primary_unit === null ? defaultUnit : data.primary_unit;

    const facts = Array.isArray(data.facts) ? data.facts : [];
    factLine.hidden = facts.length === 0;
    factText.textContent = facts.join(" · ");

    const metrics = Array.isArray(data.metrics) ? data.metrics : [];
    metricsEl.replaceChildren(
      ...metrics.map(({ label, value }) => {
        const metric = document.createElement("div");
        metric.className = "metric";
        const dt = document.createElement("dt");
        dt.textContent = label;
        const dd = document.createElement("dd");
        dd.textContent = value;
        metric.append(dt, dd);
        return metric;
      })
    );
    metricsEl.dataset.count = String(metrics.length);

    formulaEl.textContent = data.formula;
    noteEl.textContent = data.note;
    renderSchedule(data.schedule);

    primaryBlock.classList.remove("is-updated");
    void primaryBlock.offsetWidth;
    primaryBlock.classList.add("is-updated");
  }

  function renderSchedule(schedule) {
    if (!schedule) {
      scheduleSection.hidden = true;
      return;
    }
    scheduleSection.hidden = false;
    scheduleMeta.textContent = schedule.meta || "";
    scheduleHeadRow.replaceChildren(
      ...schedule.columns.map((column) => {
        const th = document.createElement("th");
        th.scope = "col";
        th.textContent = column;
        return th;
      })
    );
    scheduleRows.replaceChildren(
      ...schedule.rows.map((cells) => {
        const tr = document.createElement("tr");
        for (const cell of cells) {
          const td = document.createElement("td");
          td.textContent = String(cell);
          tr.append(td);
        }
        return tr;
      })
    );
    scheduleTotals.replaceChildren(
      ...schedule.totals.map(({ label, value }) => {
        const total = document.createElement("div");
        total.className = "schedule-total";
        const dt = document.createElement("dt");
        dt.textContent = label;
        const dd = document.createElement("dd");
        dd.textContent = value;
        total.append(dt, dd);
        return total;
      })
    );
    scheduleNote.textContent = schedule.note || "";
    scheduleTableWrap.classList.toggle("is-long", schedule.rows.length > 24);
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
      const response = await fetch(`../api/${slug}/calculate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const message =
          data && typeof data.detail === "string" ? data.detail : "计算失败，请检查输入后重试。";
        if (data && data.field) {
          const input = fieldInputs.find((item) => item.name === data.field);
          if (input) {
            const row = input.closest(".ledger-row");
            if (row.hidden && row.dataset.showWhen) {
              const [name, value] = row.dataset.showWhen.split("=");
              for (const button of document.querySelectorAll(`[data-switch="${name}"] button`)) {
                button.setAttribute("aria-pressed", String(button.dataset.value === value));
              }
              syncVisibility();
            }
            setFieldError(input, message);
            input.focus();
          }
        }
        setResultError(message);
        resultPanel.classList.add("is-stale");
        if (!scheduleSection.hidden) scheduleSection.classList.add("is-stale");
        setStatus("计算失败", true);
        announce(`计算失败：${message}`);
        return;
      }

      if (!data) throw new SyntaxError("Invalid response body");

      for (const input of fieldInputs) setFieldError(input, "");
      render(data);
      hasResult = true;
      lastSignature = JSON.stringify(payload);
      syncStaleState();
      announce(
        `${data.primary}${data.primary_unit === null ? defaultUnit : data.primary_unit}` +
          (data.facts && data.facts.length ? `，${data.facts[0]}` : "")
      );
    } catch (error) {
      const message =
        error instanceof TypeError
          ? "无法连接本地计算服务，请确认应用仍在运行。"
          : "计算失败，请稍后重试。";
      setResultError(message);
      resultPanel.classList.add("is-stale");
      if (!scheduleSection.hidden) scheduleSection.classList.add("is-stale");
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

  for (const input of fieldInputs) {
    input.addEventListener("input", () => {
      const row = input.closest(".ledger-row");
      if (row.classList.contains("is-invalid") && !validateField(input)) {
        setStatus("参数有误", true);
        return;
      }
      syncStaleState();
    });
    input.addEventListener("blur", () => validateField(input));
  }

  for (const group of switchGroups) {
    const target = group.dataset.unitTarget;
    for (const button of group.querySelectorAll("button")) {
      button.addEventListener("click", () => {
        for (const other of group.querySelectorAll("button")) {
          other.setAttribute("aria-pressed", String(other === button));
        }
        if (target && button.dataset.unitLabel) {
          const input = document.querySelector(`#${target}`);
          const unit = input && input.closest(".ledger-entry").querySelector(".unit");
          if (unit) unit.textContent = button.dataset.unitLabel;
        }
        syncVisibility();
        syncStaleState();
      });
    }
  }

  scheduleToggle.addEventListener("click", () => {
    const expanded = scheduleToggle.getAttribute("aria-expanded") === "true";
    const next = !expanded;
    scheduleToggle.setAttribute("aria-expanded", String(next));
    scheduleToggle.textContent = next ? "收起明细" : "展开明细";
    scheduleBody.hidden = !next;
  });

  syncVisibility();
  void calculate();
})();
