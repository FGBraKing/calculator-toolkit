(() => {
  "use strict";

  const button = document.querySelector("#shutdown");
  if (!button) return;
  const note = document.querySelector("#shutdown-note");

  button.addEventListener("click", async () => {
    button.disabled = true;
    button.textContent = "正在退出…";
    try {
      const response = await fetch("api/shutdown", {
        method: "POST",
        headers: { "X-Requested-With": "calculator-toolkit" },
      });
      if (!response.ok) throw new Error(String(response.status));
      button.textContent = "已退出";
      if (note) note.textContent = "服务已停止，可以关闭此页面。";
    } catch {
      button.disabled = false;
      button.textContent = "退出应用";
      if (note) note.textContent = "退出失败，请在活动监视器中结束「计算工具集」。";
    }
  });
})();
