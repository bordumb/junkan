// TypeScript configuration with various env var patterns

// Pattern 1: process.env.VAR
const databaseHost = process.env.DATABASE_HOST;
const databasePort = process.env.DATABASE_PORT || '5432';

// Pattern 2: process.env["VAR"]
const apiKey = process.env["API_KEY"];
const secretKey = process.env['SECRET_KEY'];

// Pattern 3: Destructuring
const { 
  REDIS_URL, 
  CACHE_TTL,
  SESSION_SECRET 
} = process.env;

// Pattern 4: Destructuring with rename
const { 
  DATABASE_URL: dbUrl, 
  API_ENDPOINT: apiEndpoint 
} = process.env;

// Pattern 5: With nullish coalescing
const port = process.env.PORT ?? 3000;
const host = process.env.HOST ?? 'localhost';

// TypeScript interface for config
interface Config {
  database: {
    host: string;
    port: number;
    name: string;
  };
  redis: {
    url: string;
  };
}

export const config: Config = {
  database: {
    host: process.env.DB_HOST!,
    port: parseInt(process.env.DB_PORT || '5432'),
    name: process.env.DB_NAME!,
  },
  redis: {
    url: process.env.REDIS_URL!,
  },
};
