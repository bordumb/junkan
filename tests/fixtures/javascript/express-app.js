// Express.js application with CommonJS require
require('dotenv').config();

const express = require('express');
const app = express();

// Environment variables
const PORT = process.env.PORT || 3000;
const NODE_ENV = process.env.NODE_ENV || 'development';
const DATABASE_URL = process.env.DATABASE_URL;
const REDIS_HOST = process.env.REDIS_HOST;
const JWT_SECRET = process.env.JWT_SECRET;

// Destructured env vars
const {
  AWS_ACCESS_KEY_ID,
  AWS_SECRET_ACCESS_KEY,
  S3_BUCKET
} = process.env;

app.get('/health', (req, res) => {
  res.json({ status: 'ok', env: NODE_ENV });
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});

module.exports = app;
