package config

import (
	"os"
	"syscall"
	"github.com/spf13/viper"
)

// Config holds the application configuration
type Config struct {
	Port string
}

func LoadConfig() *Config {
	// 1. Standard os.Getenv
	dbHost := os.Getenv("DB_HOST")

	// 2. Standard os.LookupEnv
	if dbPort, exists := os.LookupEnv("DB_PORT"); exists {
		println(dbPort)
	}

	// 3. Syscall (rarer but possible)
	path, _ := syscall.Getenv("PATH")

	// 4. Viper configuration (often maps to env vars)
	viper.SetEnvPrefix("APP")
	
	// Viper GetString
	apiKey := viper.GetString("API_KEY")
	
	// Viper GetInt
	maxRetries := viper.GetInt("MAX_RETRIES")
	
	// Viper GetBool
	debugMode := viper.GetBool("DEBUG_MODE")

	// 5. Whitespace variations
	region := os.Getenv( "AWS_REGION" )

	return &Config{Port: "8080"}
}

func FalsePositives() {
	// Should ignore comments
	// os.Getenv("IGNORED_VAR")
	
	// Should ignore lower case local variables that just look like env vars
	os.Getenv("not_an_env_var")
}