package com.example.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.env.Environment;

/**
 * Robust test case for Java Environment Variable extraction.
 * Covers: System.getenv, System.getProperty, Spring @Value, Environment abstraction.
 */
public class AppConfig {

    // 1. Standard System.getenv
    private static final String AWS_REGION = System.getenv("AWS_REGION");
    
    // 2. System.getenv with extra whitespace
    private final String dbHost = System.getenv( "DATABASE_HOST" );

    // 3. System.getProperty
    private String appVersion = System.getProperty("APP_VERSION");

    // 4. Spring @Value with simple variable
    @Value("${KAFKA_BROKERS}")
    private String kafkaBrokers;

    // 5. Spring @Value with default value (colon separator)
    @Value("${REDIS_PORT:6379}")
    private int redisPort;

    // 6. Spring @Value with whitespace around braces
    @Value( "${ FEATURE_FLAGS_ENABLED }" )
    private boolean featureFlags;

    // 7. Spring Environment abstraction
    public void configure(Environment env) {
        String secret = env.getProperty("API_SECRET_KEY");
        String timeout = env.getProperty( "REQUEST_TIMEOUT" );
    }

    // False Positives / Ignore cases
    public void invalidCalls() {
        // Should ignore variables inside comments
        // System.getenv("IGNORED_VAR");
        
        // Should ignore invalid variable names (spaces, empty)
        System.getenv("NOT A VAR");
        System.getenv("");
    }
}