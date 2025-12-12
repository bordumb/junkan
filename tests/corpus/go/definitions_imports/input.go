package main

// 1. Factored Import Block
import (
	"fmt"
	"net/http"
	
	// External package
	"github.com/gin-gonic/gin"
	
	// Aliased package
	utils "github.com/myorg/pkg/utils"
)

// 2. Single Line Import
import "time"

// 3. Struct Definition (Exported)
type User struct {
	ID    string
	Email string
}

// 4. Interface Definition (Unexported)
type userRepository interface {
	FindByID(id string) (*User, error)
}

// 5. Function Definition
func main() {
	r := gin.Default()
	r.Run()
}

// 6. Method Definition on Struct
func (u *User) Display() string {
	return fmt.Sprintf("User: %s", u.Email)
}

// 7. Method definition with value receiver
func (u User) Validate() bool {
	return u.Email != ""
}