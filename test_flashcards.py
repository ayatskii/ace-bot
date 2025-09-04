#!/usr/bin/env python3
"""
Simple test script to verify flashcard functionality
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import db
from flashcard_handlers import parse_word_details

def test_database_functions():
    """Test basic database functionality"""
    print("🧪 Testing database functions...")
    
    # Test user vocabulary count
    test_user_id = 12345
    count = db.get_user_vocabulary_count(test_user_id)
    print(f"✅ User vocabulary count: {count}")
    
    # Test getting user vocabulary
    vocabulary = db.get_user_vocabulary(test_user_id, limit=10)
    print(f"✅ User vocabulary items: {len(vocabulary)}")
    
    return True

def test_word_parsing():
    """Test word detail parsing"""
    print("🧪 Testing word parsing...")
    
    sample_word_details = """
    🎯 VOCABULARY WORD OF THE DAY

    📝 Word: ubiquitous
    📖 Definition: existing or being everywhere at the same time
    🇷🇺 Translation: вездесущий, повсеместный
    💡 Example: Smartphones have become ubiquitous in modern society.
    """
    
    parsed = parse_word_details(sample_word_details)
    print(f"✅ Parsed word: {parsed}")
    
    expected_word = "ubiquitous"
    if parsed['word'] == expected_word:
        print("✅ Word parsing successful!")
        return True
    else:
        print(f"❌ Word parsing failed. Expected '{expected_word}', got '{parsed['word']}'")
        return False

def main():
    """Run all tests"""
    print("🚀 Starting flashcard tests...\n")
    
    tests = [
        test_database_functions,
        test_word_parsing,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
                print("✅ PASSED\n")
            else:
                print("❌ FAILED\n")
        except Exception as e:
            print(f"❌ ERROR: {e}\n")
    
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Flashcard system is ready.")
        return True
    else:
        print("⚠️ Some tests failed. Check the implementation.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
