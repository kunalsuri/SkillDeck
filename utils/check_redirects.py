#!/usr/bin/env python3
import requests

def check_redirects():
    """
    Checks HTTP redirects and final destination URLs for target paths.
    """
    urls = [
        "https://github.com/skills",
        "https://github.com/skills/skills",
        "https://github.com/github/skills",
        "https://github.com/skills/exercise-creator",
        "https://github.com/skills/secure-code-game"
    ]

    print("Checking redirects...")
    for url in urls:
        try:
            # Send a HEAD request allowing redirects to see the ultimate destination
            response = requests.head(url, allow_redirects=True, timeout=10)
            print(f"URL: {url}")
            print(f"  Status: {response.status_code}")
            print(f"  Final Destination: {response.url}")
        except Exception as e:
            print(f"URL: {url} -> [ERROR] {e}")

if __name__ == "__main__":
    check_redirects()
