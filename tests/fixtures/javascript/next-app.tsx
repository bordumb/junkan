// Next.js application with NEXT_PUBLIC_ env vars
import React from 'react';

// Server-side env vars
const apiSecret = process.env.API_SECRET;
const databaseUrl = process.env.DATABASE_URL;

// Client-side env vars (NEXT_PUBLIC_ prefix)
const publicApiUrl = process.env.NEXT_PUBLIC_API_URL;
const publicAppName = process.env.NEXT_PUBLIC_APP_NAME;
const publicAnalyticsId = process.env.NEXT_PUBLIC_ANALYTICS_ID;

export default function App() {
  return (
    <div>
      <h1>{process.env.NEXT_PUBLIC_APP_NAME}</h1>
      <p>API: {process.env.NEXT_PUBLIC_API_URL}</p>
    </div>
  );
}

export async function getServerSideProps() {
  // Server-side only
  const data = await fetch(process.env.INTERNAL_API_URL!);
  return { props: { data } };
}
