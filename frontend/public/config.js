// Runtime API base for the deployed Static Web App. Ignored on localhost so
// the Vite proxy handles /api during development.
if (!/localhost|127\.0\.0\.1/i.test(window.location.hostname)) {
  window.__API_BASE__ = 'https://<your-app-service>.azurewebsites.net/api'
}
