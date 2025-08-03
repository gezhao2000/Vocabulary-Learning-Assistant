#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re

def extract_chinese_phrase(line):
    """从一行文本中提取开头的中文短语"""
    # 匹配行开头的中文字符序列
    chinese_pattern = r'^[\u4e00-\u9fff]+'
    match = re.search(chinese_pattern, line)
    if match:
        return match.group().strip()
    return ""

def extract_english_words(line):
    """从一行文本中提取英文单词"""
    # 提取英文单词（3个字母以上）
    word_pattern = r'\b[a-zA-Z]{3,}\b'
    words = re.findall(word_pattern, line)
    
    # 过滤常见短词
    common_words = {
        'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one', 'our', 'out', 'day',
        'get', 'has', 'him', 'his', 'how', 'man', 'new', 'now', 'old', 'see', 'two', 'way', 'who', 'boy', 'did', 'its',
        'let', 'put', 'say', 'she', 'too', 'use', 'may', 'any', 'day', 'way', 'key', 'pay', 'run', 'set', 'try', 'win'
    }
    
    filtered_words = [word.lower() for word in words if word.lower() not in common_words]
    return filtered_words

def extract_from_table(text):
    """从表格文本中提取单词和分类（认知词汇按行分类，派生词汇和写作词汇统一分类）"""
    words_with_categories = []
    
    # 分割文本行
    lines = text.split('\n')
    current_category = "未分类"
    current_section = ""  # 当前处理的部分：认知词汇、派生词汇、写作词汇
    found_word_category = False  # 标记是否找到"单词分类"
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 检查是否找到"单词分类"关键词
        if "单词分类" in line:
            found_word_category = True
            print("找到'单词分类'关键词，开始处理表格")
            continue
        
        # 只有在找到"单词分类"后才开始处理
        if not found_word_category:
            continue
        
        # 检测主要分类标题（认知词汇、派生词汇、写作词汇）
        if "认知词汇" in line:
            current_section = "认知词汇"
            print(f"检测到部分: {current_section}")
            continue
        elif "派生词汇" in line:
            current_section = "派生词汇"
            print(f"检测到部分: {current_section}")
            continue
        elif "写作词汇" in line:
            current_section = "写作词汇"
            print(f"检测到部分: {current_section}")
            continue
            
        # 处理认知词汇部分
        if current_section == "认知词汇":
            # 提取行开头的中文短语作为类别名称
            chinese_phrase = extract_chinese_phrase(line)
            if chinese_phrase:
                current_category = f"认知词汇-{chinese_phrase}"
                print(f"设置认知词汇类别: {current_category}")
            
            # 提取英文单词（无论是否有中文短语）
            english_words = extract_english_words(line)
            if english_words:
                print(f"认知词汇部分提取单词: {english_words} -> 类别: {current_category}")
                for word in english_words:
                    words_with_categories.append({
                        'word': word.lower(),
                        'category': current_category,
                        'definition': '',
                        'pronunciation': ''
                    })
        
        # 处理派生词汇和写作词汇部分
        elif current_section in ["派生词汇", "写作词汇"]:
            # 确保类别已设置
            if current_category != current_section:
                current_category = current_section
                print(f"设置{current_section}类别: {current_category}")
            
            # 提取英文单词
            english_words = extract_english_words(line)
            if english_words:
                print(f"{current_section}部分提取单词: {english_words} -> 类别: {current_category}")
                for word in english_words:
                    words_with_categories.append({
                        'word': word.lower(),
                        'category': current_category,
                        'definition': '',
                        'pronunciation': ''
                    })
    
    # 调试输出：显示提取的单词和分类
    print(f"提取到 {len(words_with_categories)} 个单词")
    categories = {}
    for word_data in words_with_categories:
        category = word_data['category']
        if category not in categories:
            categories[category] = []
        categories[category].append(word_data['word'])
    
    for category, words in categories.items():
        print(f"分类 '{category}': {len(words)} 个单词 - {words[:5]}...")  # 只显示前5个单词
    
    return words_with_categories

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
    words_with_categories = extract_from_table(test_text)
    
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