import pandas as pd
import argparse
import os

def check_and_add_entry(file_path, host, database, username, password):
    # Check if the file exists and is not empty
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        # Read the existing CSV file with header
        df = pd.read_csv(file_path, sep=';')
    else:
        # Create a new DataFrame with columns if file does not exist
        df = pd.DataFrame(columns=['host', 'database', 'username', 'password'])

    # Check if the entry exists and remove it
    mask = (df['host'] == host) & (df['database'] == database) & (df['username'] == username)
    if not df[mask].empty:
        print("Replacing existing entry.")
        df = df[~mask]
    else:
        print("Adding new entry.")

    # Add (or replace) the entry
    new_entry = {'host': host, 'database': database, 'username': username, 'password': password}
    df = df.append(new_entry, ignore_index=True)

    # Save the updated CSV file
    df.to_csv(file_path, sep=';', index=False)

def main():
    parser = argparse.ArgumentParser(description="Check and replace (or add) a database entry in a CSV file.")
    parser.add_argument("file_path", help="Path to the CSV file")
    parser.add_argument("host", help="Database host")
    parser.add_argument("database", help="Database name")
    parser.add_argument("username", help="Username")
    parser.add_argument("password", help="Password")

    args = parser.parse_args()

    check_and_add_entry(args.file_path, args.host, args.database, args.username, args.password)

if __name__ == "__main__":
    main()
