package com.example.service;

// 1. Standard Java Import
import java.util.List;
import java.util.Map;

// 2. External Library Import
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

// 3. Static Import
import static java.util.Collections.emptyList;

/**
 * Test case for Java Definitions (Classes, Interfaces, Records) and Imports.
 */
public class UserService implements IUserService {
    
    private static final Logger logger = LoggerFactory.getLogger(UserService.class);

    // 4. Inner Record definition
    public record UserDto(String id, String email) {}

    public void processUsers() {
        // Local logic
    }
}

// 5. Interface Definition in same file
interface IUserService {
    void processUsers();
}

// 6. Enum Definition
enum UserStatus {
    ACTIVE, INACTIVE
}