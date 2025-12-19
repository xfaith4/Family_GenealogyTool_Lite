"""
Example client for /api/import/rmtree demonstrating the expected multipart upload.

Usage:
    python scripts/upload_rmtree_example.py /path/to/tree.rmtree
    python scripts/upload_rmtree_example.py /path/to/backup.rmbackup
"""
import sys
import requests


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/upload_rmtree_example.py <path to .rmtree or .rmbackup>")
        sys.exit(1)

    file_path = sys.argv[1]
    with open(file_path, "rb") as fh:
        resp = requests.post("http://localhost:3001/api/import/rmtree", files={"file": fh})
    print(resp.status_code)
    try:
        print(resp.json())
    except Exception:
        print(resp.text)


if __name__ == "__main__":
    main()
