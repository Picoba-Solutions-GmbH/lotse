import logging

from ldap3 import (ALL, ALL_ATTRIBUTES, SIMPLE, SUBTREE, SYNC, Connection,
                   Server)

from src.utils import config

logger = logging.getLogger(__name__)


def get_ldap_config() -> tuple[str, str, str]:
    if not all([config.LDAP_SERVER, config.LDAP_ROOT_DN, config.LDAP_DOMAIN]):
        raise ValueError(
            "LDAP configuration is incomplete. "
            "Please check LDAP_SERVER, LDAP_ROOT_DN, and LDAP_DOMAIN environment variables."
        )

    assert config.LDAP_SERVER is not None
    assert config.LDAP_ROOT_DN is not None
    assert config.LDAP_DOMAIN is not None

    return config.LDAP_SERVER, config.LDAP_ROOT_DN, config.LDAP_DOMAIN


def login(user_name: str, password: str) -> bool:
    try:
        server_url, root_dn, domain = get_ldap_config()
    except ValueError as e:
        logger.error(f"LDAP configuration error: {str(e)}")
        return False

    logger.info(f"User {user_name} is trying to authenticate...")

    ldap_user_name = f'{domain}\\{user_name}'
    server = Server(server_url, get_info=ALL)
    connection = Connection(
        server,
        user=ldap_user_name,
        password=password,
        authentication=SIMPLE,
        check_names=True,
        client_strategy=SYNC
    )
    try:
        if not connection.bind():
            logger.info(f"Logging to active directory failed for user {user_name}")
            return False
    except Exception as e:
        logger.info(f"Logging to active directory failed for user {user_name}")
        logger.exception(e)
        return False

    search_filter = f"(sAMAccountName={user_name})"
    connection.search(
        search_base=root_dn,
        search_filter=search_filter,
        search_scope=SUBTREE,
        attributes=ALL_ATTRIBUTES
    )

    return len(connection.entries) > 0
