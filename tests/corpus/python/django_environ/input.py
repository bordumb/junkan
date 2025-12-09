"""
django-environ patterns.
Standard for Django settings management.
"""
import environ

# Case 1: Initialization
env = environ.Env(
    DEBUG=(bool, False)
)

# Case 2: Reading variables via method calls
DEBUG = env("DEBUG")
SECRET_KEY = env.str("SECRET_KEY")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

# Case 3: Typed reads
DATABASE_URL = env.db("DATABASE_URL")
CACHE_URL = env.cache("CACHE_URL")
EMAIL_URL = env.email_url("EMAIL_URL")

# Case 4: Default values
# Note: default is often a kwarg
PAGE_SIZE = env.int("PAGE_SIZE", default=20)

# Case 5: Nested in dict (common in settings.py)
DATABASES = {
    'default': env.db('DATABASE_URL', default='sqlite:///db.sqlite3'),
    'replica': env.db('REPLICA_DATABASE_URL')
}