// Optional RUNTIME override of the backend API base, for hosts where you cannot
// set build-time environment variables. It is read before VITE_API_BASE_URL.
//
// Deliberately left commented out. An earlier version shipped a placeholder
// URL, which meant any deploy that forgot to edit it pointed the app at a
// hostname that does not exist — a confusing failure. With this commented, the
// app falls back to VITE_API_BASE_URL and then to /api.
//
// On Vercel or Static Web Apps, prefer setting VITE_API_BASE_URL at build time.
// Uncomment and edit only if you need to change the backend without rebuilding:
//
// window.__API_BASE__ = 'https://your-backend.azurewebsites.net/api'
