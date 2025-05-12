import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)
load_dotenv(override=True)

app_name = "Lotse"
company_dir = "Kubernetes"

HOME_PATH = None
if os.name == "nt":
    base_path = Path(os.environ.get('PROGRAMDATA', 'C:\\ProgramData'))
    HOME_PATH = Path(base_path / company_dir / app_name)
elif os.name == "posix":
    HOME_PATH = Path("/var") / company_dir / app_name
else:
    HOME_PATH = Path.home() / company_dir / app_name

PACKAGES_ROOT = os.path.join(HOME_PATH, "packages")
if not os.path.exists(PACKAGES_ROOT):
    os.makedirs(PACKAGES_ROOT)

VENVS_ROOT = os.path.join(HOME_PATH, "venvs")
if not os.path.exists(VENVS_ROOT):
    os.makedirs(VENVS_ROOT)

OPENAPI_PREFIX_PATH = os.getenv("OPENAPI_PREFIX_PATH", "/api")
API_VERSION = os.getenv("API_VERSION", "0.1.0")
APP_NAME = os.getenv("APP_NAME", "Lotse")

POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB = os.getenv("POSTGRES_DB")
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"

ACTIVEMQ_ACTIVE = os.getenv("ACTIVEMQ_ACTIVE", "false").lower() == "true"
ACTIVEMQ_HOST = os.getenv("ACTIVEMQ_HOST", "localhost")
ACTIVEMQ_PORT = int(os.getenv("ACTIVEMQ_PORT", "61613"))
ACTIVEMQ_USER = os.getenv("ACTIVEMQ_USER", "admin")
ACTIVEMQ_PASSWORD = os.getenv("ACTIVEMQ_PASSWORD", "password")
ACTIVEMQ_QUEUE_NAME = os.getenv("ACTIVEMQ_QUEUE_NAME", "default_queue")

GLOBAL_TASK_TIMEOUT_SECONDS = int(os.getenv("GLOBAL_STASK_TIMEOUT_SECONDS", "3600"))  # 1 hour

K8S_NAMESPACE = os.getenv("K8S_NAMESPACE", "test")

# to get a string like this run:
# openssl rand -hex 32
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "secret")

IS_DEBUG = os.getenv("VSCODE_DEBUG_MODE", "false").lower() == "true"
ENABLE_AUTH = os.getenv("ENABLE_AUTH", "true").lower() == "true"

LDAP_SERVER = os.getenv('LDAP_SERVER')
LDAP_ROOT_DN = os.getenv('LDAP_ROOT_DN')
LDAP_DOMAIN = os.getenv('LDAP_DOMAIN')
