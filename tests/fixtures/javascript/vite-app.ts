// Vite application with import.meta.env

// Vite-specific env vars
const apiUrl = import.meta.env.VITE_API_URL;
const appTitle = import.meta.env.VITE_APP_TITLE;
const analyticsKey = import.meta.env.VITE_ANALYTICS_KEY;
const debugMode = import.meta.env.VITE_DEBUG_MODE;

// Built-in Vite env vars
const mode = import.meta.env.MODE;
const isDev = import.meta.env.DEV;
const isProd = import.meta.env.PROD;

export const config = {
  apiUrl: import.meta.env.VITE_API_URL,
  wsUrl: import.meta.env.VITE_WS_URL,
  environment: import.meta.env.MODE,
};
