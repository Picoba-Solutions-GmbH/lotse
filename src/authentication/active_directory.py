import logging
from dataclasses import dataclass

from ldap3 import ALL, SIMPLE, SUBTREE, SYNC, Connection, Server
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars

from src.utils import config

logger = logging.getLogger(__name__)


@dataclass
class LdapUser:
    user_name: str
    display_name: str | None
    email: str | None


def is_configured() -> bool:
    return all([config.LDAP_SERVER, config.LDAP_ROOT_DN, config.LDAP_DOMAIN])


def normalize_user_name(user_name: str) -> str:
    name = user_name.strip()
    if "\\" in name:
        name = name.split("\\", 1)[1]
    if "@" in name:
        name = name.split("@", 1)[0]
    return name.lower()


def _attribute(entry, name: str) -> str | None:
    if name not in entry.entry_attributes:
        return None
    value = entry[name].value
    return str(value) if value else None


def login(user_name: str, password: str) -> LdapUser | None:
    if not is_configured():
        return None

    user_name = normalize_user_name(user_name)
    if not user_name or not password:
        return None

    logger.info("User %s is trying to authenticate against the active directory...", user_name)
    ldap_user_name = f'{config.LDAP_DOMAIN}\\{user_name}'
    server = Server(config.LDAP_SERVER, get_info=ALL)
    connection = Connection(server,
                            user=ldap_user_name,
                            password=password,
                            authentication=SIMPLE,
                            check_names=True,
                            client_strategy=SYNC)
    try:
        if not connection.bind():
            logger.info("Logging to active directory failed for user %s", user_name)
            return None

        connection.search(
            search_base=config.LDAP_ROOT_DN,
            search_filter=f"(sAMAccountName={escape_filter_chars(user_name)})",
            search_scope=SUBTREE,
            attributes=["sAMAccountName", "displayName", "mail"])

        if len(connection.entries) == 0:
            logger.info("User %s not found in active directory", user_name)
            return None

        entry = connection.entries[0]
        account_name = _attribute(entry, "sAMAccountName") or user_name
        return LdapUser(
            user_name=account_name.lower(),
            display_name=_attribute(entry, "displayName"),
            email=_attribute(entry, "mail"),
        )
    except LDAPException:
        logger.exception("Logging to active directory failed for user %s", user_name)
        return None
    finally:
        try:
            connection.unbind()
        except LDAPException:
            pass
