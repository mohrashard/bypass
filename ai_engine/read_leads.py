import json
import os
import sys

def main():
    try:
        path = os.path.join(os.path.dirname(__file__), "..", "lead_engine", "leads.json")
        with open(path, 'r', encoding='utf-8') as f:
            print(f.read())
    except Exception as e:
        print("[]")

if __name__ == "__main__":
    main()
