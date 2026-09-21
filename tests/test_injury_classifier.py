#!/usr/bin/env python3
"""Unit test for the injury classifier agent in scrape_news.py"""

import os
import sys
sys.path.insert(0, "jobs")

from scrape_news import classify_injury_headline

TEST_HEADLINES = [
    # Should be TRUE - genuine injuries
    ("Harry Wilson ruled out for six weeks with quad injury", True),
    ("Dean Henderson ankle injury — out for Crystal Palace", True),
    ("Rashford doubt for United after training knock", True),
    ("Nikola Milenkovic hamstring — set to miss several weeks", True),
    ("Kenny Tete concussion — unavailable for Fulham", True),
    
    # Should be FALSE - not injuries
    ("Should Haaland's goal have been ruled out?", False),
    ("Dean Henderson fit and available for Crystal Palace", False),
    ("Joe Gomez back from injury and in contention", False),
    ("Brighton 3-0 Arsenal — match report", False),
    ("Salah scores twice as Liverpool cruise to victory", False),
    ("Premier League clarifies controversial goal after star ruled offside", False),
]

def main():
    print("Testing injury classifier agent...\n")
    correct = 0
    total = len(TEST_HEADLINES)
    
    for headline, expected in TEST_HEADLINES:
        result = classify_injury_headline(headline)
        status = "✅" if result == expected else "❌"
        if result == expected:
            correct += 1
        print(f"{status} [{result}] expected [{expected}]")
        print(f"   {headline[:80]}")
        print()
    
    print(f"Result: {correct}/{total} correct")

if __name__ == "__main__":
    main()
