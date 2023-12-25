import pandas as pd
import argparse

def check_and_add_entry(file_path, host, database, username, password):
    # Read the existing CSV file
    try:
        df = pd.read_csv(file_path, sep=';', header=None, names=['host', 'database', 'username', 'password'])
    except FileNotFoundError:
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
