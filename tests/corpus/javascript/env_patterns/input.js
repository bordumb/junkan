// Basic process.env
const dbHost = process.env.DB_HOST;

// Destructuring
const { API_KEY, API_SECRET } = process.env;

// React App (Create React App pattern)
const apiUrl = process.env.REACT_APP_API_URL;

// Vite (import.meta.env pattern)
const viteApi = import.meta.env.VITE_API_ENDPOINT;

// Next.js Public
const nextPublic = process.env.NEXT_PUBLIC_ANALYTICS_ID;
