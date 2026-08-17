"""The smallest argv the backup CLI accepts, shared by every test that drives it."""

REQUIRED_PAIRS = [
    ("--compose-dir", "/compose"),
    ("--backups-dir", "/backups"),
    ("--repo-name", "stack"),
    ("--databases-csv", "/etc/baudolo/databases.csv"),
]
REQUIRED = [arg for pair in REQUIRED_PAIRS for arg in pair]
BASE_ARGV = ["baudolo", *REQUIRED]
