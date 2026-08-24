// Visita la app con un navegador real (headless) en vez de un curl simple.
// Streamlit Community Cloud necesita una sesión con cookies + JavaScript
// para "despertar"/mantener viva la app — un curl plano se queda en un
// bucle de redirecciones cuando la app está dormida (ver commit anterior).
const { chromium } = require("playwright");

const APP_URL = "https://jonathanportillatrainer.streamlit.app";

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  await page.goto(APP_URL, { waitUntil: "networkidle", timeout: 90000 });

  // Si la app estaba dormida, Streamlit Cloud muestra un botón para
  // despertarla ("Yes, get this app back up!" o similar). Si existe, lo
  // clickeamos; si no existe (app ya despierta), seguimos sin problema.
  const wakeButton = page.getByRole("button", { name: /get this app back up|wake/i });
  if (await wakeButton.count()) {
    await wakeButton.first().click();
    await page.waitForTimeout(15000);
  }

  // Deja un momento la sesión abierta para que la app termine de cargar
  // por completo (widgets, WebSocket) antes de cerrar.
  await page.waitForTimeout(5000);

  await browser.close();
  console.log("Visita completada.");
})().catch((err) => {
  console.error("Error visitando la app:", err);
  process.exit(1);
});
