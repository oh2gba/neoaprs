"""The logger of the migrations: its lines go to stderr too, and so to the journal (daemon.py), because they change what the operator has stored. The steps (migrationsteps*.py) write to it,
and the runner (migrations.py), the daemon and the tools read it."""
import logging

MIGRATION_LOG = "neoaprs.migrations"
log = logging.getLogger(MIGRATION_LOG)
