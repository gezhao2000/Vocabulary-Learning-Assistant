#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os

# Add the current directory to the path so we can import Vocabulary
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from Vocabulary import PDFWordExtractor, LocalDictionary

def test_categorization():
    """测试单词分类逻辑"""
    
    # 模拟PDF文本内容
    test_text = """
    单词分类
    
    认知词汇
    动物：cat dog bird fish horse cow pig sheep chicken elephant tiger lion
    颜色：red blue green yellow black white pink purple orange brown
    数字：one two three four five six seven eight nine ten
    
    派生词汇
    beautiful wonderful colorful helpful careful useful powerful
    quickly slowly carefully happily sadly angrily quietly loudly
    
    写作词汇
    however therefore moreover furthermore nevertheless meanwhile
    although because since while when where why how
    """
    
    print("测试文本:")
    print(test_text)
    print("=" * 50)
    
    # 测试提取逻辑
    words_with_categories = PDFWordExtractor._extract_from_table(test_text)
    
    print(f"\n提取结果:")
    print(f"总共提取到 {len(words_with_categories)} 个单词")
    
    # 按分类统计
    categories = {}
    for word_data in words_with_categories:
        category = word_data['category']
        if category not in categories:
            categories[category] = []
        categories[category].append(word_data['word'])
    
    print(f"\n分类统计:")
    for category, words in categories.items():
        print(f"分类 '{category}': {len(words)} 个单词")
        print(f"  单词: {words}")
        print()

if __name__ == "__main__":
    test_categorization() 