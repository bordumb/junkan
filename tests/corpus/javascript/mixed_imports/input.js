// CommonJS Require
const logger = require('./utils/logger');
const { dbConfig } = require('../config/database');

// Dynamic Import (Async)
async function loadPlugin(pluginName) {
  if (pluginName === 'auth') {
    const auth = await import('./plugins/auth.js');
    return auth;
  }
}

// Side-effect import
require('dotenv').config();

class App {
  constructor() {
    this.db = dbConfig;
  }
}

module.exports = App;