const gatewayInput = document.getElementById("gatewayUrl");
const webAppInput = document.getElementById("webAppUrl");
const status = document.getElementById("status");

chrome.storage.sync.get({
  gatewayUrl: "http://localhost:3000",
  webAppUrl: "http://localhost:5173",
}, (items) => {
  gatewayInput.value = items.gatewayUrl;
  webAppInput.value = items.webAppUrl;
});

document.getElementById("save").addEventListener("click", () => {
  const gatewayUrl = gatewayInput.value.trim().replace(/\/+$/, "");
  const webAppUrl = webAppInput.value.trim().replace(/\/+$/, "");
  chrome.storage.sync.set({ gatewayUrl, webAppUrl }, () => {
    status.textContent = `Saved ${gatewayUrl} and ${webAppUrl}`;
  });
});
