"""The migrations logger. Its lines also go to stderr, because migrations change stored data."""

import logging

MIGRATION_LOG = "neoaprs.migrations"
log = logging.getLogger(MIGRATION_LOG)
