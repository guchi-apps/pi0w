if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js");
  });
}

document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || form.method.toLowerCase() !== "post") {
    return;
  }
  event.preventDefault();

  try {
    const res = await fetch(form.action, { method: "POST", body: new FormData(form) });
    const html = await res.text();
    const newDoc = new DOMParser().parseFromString(html, "text/html");
    const newMain = newDoc.querySelector("main");
    const currentMain = document.querySelector("main");
    if (!newMain || !currentMain) {
      window.location.reload();
      return;
    }
    currentMain.replaceWith(newMain);

    // ヘッダーの全OFFボタンも状態(ラベル/見た目)が変わるため合わせて差し替える
    const newHeader = newDoc.querySelector("header.app-bar");
    const currentHeader = document.querySelector("header.app-bar");
    if (newHeader && currentHeader) {
      currentHeader.replaceWith(newHeader);
    }
  } catch (err) {
    window.location.reload();
  }
});

