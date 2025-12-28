import pandas as pd
import argparse
import os


def check_and_add_entry(file_path, instance, database, username, password):
    # Check if the file exists and is not empty
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        # Read the existing CSV file with header
        df = pd.read_csv(file_path, sep=";")
    else:
        # Create a new DataFrame with columns if file does not exist
        df = pd.DataFrame(columns=["instance", "database", "username", "password"])

    # Check if the entry exists and remove it
    mask = (
        (df["instance"] == instance)
        & (
            (df["database"] == database)
            | (((df["database"].isna()) | (df["database"] == "")) & (database == ""))
        )
        & (df["username"] == username)
    )

    if not df[mask].empty:
        print("Replacing existing entry.")
        df = df[~mask]
    else:
        print("Adding new entry.")

    # Create a new DataFrame for the new entry
    new_entry = pd.DataFrame(
        [
            {
                "instance": instance,
                "database": database,
                "username": username,
                "password": password,
            }
        ]
    )

    # Add (or replace) the entry using concat
    df = pd.concat([df, new_entry], ignore_index=True)

    # Save the updated CSV file
    df.to_csv(file_path, sep=";", index=False)


def main():
    parser = argparse.ArgumentParser(
        description="Check and replace (or add) a database entry in a CSV file."
    )
    parser.add_argument("file_path", help="Path to the CSV file")
    parser.add_argument("instance", help="Database instance")
    parser.add_argument("database", help="Database name")
    parser.add_argument("username", help="Username")
    parser.add_argument("password", nargs="?", default="", help="Password (optional)")

    args = parser.parse_args()

    check_and_add_entry(
        args.file_path, args.instance, args.database, args.username, args.password
    )


if __name__ == "__main__":
    main()
