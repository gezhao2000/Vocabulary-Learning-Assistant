import os
import re
import json
import random
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import PyPDF2
import requests
import time
import hashlib

from datetime import datetime, timedelta
import sqlite3

# 创建全局本地词典实例
local_dict = None

class WordDatabase:
    """单词数据库管理类"""

    def __init__(self, db_name="vocabulary.db"):
        self.db_name = db_name
        self.init_database()

    def init_database(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        # 创建单词表
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS words (
                                                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                            word TEXT UNIQUE NOT NULL,
                                                            definition TEXT,
                                                            phrases TEXT,
                                                            category TEXT,
                                                            difficulty INTEGER DEFAULT 1,
                                                            correct_count INTEGER DEFAULT 0,
                                                            wrong_count INTEGER DEFAULT 0,
                                                            last_reviewed DATE,
                                                            created_date DATE DEFAULT CURRENT_DATE
                       )
                       ''')

        # 创建学习记录表
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS study_records (
                                                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                                    word TEXT,
                                                                    result TEXT,
                                                                    study_date DATE DEFAULT CURRENT_DATE,
                                                                    response_time INTEGER
                       )
                       ''')

        conn.commit()
        conn.close()

    def add_word(self, word, definition="", phrases=None, category=""):
        """添加单词到数据库"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        try:
            if phrases is None:
                phrases = ""
            phrases_str = json.dumps(phrases, ensure_ascii=False)
            cursor.execute('''
                           INSERT OR IGNORE INTO words (word, definition, phrases, category)
                VALUES (?, ?, ?, ?)
                           ''', (word.lower(), definition, phrases_str, category))
            conn.commit()
            return True
        except Exception as e:
            print(f"添加单词失败: {e}")
            return False
        finally:
            conn.close()

    def add_or_update_word(self, word, definition="", phrases=None, category=""):
        """添加或更新单词到数据库（如果单词已存在则更新释义和短语）"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        try:
            if phrases is None:
                phrases = ""
            
            # 确保phrases是字符串格式
            if isinstance(phrases, list):
                phrases_str = json.dumps(phrases, ensure_ascii=False)
            elif not isinstance(phrases, str):
                phrases_str = str(phrases)
            else:
                phrases_str = phrases
            
            # 检查单词是否已存在
            cursor.execute('SELECT word FROM words WHERE word = ?', (word.lower(),))
            existing_word = cursor.fetchone()
            
            if existing_word:
                # 单词已存在，更新释义和短语
                cursor.execute('''
                               UPDATE words 
                               SET definition = ?, phrases = ?, category = ?
                               WHERE word = ?
                               ''', (definition, phrases_str, category, word.lower()))
                conn.commit()
                return "updated"
            else:
                # 单词不存在，插入新单词
                cursor.execute('''
                               INSERT INTO words (word, definition, phrases, category)
                               VALUES (?, ?, ?, ?)
                               ''', (word.lower(), definition, phrases_str, category))
                conn.commit()
                return "inserted"
        except Exception as e:
            print(f"添加或更新单词失败: {e}")
            print(f"参数类型 - word: {type(word)}, definition: {type(definition)}, phrases: {type(phrases)}")
            return False
        finally:
            conn.close()

    def get_words_for_study(self, limit=20, category=None):
        """获取用于学习的单词"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        query = '''
                SELECT word, definition, phrases, difficulty, correct_count, wrong_count
                FROM words
                WHERE 1=1 \
                '''
        params = []

        if category:
            query += " AND category = ?"
            params.append(category)

        # 优先选择错误率高的单词
        query += '''
            ORDER BY 
                CASE WHEN (correct_count + wrong_count) = 0 THEN 0
                     ELSE CAST(wrong_count AS FLOAT) / (correct_count + wrong_count)
                END DESC,
                last_reviewed ASC NULLS FIRST
            LIMIT ?
        '''
        params.append(limit)

        cursor.execute(query, params)
        words = cursor.fetchall()
        conn.close()

        # 处理phrases字段
        processed_words = []
        for word_data in words:
            word, definition, phrases_str, difficulty, correct_count, wrong_count = word_data
            try:
                phrases = json.loads(phrases_str) if phrases_str else []
            except:
                phrases = []
            processed_words.append((word, definition, phrases, difficulty, correct_count, wrong_count))

        return processed_words

    def update_word_stats(self, word, is_correct, response_time=0):
        """更新单词统计信息"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        if is_correct:
            cursor.execute('''
                           UPDATE words
                           SET correct_count = correct_count + 1, last_reviewed = CURRENT_DATE
                           WHERE word = ?
                           ''', (word.lower(),))
        else:
            cursor.execute('''
                           UPDATE words
                           SET wrong_count = wrong_count + 1, last_reviewed = CURRENT_DATE
                           WHERE word = ?
                           ''', (word.lower(),))

        # 记录学习记录
        result = "correct" if is_correct else "wrong"
        cursor.execute('''
                       INSERT INTO study_records (word, result, response_time)
                       VALUES (?, ?, ?)
                       ''', (word.lower(), result, response_time))

        conn.commit()
        conn.close()

    def reset_database(self):
        """重置数据库（删除所有数据并重新初始化）"""
        try:
            # 关闭所有数据库连接
            import sqlite3
            
            # 尝试连接并关闭，确保没有活跃连接
            try:
                conn = sqlite3.connect(self.db_name)
                conn.close()
            except:
                pass
            
            # 删除数据库文件
            if os.path.exists(self.db_name):
                os.remove(self.db_name)
                print(f"已删除数据库文件: {self.db_name}")
            
            # 重新初始化数据库
            self.init_database()
            print("数据库已重新初始化")
            
            return True
            
        except Exception as e:
            print(f"重置数据库失败: {e}")
            return False

class PDFWordExtractor:
    """PDF单词提取器"""

    @staticmethod
    def extract_words_from_pdf(pdf_path):
        """从PDF文件中提取单词（优化版：专注于第一页表格，在找到'单词分类'后开始处理）"""
        words_with_categories = []

        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                
                # 只处理第一页
                if len(pdf_reader.pages) > 0:
                    first_page = pdf_reader.pages[0]
                    text = first_page.extract_text()
                    
                    # 提取单词和分类
                    words_with_categories = PDFWordExtractor._extract_from_table(text)

        except Exception as e:
            print(f"PDF读取错误: {e}")

        return words_with_categories

    @staticmethod
    def _extract_from_table(text):
        """从表格文本中提取单词和分类（认知词汇按行分类，派生词汇和写作词汇统一分类）"""
        words_with_categories = []
        
        # 分割文本行
        lines = text.split('\n')
        current_category = ""  # 初始类别为空
        current_section = ""  # 当前处理的部分：认知词汇、派生词汇、写作词汇
        found_word_category = False  # 标记是否找到"单词分类"
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 检查是否找到"单词分类"关键词
            if "单词分类" in line:
                found_word_category = True
                continue
            
            # 只有在找到"单词分类"后才开始处理
            if not found_word_category:
                continue
            
            # 检测主要分类标题（认知词汇、派生词汇、写作词汇）
            if "认知词汇" in line:
                current_section = "认知词汇"
                continue
            elif "派生词汇" in line:
                current_section = "派生词汇"
                continue
            elif "写作词汇" in line:
                current_section = "写作词汇"
                continue
            elif "Round1" in line:
                return words_with_categories
                
            # 处理认知词汇部分
            if current_section == "认知词汇":
                # 提取行开头的中文短语作为类别名称
                chinese_phrase = PDFWordExtractor._extract_chinese_phrase(line)
                if chinese_phrase:
                    # 如果找到新的中文短语，更新当前类别
                    current_category = f"认知词汇-{chinese_phrase}"
                
                # 提取英文单词（无论是否有中文短语）
                english_words = PDFWordExtractor._extract_english_words(line)
                if english_words and current_category:  # 只有当类别已设置时才添加单词
                    for word in english_words:
                        words_with_categories.append({
                            'word': word.lower(),
                            'category': current_category,
                            'definition': '',  # 稍后通过API获取
                            'phrases': []
                        })
            
            # 处理派生词汇和写作词汇部分
            elif current_section in ["派生词汇", "写作词汇"]:
                # 确保类别已设置
                if current_category != current_section:
                    current_category = current_section
                
                # 提取英文单词
                english_words = PDFWordExtractor._extract_english_words(line)
                if english_words and current_category:  # 只有当类别已设置时才添加单词
                    for word in english_words:
                        words_with_categories.append({
                            'word': word.lower(),
                            'category': current_category,
                            'definition': '',  # 稍后通过API获取
                            'phrases': []
                        })
        
        return words_with_categories

    @staticmethod
    def _is_category_header(line):
        """判断是否为分类标题行"""
        # 中文分类标题的特征
        category_patterns = [
            r'^[^a-zA-Z]*[：:]\s*$',  # 以冒号结尾
            r'^[^a-zA-Z]*词汇[^a-zA-Z]*$',  # 包含"词汇"字样
            r'^[^a-zA-Z]*分类[^a-zA-Z]*$',  # 包含"分类"字样
            r'^[^a-zA-Z]*认知[^a-zA-Z]*$',  # 包含"认知"字样
            r'^[^a-zA-Z]*派生[^a-zA-Z]*$',  # 包含"派生"字样
            r'^[^a-zA-Z]*写作[^a-zA-Z]*$',  # 包含"写作"字样
        ]
        
        for pattern in category_patterns:
            if re.search(pattern, line):
                return True
        return False

    @staticmethod
    def _extract_chinese_phrase(line):
        """从一行文本中提取开头的中文短语"""
        # 匹配行开头的中文字符序列
        chinese_pattern = r'^[\u4e00-\u9fff]+'
        match = re.search(chinese_pattern, line)
        if match:
            return match.group().strip()
        return ""

    @staticmethod
    def _extract_english_words(line):
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

    @staticmethod
    def extract_words_with_translation(pdf_path):
        """从PDF提取单词并自动获取翻译"""
        words_with_categories = PDFWordExtractor.extract_words_from_pdf(pdf_path)
        
        # 为每个单词获取翻译
        try:
            for i, word_data in enumerate(words_with_categories):
                if local_dict is not None:
                    # 启用自动翻译功能
                    definition, phrases = local_dict.get_word_definition(word_data['word'], auto_translate=True)
                    word_data['definition'] = definition
                    word_data['phrases'] = phrases
                    
                    # 添加延迟以避免API请求过于频繁
                    if i > 0 and i % 5 == 0:  # 每5个单词暂停一下
                        time.sleep(0.5)
                else:
                    word_data['definition'] = ""
                    word_data['phrases'] = []
        except Exception as e:
            print(f"获取单词释义时出错: {e}")
            # 如果出错，设置默认值
            for word_data in words_with_categories:
                word_data['definition'] = ""
                word_data['phrases'] = []
        
        return words_with_categories

    @staticmethod
    def batch_extract_from_folder(folder_path):
        """批量从文件夹中的PDF提取单词（优化版）"""
        all_words = {}

        for filename in os.listdir(folder_path):
            if filename.lower().endswith('.pdf'):
                pdf_path = os.path.join(folder_path, filename)
                words_with_categories = PDFWordExtractor.extract_words_with_translation(pdf_path)
                
                # 按分类组织单词
                for word_data in words_with_categories:
                    category = word_data['category']
                    if category not in all_words:
                        all_words[category] = []
                    all_words[category].append(word_data)

        return all_words

    @staticmethod
    def extract_exercise_format(pdf_path):
        """提取练习题格式（用于生成练习）"""
        exercise_patterns = []
        
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                
                # 从第二页开始查找练习题
                for page_num in range(1, min(len(pdf_reader.pages), 5)):  # 只检查前5页
                    page = pdf_reader.pages[page_num]
                    text = page.extract_text()
                    
                    # 查找选择题格式
                    choice_pattern = r'(\d+\.\s*[a-zA-Z]+[^A-D]*?A\.[^B]*?B\.[^C]*?C\.[^D]*?D\.[^0-9]*)'
                    matches = re.findall(choice_pattern, text, re.DOTALL)
                    
                    for match in matches:
                        exercise_patterns.append(match)
                        
        except Exception as e:
            print(f"提取练习题格式错误: {e}")
            
        return exercise_patterns
        
class LocalDictionary:
    """本地词典类，提供单词释义查询功能"""

    def __init__(self, dict_file="gaokao_dictionary.json", db_file="dictionary.db"):
        self.dict_file = dict_file
        self.db_file = db_file
        self.dictionary = {}
        self.init_dictionary_database()
        self.load_dictionary()

    def init_dictionary_database(self):
        """初始化词典数据库"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # 创建词典表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS dictionary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word TEXT UNIQUE NOT NULL,
                    definition TEXT,
                    phrases TEXT,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            conn.close()
            print(f"词典数据库初始化完成: {self.db_file}")
        except Exception as e:
            print(f"初始化词典数据库失败: {e}")

    def load_dictionary(self):
        """加载词典（优先从数据库加载，如果数据库为空则从JSON文件加载）"""
        try:
            # 首先尝试从数据库加载
            db_dict = self.load_from_database()
            if db_dict:
                self.dictionary = db_dict
                print(f"从数据库加载词典，包含 {len(self.dictionary)} 个单词")
                return
            
            # 如果数据库为空，尝试从JSON文件加载
            if os.path.exists(self.dict_file):
                with open(self.dict_file, 'r', encoding='utf-8') as f:
                    self.dictionary = json.load(f)
                print(f"从JSON文件加载词典，包含 {len(self.dictionary)} 个单词")
                
                # 将JSON数据保存到数据库
                self.save_json_to_database()
            else:
                # 如果JSON文件也不存在，创建空词典
                self.dictionary = {}
                print("创建空词典")
                
        except Exception as e:
            print(f"加载词典失败: {e}")
            self.dictionary = {}

    def load_from_database(self):
        """从数据库加载词典"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('SELECT word, definition, phrases FROM dictionary')
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                return {}
            
            dictionary = {}
            for row in rows:
                word, definition, phrases_str = row
                try:
                    phrases = json.loads(phrases_str) if phrases_str else []
                except:
                    phrases = []
                
                dictionary[word] = {
                    'definition': definition or '',
                    'phrases': phrases
                }
            
            return dictionary
        except Exception as e:
            print(f"从数据库加载词典失败: {e}")
            return {}

    def save_json_to_database(self):
        """将JSON词典数据保存到数据库"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # 清空现有数据
            cursor.execute('DELETE FROM dictionary')
            
            # 插入新数据
            for word, info in self.dictionary.items():
                if isinstance(info, dict):
                    definition = info.get('definition', '')
                    phrases = info.get('phrases', [])
                    phrases_str = json.dumps(phrases, ensure_ascii=False)
                    
                    cursor.execute('''
                        INSERT INTO dictionary (word, definition, phrases)
                        VALUES (?, ?, ?)
                    ''', (word, definition, phrases_str))
            
            conn.commit()
            conn.close()
            print(f"成功将 {len(self.dictionary)} 个单词保存到数据库")
        except Exception as e:
            print(f"保存词典到数据库失败: {e}")

    def create_basic_dictionary(self):
        """创建基础词典（包含常见高考词汇）"""
        # 返回空词典，不再创建基础词典
        return {}

    def import_from_json_file(self, file_path):
        """从本地JSON文件导入词典"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 转换数据格式
            converted_dict = {}
            
            # 检查数据格式并转换
            if isinstance(data, list):
                # 如果是列表格式 - 支持新的词典格式
                for item in data:
                    if isinstance(item, dict):
                        word = None
                        definition = ""
                        phrases = ""
                        
                        # 获取单词
                        word = item.get('word', item.get('Word', item.get('name', '')))
                        
                        if word:
                            word = str(word).lower().strip()
                            
                            # 处理翻译数组格式
                            if 'translations' in item and isinstance(item['translations'], list):
                                translation_parts = []
                                for trans in item['translations']:
                                    if isinstance(trans, dict):
                                        trans_text = trans.get('translation', '')
                                        trans_type = trans.get('type', '')
                                        if trans_text:
                                            if trans_type:
                                                translation_parts.append(f"{trans_text} ({trans_type})")
                                            else:
                                                translation_parts.append(trans_text)
                                    elif isinstance(trans, str):
                                        translation_parts.append(trans)
                                
                                definition = '；'.join(translation_parts)
                            
                            # 处理短语
                            if 'phrases' in item and isinstance(item['phrases'], list):
                                phrase_parts = []
                                for phrase in item['phrases']:
                                    if isinstance(phrase, dict):
                                        phrase_text = phrase.get('phrase', '')
                                        phrase_trans = phrase.get('translation', '')
                                        if phrase_text and phrase_trans:
                                            phrase_parts.append(f"{phrase_text}: {phrase_trans}")
                                    elif isinstance(phrase, str):
                                        phrase_parts.append(phrase)
                                
                                phrases = '\n'.join(phrase_parts)

                            # 如果没有translations字段，尝试其他字段
                            if not definition:
                                for def_field in ['translation', 'Translation', 'definition', 'Definition', 'meaning', 'Meaning', 'chinese', 'Chinese']:
                                    if def_field in item:
                                        definition = str(item[def_field]).strip()
                                        break
                            
                            converted_dict[word] = {
                                'definition': definition,
                                'phrases': phrases
                            }
            
            elif isinstance(data, dict):
                # 如果是字典格式
                for word, info in data.items():
                    if isinstance(info, dict):
                        # 处理新的词典格式
                        definition = ""
                        phrases = ""
                        
                        # 处理翻译数组
                        if 'translations' in info and isinstance(info['translations'], list):
                            translation_parts = []
                            for trans in info['translations']:
                                if isinstance(trans, dict):
                                    trans_text = trans.get('translation', '')
                                    trans_type = trans.get('type', '')
                                    if trans_text:
                                        if trans_type:
                                            translation_parts.append(f"{trans_text} ({trans_type})")
                                        else:
                                            translation_parts.append(trans_text)
                                elif isinstance(trans, str):
                                    translation_parts.append(trans)
                            
                            definition = '；'.join(translation_parts)
                        
                        # 处理短语
                        if 'phrases' in info and isinstance(info['phrases'], list):
                            phrase_parts = []
                            for phrase in info['phrases']:
                                if isinstance(phrase, dict):
                                    phrase_text = phrase.get('phrase', '')
                                    phrase_trans = phrase.get('translation', '')
                                    if phrase_text and phrase_trans:
                                        phrase_parts.append(f"{phrase_text}: {phrase_trans}")
                                elif isinstance(phrase, str):
                                    phrase_parts.append(phrase)
                            
                            phrases = '\n'.join(phrase_parts)
                        
                        # 如果没有translations字段，使用传统字段
                        if not definition:
                            definition = str(info.get('definition', info.get('translation', ''))).strip()
                        
                        converted_dict[word.lower().strip()] = {
                            'definition': definition,
                            'phrases': phrases
                        }
                    elif isinstance(info, str):
                        # 如果值是字符串，作为释义
                        converted_dict[word.lower().strip()] = {
                            'definition': str(info).strip(),
                            'phrases': ""
                        }
            
            # 保存转换后的词典到数据库
            if converted_dict:
                self.dictionary.update(converted_dict)
                self.save_to_database(converted_dict)
                print(f"成功导入词典，包含 {len(converted_dict)} 个单词")
                return True
            else:
                print("词典文件格式不支持或为空")
                return False
                
        except Exception as e:
            print(f"导入词典文件失败: {e}")
            return False

    def get_word_definition(self, word, auto_translate=True):
        """获取单词定义"""
        word_lower = word.lower()
        if word_lower in self.dictionary:
            word_info = self.dictionary[word_lower]
            definition = word_info.get('definition', '')
            phrases = word_info.get('phrases', '')
            
            return definition if definition else "暂无释义", phrases
        
        # 如果本地词典中没有找到，且启用了自动翻译
        if auto_translate:
            try:
                # 创建在线翻译器实例
                translator = OnlineTranslator()
                definition, phrases = translator.translate_word(word)
                
                # 如果在线翻译成功，保存到本地词典
                if definition and definition != "暂无释义" and definition != word:
                    # 确保翻译结果有效
                    self.add_word(word, definition, phrases)
                    print(f"已通过在线翻译获取并保存单词 '{word}' 的释义: {definition}")
                    
                    # 立即保存到数据库
                    self.save_word_to_database(word_lower, definition, phrases)
                    
                    return definition, phrases
                else:
                    print(f"翻译结果无效或为空: {word} -> {definition}")
                    return "暂无释义", ""
            except Exception as e:
                print(f"在线翻译单词 '{word}' 失败: {e}")
                return "暂无释义", ""
        
        return "暂无释义", ""

    def add_word(self, word, definition, phrases=None):
        """添加单词到词典"""
        word_lower = word.lower()
        if phrases is None:
            phrases = ""
        
        # 确保短语是字符串格式
        if isinstance(phrases, list):
            phrases = json.dumps(phrases, ensure_ascii=False)
        elif not isinstance(phrases, str):
            phrases = str(phrases)
        
        # 更新内存中的词典
        self.dictionary[word_lower] = {
            'definition': definition,
            'phrases': phrases
        }
        
        # 保存到数据库
        self.save_word_to_database(word_lower, definition, phrases)
        
        print(f"单词 '{word}' 已添加到本地词典: {definition}")

    def save_word_to_database(self, word, definition, phrases):
        """保存单个单词到数据库"""
        try:
            # 确保phrases是字符串格式
            if isinstance(phrases, list):
                phrases = json.dumps(phrases, ensure_ascii=False)
            elif not isinstance(phrases, str):
                phrases = str(phrases)
            
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # 检查单词是否已存在
            cursor.execute('SELECT word FROM dictionary WHERE word = ?', (word,))
            existing_word = cursor.fetchone()
            
            # 使用INSERT OR REPLACE来支持更新现有单词
            cursor.execute('''
                INSERT OR REPLACE INTO dictionary (word, definition, phrases, updated_date)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (word, definition, phrases))
            
            conn.commit()
            conn.close()
            
            if existing_word:
                print(f"已更新单词 '{word}' 的释义到数据库")
            else:
                print(f"已插入单词 '{word}' 的释义到数据库")
                
        except Exception as e:
            print(f"保存单词 '{word}' 到数据库失败: {e}")
            print(f"参数类型 - word: {type(word)}, definition: {type(definition)}, phrases: {type(phrases)}")
            print(f"参数值 - word: {word}, definition: {definition}, phrases: {phrases}")

    def save_to_database(self, words_dict=None):
        """保存词典到数据库"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # 如果没有指定词典，使用当前词典
            if words_dict is None:
                words_dict = self.dictionary
            
            # 批量插入或更新
            for word, info in words_dict.items():
                if isinstance(info, dict):
                    definition = info.get('definition', '')
                    phrases = info.get('phrases', '')
                    
                    # 确保phrases是字符串格式
                    if isinstance(phrases, list):
                        phrases = json.dumps(phrases, ensure_ascii=False)
                    elif not isinstance(phrases, str):
                        phrases = str(phrases)
                    
                    cursor.execute('''
                        INSERT OR REPLACE INTO dictionary (word, definition, phrases, updated_date)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (word, definition, phrases))
            
            conn.commit()
            conn.close()
            print(f"成功保存 {len(words_dict)} 个单词到数据库")
        except Exception as e:
            print(f"保存词典到数据库失败: {e}")

    def save_dictionary(self):
        """保存词典到文件（兼容旧版本）"""
        try:
            with open(self.dict_file, 'w', encoding='utf-8') as f:
                json.dump(self.dictionary, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存词典失败: {e}")

    def get_dictionary_size(self):
        """获取词典大小"""
        return len(self.dictionary)

    def get_database_stats(self):
        """获取数据库统计信息"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # 获取总单词数
            cursor.execute('SELECT COUNT(*) FROM dictionary')
            total_words = cursor.fetchone()[0]
            
            # 获取最近添加的单词
            cursor.execute('''
                SELECT word, created_date 
                FROM dictionary 
                ORDER BY created_date DESC 
                LIMIT 5
            ''')
            recent_words = cursor.fetchall()
            
            # 获取最近更新的单词
            cursor.execute('''
                SELECT word, updated_date 
                FROM dictionary 
                ORDER BY updated_date DESC 
                LIMIT 5
            ''')
            updated_words = cursor.fetchall()
            
            conn.close()
            
            return {
                'total_words': total_words,
                'recent_words': recent_words,
                'updated_words': updated_words
            }
        except Exception as e:
            print(f"获取数据库统计信息失败: {e}")
            return {'total_words': 0, 'recent_words': [], 'updated_words': []}

class OnlineTranslator:
    """在线翻译API类"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # 百度翻译API配置信息
        self.APP_ID = '20250803002423036'
        self.SECRET_KEY = 'vIrOI041lyGHvFucedH8'
    
    def translate_word(self, word):
        """翻译单词（使用百度翻译API）"""
        try:
            # 使用百度翻译API
            chinese_translation = self._translate_with_baidu(word)
            if chinese_translation and chinese_translation != word:
                return chinese_translation, []
            
            # 如果百度翻译失败，返回空结果
            return "", []
            
        except Exception as e:
            print(f"在线翻译失败: {e}")
            return "", []
    
    def _translate_with_baidu(self, word):
        """使用百度翻译API翻译单词"""
        try:
            url = "http://api.fanyi.baidu.com/api/trans/vip/translate"
            salt = str(time.time())
            sign = hashlib.md5((self.APP_ID + word + salt + self.SECRET_KEY).encode('utf-8')).hexdigest()
            
            params = {
                'q': word,
                'from': 'en',
                'to': 'zh',
                'appid': self.APP_ID,
                'salt': salt,
                'sign': sign
            }
            
            response = self.session.get(url, params=params, timeout=10)
            result = response.json()
            
            # 添加错误处理和日志记录
            if 'trans_result' in result:
                translation = result['trans_result'][0]['dst']
                print(f"百度翻译成功: {word} -> {translation}")
                return translation
            else:
                # 打印错误信息和完整的API响应
                print(f"百度翻译API响应错误: {result}")
                return ""  # 如果翻译失败，返回空字符串
                
        except Exception as e:
            print(f"百度翻译失败: {e}")
            return ""





class WordAPI:
    """单词API接口，使用本地词典获取单词释义和发音"""

    @staticmethod
    def get_word_definition(word):
        """获取单词定义（使用本地词典）"""
        try:
            if local_dict is not None:
                return local_dict.get_word_definition(word)
            else:
                return "", ""
        except Exception as e:
            print(f"获取单词定义时出错: {e}")
            return "", ""

class VocabularyApp:
    """主应用程序类"""

    def __init__(self, root):
        self.root = root
        self.root.title("高中生单词背诵助手")
        self.root.geometry("800x600")
        self.root.configure(bg='#f0f0f0')

        self.db = WordDatabase()
        self.current_word = None
        self.current_options = []
        self.study_session = []
        self.current_index = 0
        self.correct_count = 0

        self.setup_ui()

    def setup_ui(self):
        """设置用户界面"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        title_label = ttk.Label(
            main_frame,
            text="单词背诵助手",
            font=("Arial", 24, "bold")
        )
        title_label.pack(pady=(0, 20))

        # 创建notebook用于选项卡
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        # 词库管理选项卡
        self.setup_vocabulary_tab(notebook)

        # 学习选项卡
        self.setup_study_tab(notebook)

        # 统计选项卡
        self.setup_stats_tab(notebook)

    def setup_vocabulary_tab(self, notebook):
        """设置词库管理选项卡"""
        vocab_frame = ttk.Frame(notebook, padding="10")
        notebook.add(vocab_frame, text="词库管理")

        # PDF导入区域
        import_frame = ttk.LabelFrame(vocab_frame, text="导入PDF单词", padding="10")
        import_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(
            import_frame,
            text="选择PDF文件",
            command=self.import_pdf_files
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            import_frame,
            text="批量导入文件夹",
            command=self.import_pdf_folder
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            import_frame,
            text="重置单词数据库",
            command=self.reset_word_database
        ).pack(side=tk.LEFT)

        # 单词列表
        list_frame = ttk.LabelFrame(vocab_frame, text="词库单词", padding="10")
        list_frame.pack(fill=tk.BOTH, expand=True)

        # 创建表格
        columns = ('单词', '释义', '分类', '正确率')
        self.word_tree = ttk.Treeview(list_frame, columns=columns, show='headings')

        for col in columns:
            self.word_tree.heading(col, text=col)
            self.word_tree.column(col, width=150)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.word_tree.yview)
        self.word_tree.configure(yscrollcommand=scrollbar.set)

        self.word_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 词典管理按钮
        dict_frame = ttk.LabelFrame(vocab_frame, text="词典管理", padding="10")
        dict_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(
            dict_frame,
            text="添加单词到词典",
            command=self.add_word_to_dictionary
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            dict_frame,
            text="查看词典信息",
            command=self.show_dictionary_info
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            dict_frame,
            text="导入词典文件",
            command=self.import_dictionary_file
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            dict_frame,
            text="重建基础词典",
            command=self.rebuild_dictionary
        ).pack(side=tk.LEFT)

        # 刷新按钮
        ttk.Button(vocab_frame, text="刷新列表", command=self.refresh_word_list).pack(pady=10)

    def setup_study_tab(self, notebook):
        """设置学习选项卡"""
        study_frame = ttk.Frame(notebook, padding="10")
        notebook.add(study_frame, text="开始学习")

        # 学习设置
        settings_frame = ttk.LabelFrame(study_frame, text="学习设置", padding="10")
        settings_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(settings_frame, text="单词数量:").pack(side=tk.LEFT)
        self.word_count_var = tk.StringVar(value="20")
        ttk.Entry(settings_frame, textvariable=self.word_count_var, width=10).pack(side=tk.LEFT, padx=5)

        ttk.Button(settings_frame, text="开始学习", command=self.start_study).pack(side=tk.LEFT, padx=10)
        
        # 添加生成练习题按钮
        ttk.Button(settings_frame, text="生成练习题", command=self.generate_exercises).pack(side=tk.LEFT, padx=10)

        # 学习区域
        self.study_area = ttk.Frame(study_frame)
        self.study_area.pack(fill=tk.BOTH, expand=True)

        self.setup_study_interface()

    def setup_study_interface(self):
        """设置学习界面"""
        # 创建主滚动框架
        self.main_canvas = tk.Canvas(self.study_area)
        scrollbar = ttk.Scrollbar(self.study_area, orient="vertical", command=self.main_canvas.yview)
        self.scrollable_frame = ttk.Frame(self.main_canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))
        )

        self.main_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.main_canvas.configure(yscrollcommand=scrollbar.set)

        # 进度显示
        self.progress_label = ttk.Label(
            self.scrollable_frame,
            text="点击'开始学习'开始背单词",
            font=("Arial", 14)
        )
        self.progress_label.pack(pady=10)

        # 单词显示
        self.word_label = ttk.Label(
            self.scrollable_frame,
            text="",
            font=("Arial", 32, "bold"),
            foreground="#2c3e50"
        )
        self.word_label.pack(pady=20)

        # 短语显示
        self.phrases_label = ttk.Label(
            self.scrollable_frame,
            text="",
            font=("Arial", 12),
            foreground="#7f8c8d"
        )
        self.phrases_label.pack(pady=5)

        # 选项按钮框架
        self.options_frame = ttk.Frame(self.scrollable_frame)
        self.options_frame.pack(pady=20, fill=tk.X, padx=20)

        # 结果反馈
        self.feedback_label = ttk.Label(
            self.scrollable_frame,
            text="",
            font=("Arial", 16)
        )
        self.feedback_label.pack(pady=10)

        # 下一题按钮
        self.next_button = ttk.Button(
            self.scrollable_frame,
            text="下一题",
            command=self.next_question,
            state=tk.DISABLED
        )
        self.next_button.pack(pady=10)

        # 布局滚动组件
        self.main_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 绑定鼠标滚轮事件
        def _on_mousewheel(event):
            self.main_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        self.main_canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def setup_stats_tab(self, notebook):
        """设置统计选项卡"""
        stats_frame = ttk.Frame(notebook, padding="10")
        notebook.add(stats_frame, text="学习统计")

        self.stats_text = tk.Text(stats_frame, height=20, width=60)
        self.stats_text.pack(fill=tk.BOTH, expand=True)

        ttk.Button(stats_frame, text="刷新统计", command=self.refresh_stats).pack(pady=10)

    def import_pdf_files(self):
        """导入PDF文件"""
        file_paths = filedialog.askopenfilenames(
            title="选择PDF文件",
            filetypes=[("PDF files", "*.pdf")]
        )

        if file_paths:
            self.process_pdf_files(file_paths)

    def import_pdf_folder(self):
        """批量导入PDF文件夹"""
        folder_path = filedialog.askdirectory(title="选择包含PDF文件的文件夹")

        if folder_path:
            # 创建进度对话框
            progress_dialog = tk.Toplevel(self.root)
            progress_dialog.title("批量导入进度")
            progress_dialog.geometry("400x200")
            progress_dialog.transient(self.root)
            progress_dialog.grab_set()
            
            # 居中显示
            progress_dialog.update_idletasks()
            x = (progress_dialog.winfo_screenwidth() // 2) - (400 // 2)
            y = (progress_dialog.winfo_screenheight() // 2) - (200 // 2)
            progress_dialog.geometry(f"400x200+{x}+{y}")
            
            # 进度标签
            progress_label = ttk.Label(progress_dialog, text="正在扫描文件夹...", font=("Arial", 12))
            progress_label.pack(pady=20)
            
            # 进度条
            progress_bar = ttk.Progressbar(progress_dialog, mode='indeterminate', length=300)
            progress_bar.pack(pady=10)
            progress_bar.start()
            
            # 详细进度标签
            detail_label = ttk.Label(progress_dialog, text="", font=("Arial", 10))
            detail_label.pack(pady=10)
            
            # 统计标签
            stats_label = ttk.Label(progress_dialog, text="", font=("Arial", 10))
            stats_label.pack(pady=10)
            
            def update_progress(message, current_words=0, total_processed=0):
                """更新进度显示"""
                progress_label.config(text=message)
                detail_label.config(text=f"已处理单词: {current_words}")
                stats_label.config(text=f"新增: {inserted_count} | 更新: {updated_count} | 翻译: {translated_count}")
                progress_dialog.update()
            
            total_words = 0
            inserted_count = 0
            updated_count = 0
            translated_count = 0
            
            try:
                # 第一阶段：扫描文件夹
                update_progress("正在扫描PDF文件...")
                all_words = PDFWordExtractor.batch_extract_from_folder(folder_path)
                
                # 计算总单词数
                total_word_count = sum(len(words) for words in all_words.values())
                progress_bar.stop()
                progress_bar.config(mode='determinate', maximum=total_word_count)
                
                # 第二阶段：处理单词
                processed_words = 0
                for category, words in all_words.items():
                    update_progress(f"正在处理分类: {category}", processed_words)
                    
                    for word_data in words:
                        # 检查是否是通过在线翻译获取的释义
                        if word_data['definition'] and word_data['definition'] != "暂无释义":
                            # 检查是否是新翻译的（通过检查本地词典中是否已有该单词）
                            if local_dict and word_data['word'].lower() not in local_dict.dictionary:
                                translated_count += 1
                        
                        result = self.db.add_or_update_word(
                            word_data['word'], 
                            word_data['definition'], 
                            word_data['phrases'], 
                            word_data['category']
                        )
                        
                        if result == "inserted":
                            inserted_count += 1
                            total_words += 1
                        elif result == "updated":
                            updated_count += 1
                            total_words += 1
                        
                        processed_words += 1
                        progress_bar['value'] = processed_words
                        
                        # 每10个单词更新一次进度
                        if processed_words % 10 == 0:
                            update_progress(f"正在处理分类: {category}", processed_words)
                
                # 导入完成
                progress_label.config(text="批量导入完成！")
                detail_label.config(text=f"总处理单词数: {total_words}")
                stats_label.config(text=f"新增: {inserted_count} | 更新: {updated_count} | 翻译: {translated_count}")
                
                # 延迟显示完成消息
                progress_dialog.after(2000, lambda: self._show_folder_import_complete(progress_dialog, total_words, inserted_count, updated_count, translated_count))
                
            except Exception as e:
                progress_dialog.destroy()
                messagebox.showerror("导入错误", f"批量导入过程中出现错误：{e}")
                print(f"批量导入错误: {e}")
    
    def _show_folder_import_complete(self, progress_dialog, total_words, inserted_count, updated_count, translated_count):
        """显示文件夹导入完成消息"""
        progress_dialog.destroy()
        
        # 显示详细的导入结果
        result_message = f"批量导入完成！\n\n"
        result_message += f"总处理单词数: {total_words}\n"
        result_message += f"新增单词数: {inserted_count}\n"
        result_message += f"更新单词数: {updated_count}\n"
        result_message += f"在线翻译单词数: {translated_count}"
        
        messagebox.showinfo("导入完成", result_message)
        self.refresh_word_list()

    def process_pdf_files(self, file_paths):
        """处理PDF文件"""
        # 创建进度对话框
        progress_dialog = tk.Toplevel(self.root)
        progress_dialog.title("导入进度")
        progress_dialog.geometry("400x200")
        progress_dialog.transient(self.root)
        progress_dialog.grab_set()
        
        # 居中显示
        progress_dialog.update_idletasks()
        x = (progress_dialog.winfo_screenwidth() // 2) - (400 // 2)
        y = (progress_dialog.winfo_screenheight() // 2) - (200 // 2)
        progress_dialog.geometry(f"400x200+{x}+{y}")
        
        # 进度标签
        progress_label = ttk.Label(progress_dialog, text="正在准备导入...", font=("Arial", 12))
        progress_label.pack(pady=20)
        
        # 进度条
        progress_bar = ttk.Progressbar(progress_dialog, mode='determinate', length=300)
        progress_bar.pack(pady=10)
        
        # 详细进度标签
        detail_label = ttk.Label(progress_dialog, text="", font=("Arial", 10))
        detail_label.pack(pady=10)
        
        # 统计标签
        stats_label = ttk.Label(progress_dialog, text="", font=("Arial", 10))
        stats_label.pack(pady=10)
        
        total_words = 0
        inserted_count = 0
        updated_count = 0
        translated_count = 0
        
        # 计算总文件数
        total_files = len(file_paths)
        progress_bar['maximum'] = total_files
        
        def update_progress(file_index, filename, current_words, total_processed):
            """更新进度显示"""
            progress = (file_index + 1) / total_files * 100
            progress_bar['value'] = file_index + 1
            
            progress_label.config(text=f"正在处理文件 {file_index + 1}/{total_files}")
            detail_label.config(text=f"当前文件: {filename}\n已处理单词: {current_words}")
            stats_label.config(text=f"新增: {inserted_count} | 更新: {updated_count} | 翻译: {translated_count}")
            
            progress_dialog.update()

        try:
            for file_index, file_path in enumerate(file_paths):
                filename = os.path.basename(file_path)
                update_progress(file_index, filename, 0, total_words)
                
                # 提取单词
                words_with_categories = PDFWordExtractor.extract_words_with_translation(file_path)
                
                # 处理单词
                for word_index, word_data in enumerate(words_with_categories):
                    # 检查是否是通过在线翻译获取的释义
                    if word_data['definition'] and word_data['definition'] != "暂无释义":
                        # 检查是否是新翻译的（通过检查本地词典中是否已有该单词）
                        if local_dict and word_data['word'].lower() not in local_dict.dictionary:
                            translated_count += 1
                    
                    result = self.db.add_or_update_word(
                        word_data['word'], 
                        word_data['definition'], 
                        word_data['phrases'], 
                        word_data['category']
                    )
                    
                    if result == "inserted":
                        inserted_count += 1
                        total_words += 1
                    elif result == "updated":
                        updated_count += 1
                        total_words += 1
                    
                    # 更新详细进度
                    if word_index % 5 == 0:  # 每5个单词更新一次
                        update_progress(file_index, filename, word_index + 1, total_words)
                
                # 文件处理完成
                update_progress(file_index, filename, len(words_with_categories), total_words)
            
            # 导入完成
            progress_label.config(text="导入完成！")
            detail_label.config(text=f"总处理单词数: {total_words}")
            stats_label.config(text=f"新增: {inserted_count} | 更新: {updated_count} | 翻译: {translated_count}")
            
            # 延迟显示完成消息
            progress_dialog.after(2000, lambda: self._show_import_complete(progress_dialog, total_words, inserted_count, updated_count, translated_count))
            
        except Exception as e:
            progress_dialog.destroy()
            messagebox.showerror("导入错误", f"导入过程中出现错误：{e}")
            print(f"导入错误: {e}")
    
    def _show_import_complete(self, progress_dialog, total_words, inserted_count, updated_count, translated_count):
        """显示导入完成消息"""
        progress_dialog.destroy()
        
        # 显示详细的导入结果
        result_message = f"导入完成！\n\n"
        result_message += f"总处理单词数: {total_words}\n"
        result_message += f"新增单词数: {inserted_count}\n"
        result_message += f"更新单词数: {updated_count}\n"
        result_message += f"在线翻译单词数: {translated_count}"
        
        messagebox.showinfo("导入完成", result_message)
        self.refresh_word_list()

    def refresh_word_list(self):
        """刷新单词列表"""
        # 清空现有项目
        for item in self.word_tree.get_children():
            self.word_tree.delete(item)

        # 获取单词数据
        conn = sqlite3.connect(self.db.db_name)
        cursor = conn.cursor()
        cursor.execute('''
                       SELECT word, definition, category, correct_count, wrong_count
                       FROM words
                       ORDER BY word
                       ''')

        for row in cursor.fetchall():
            word, definition, category, correct, wrong = row
            total = correct + wrong
            accuracy = f"{correct/total*100:.1f}%" if total > 0 else "未测试"

            # 截短释义
            short_def = definition[:30] + "..." if len(definition) > 30 else definition

            self.word_tree.insert('', 'end', values=(word, short_def, category, accuracy))

        conn.close()

    def start_study(self):
        """开始学习"""
        try:
            count = int(self.word_count_var.get())
        except ValueError:
            messagebox.showerror("错误", "请输入有效的数字")
            return

        # 获取学习单词
        words = self.db.get_words_for_study(limit=count)

        if not words:
            messagebox.showinfo("提示", "词库中没有单词，请先导入PDF文件")
            return

        self.study_session = words
        self.current_index = 0
        self.correct_count = 0

        self.show_question()

    def show_question(self):
        """显示题目"""
        if self.current_index >= len(self.study_session):
            self.show_study_results()
            return

        word_data = self.study_session[self.current_index]
        self.current_word = word_data[0]
        correct_definition = word_data[1]

        # 更新进度
        progress = f"第 {self.current_index + 1} 题 / 共 {len(self.study_session)} 题"
        self.progress_label.config(text=progress)

        # 显示单词
        self.word_label.config(text=self.current_word.upper())
        
        # 显示短语
        phrases = word_data[2] if isinstance(word_data[2], list) else []
        if phrases:
            phrases_text = "; ".join([f"{p.get('phrase', '')}: {p.get('translation', '')}" for p in phrases[:3]])
            self.phrases_label.config(text=phrases_text)
        else:
            self.phrases_label.config(text="")

        # 生成选项
        self.generate_options(correct_definition)

        # 重置反馈和按钮
        self.feedback_label.config(text="", foreground="black")
        self.next_button.config(state=tk.DISABLED)
        
        # 滚动到顶部
        if hasattr(self, 'main_canvas'):
            self.main_canvas.update_idletasks()
            self.main_canvas.yview_moveto(0)

    def generate_options(self, correct_definition):
        """生成选择题选项"""
        # 清空现有选项
        for widget in self.options_frame.winfo_children():
            widget.destroy()

        # 获取错误选项
        conn = sqlite3.connect(self.db.db_name)
        cursor = conn.cursor()
        cursor.execute('''
                       SELECT definition FROM words
                       WHERE definition != ? AND definition != ""
                       ORDER BY RANDOM() LIMIT 3
                       ''', (correct_definition,))

        wrong_options = [row[0] for row in cursor.fetchall()]
        conn.close()

        # 如果错误选项不足，添加一些通用错误选项
        if len(wrong_options) < 3:
            generic_options = [
                "动物的名称",
                "一种颜色",
                "时间单位",
                "地理位置",
                "数学概念"
            ]
            wrong_options.extend(generic_options[:3-len(wrong_options)])

        # 组合所有选项
        all_options = [correct_definition] + wrong_options[:3]
        random.shuffle(all_options)

        self.current_options = all_options
        self.correct_answer = correct_definition

        # 创建选项按钮
        for i, option in enumerate(all_options):
            # 截短选项文本
            display_text = option[:50] + "..." if len(option) > 50 else option

            btn = ttk.Button(
                self.options_frame,
                text=f"{chr(65+i)}. {display_text}",
                command=lambda opt=option: self.check_answer(opt),
                width=60
            )
            btn.pack(pady=5, fill=tk.X)

    def check_answer(self, selected_option):
        """检查答案"""
        is_correct = selected_option == self.correct_answer

        # 更新统计
        self.db.update_word_stats(self.current_word, is_correct)

        if is_correct:
            self.correct_count += 1
            self.feedback_label.config(text="✓ 正确！", foreground="green")
        else:
            self.feedback_label.config(text=f"✗ 错误。正确答案是：{self.correct_answer}", foreground="red")

        # 禁用所有选项按钮
        for widget in self.options_frame.winfo_children():
            widget.config(state=tk.DISABLED)

        # 启用下一题按钮
        self.next_button.config(state=tk.NORMAL)

    def next_question(self):
        """下一题"""
        self.current_index += 1
        self.show_question()

    def show_study_results(self):
        """显示学习结果"""
        accuracy = self.correct_count / len(self.study_session) * 100

        result_text = f"""
学习完成！

总题数: {len(self.study_session)}
正确数: {self.correct_count}
准确率: {accuracy:.1f}%

继续加油！💪
        """

        self.progress_label.config(text="学习完成")
        self.word_label.config(text="🎉")
        self.phrases_label.config(text="")
        self.feedback_label.config(text=result_text, foreground="blue")

        # 清空选项
        for widget in self.options_frame.winfo_children():
            widget.destroy()

        self.next_button.config(text="重新开始", state=tk.NORMAL, command=self.reset_study)

    def reset_study(self):
        """重置学习"""
        self.progress_label.config(text="点击'开始学习'开始背单词")
        self.word_label.config(text="")
        self.phrases_label.config(text="")
        self.feedback_label.config(text="")

        for widget in self.options_frame.winfo_children():
            widget.destroy()

        self.next_button.config(text="下一题", state=tk.DISABLED, command=self.next_question)
        
        # 滚动到顶部
        if hasattr(self, 'main_canvas'):
            self.main_canvas.update_idletasks()
            self.main_canvas.yview_moveto(0)

    def refresh_stats(self):
        """刷新统计信息"""
        conn = sqlite3.connect(self.db.db_name)
        cursor = conn.cursor()

        # 获取总体统计
        cursor.execute('SELECT COUNT(*) FROM words')
        total_words = cursor.fetchone()[0]

        cursor.execute('''
                       SELECT COUNT(*) FROM words
                       WHERE correct_count + wrong_count > 0
                       ''')
        studied_words = cursor.fetchone()[0]

        cursor.execute('''
                       SELECT AVG(CAST(correct_count AS FLOAT) / (correct_count + wrong_count)) * 100
                       FROM words
                       WHERE correct_count + wrong_count > 0
                       ''')
        avg_accuracy = cursor.fetchone()[0] or 0

        # 获取最近学习记录
        cursor.execute('''
                       SELECT word, result, study_date
                       FROM study_records
                       ORDER BY id DESC
                           LIMIT 10
                       ''')
        recent_records = cursor.fetchall()

        conn.close()

        # 显示统计信息
        stats_text = f"""
=== 学习统计 ===

词库总数: {total_words} 个单词
已学习: {studied_words} 个单词
平均准确率: {avg_accuracy:.1f}%

=== 最近学习记录 ===
"""

        for word, result, date in recent_records:
            status = "✓" if result == "correct" else "✗"
            stats_text += f"{status} {word} - {date}\n"

        self.stats_text.delete(1.0, tk.END)
        self.stats_text.insert(1.0, stats_text)

    def generate_exercises(self):
        """生成练习题"""
        # 获取所有单词
        all_words = self.db.get_words_for_study(limit=100) # 获取更多单词以生成更多练习题

        if not all_words:
            messagebox.showinfo("提示", "词库中没有单词，请先导入PDF文件")
            return

        # 随机选择单词
        random.shuffle(all_words)
        selected_words = all_words[:10] # 选择10个单词

        # 生成练习题文本
        exercise_text = "=== 自动生成的练习题 ===\n\n"
        
        for i, word_data in enumerate(selected_words, 1):
            word = word_data[0]
            definition = word_data[1]
            
            # 生成错误选项
            wrong_options = self.generate_wrong_options(definition, all_words)
            all_options = [definition] + wrong_options[:3]
            random.shuffle(all_options)
            correct_index = all_options.index(definition)
            
            exercise_text += f"{i}. {word}\n"
            exercise_text += f"   A. {all_options[0]}\n"
            exercise_text += f"   B. {all_options[1]}\n"
            exercise_text += f"   C. {all_options[2]}\n"
            exercise_text += f"   D. {all_options[3]}\n"
            exercise_text += f"   正确答案: {chr(65 + correct_index)}\n\n"

        # 保存为文本文件
        file_path = filedialog.asksaveasfilename(
            title="保存练习题",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(exercise_text)
                messagebox.showinfo("练习题生成成功", f"练习题已保存到 {file_path}")
            except Exception as e:
                messagebox.showerror("错误", f"保存练习题失败: {e}")

    def generate_wrong_options(self, correct_definition, all_words):
        """生成错误选项"""
        wrong_options = []
        
        # 从其他单词的释义中获取错误选项
        for word_data in all_words:
            if word_data[1] != correct_definition and word_data[1]:
                wrong_options.append(word_data[1])
                if len(wrong_options) >= 10:  # 最多取10个
                    break
        
        # 如果错误选项不足，添加一些通用选项
        if len(wrong_options) < 3:
            generic_options = [
                "动物的名称",
                "一种颜色",
                "时间单位",
                "地理位置",
                "数学概念",
                "食物名称",
                "职业名称",
                "交通工具"
            ]
            wrong_options.extend(generic_options[:3-len(wrong_options)])
        
        return wrong_options

    def add_word_to_dictionary(self):
        """添加单词到词典"""
        # 创建添加单词的对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("添加单词到词典")
        dialog.geometry("400x300")
        dialog.transient(self.root)
        dialog.grab_set()

        # 输入框架
        input_frame = ttk.Frame(dialog, padding="20")
        input_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(input_frame, text="单词:").pack(anchor=tk.W)
        word_var = tk.StringVar()
        word_entry = ttk.Entry(input_frame, textvariable=word_var, width=40)
        word_entry.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(input_frame, text="中文释义:").pack(anchor=tk.W)
        definition_var = tk.StringVar()
        definition_entry = ttk.Entry(input_frame, textvariable=definition_var, width=40)
        definition_entry.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(input_frame, text="短语 (可选，格式: 短语:翻译，多个用分号分隔):").pack(anchor=tk.W)
        phrases_var = tk.StringVar()
        phrases_entry = ttk.Entry(input_frame, textvariable=phrases_var, width=40)
        phrases_entry.pack(fill=tk.X, pady=(0, 20))

        def save_word():
            word = word_var.get().strip()
            definition = definition_var.get().strip()
            phrases = phrases_var.get().strip()

            if not word or not definition:
                messagebox.showerror("错误", "请填写单词和释义")
                return

            # 添加到本地词典
            local_dict.add_word(word, definition, phrases)
            messagebox.showinfo("成功", f"单词 '{word}' 已添加到词典")
            dialog.destroy()

        def cancel():
            dialog.destroy()

        # 按钮框架
        button_frame = ttk.Frame(input_frame)
        button_frame.pack(pady=20)

        ttk.Button(button_frame, text="保存", command=save_word).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="取消", command=cancel).pack(side=tk.LEFT)

        # 设置焦点
        word_entry.focus()

    def show_dictionary_info(self):
        """显示词典信息"""
        size = local_dict.get_dictionary_size()
        db_stats = local_dict.get_database_stats()
        
        info_text = f"""
词典信息:
- 词典文件: {local_dict.dict_file}
- 数据库文件: {local_dict.db_file}
- 内存中单词数: {size}
- 数据库中单词数: {db_stats['total_words']}
- 词典状态: {'已加载' if local_dict.dictionary else '未加载'}

数据库统计:
- 总单词数: {db_stats['total_words']} 个

最近添加的单词:
"""
        
        if db_stats['recent_words']:
            for word, date in db_stats['recent_words']:
                info_text += f"- {word} ({date})\n"
        else:
            info_text += "- 暂无\n"
            
        info_text += "\n最近更新的单词:\n"
        
        if db_stats['updated_words']:
            for word, date in db_stats['updated_words']:
                info_text += f"- {word} ({date})\n"
        else:
            info_text += "- 暂无\n"
            
        info_text += """
词典来源:
- 数据库存储: 自动保存到SQLite数据库
- 导入词典: 从本地JSON文件导入
- 用户添加: 通过界面手动添加

您可以通过以下方式扩展词典:
1. 点击"导入词典文件"选择本地JSON文件
2. 使用"添加单词到词典"手动添加
3. 所有添加的单词会自动保存到数据库
        """
        messagebox.showinfo("词典信息", info_text)

    def import_dictionary_file(self):
        """从本地导入词典JSON文件"""
        try:
            from tkinter import filedialog
            
            # 打开文件选择对话框
            file_path = filedialog.askopenfilename(
                title="选择词典JSON文件",
                filetypes=[
                    ("JSON文件", "*.json"),
                    ("所有文件", "*.*")
                ]
            )
            
            if file_path:
                # 显示导入进度
                progress_dialog = tk.Toplevel(self.root)
                progress_dialog.title("导入词典")
                progress_dialog.geometry("300x150")
                progress_dialog.transient(self.root)
                progress_dialog.grab_set()

                progress_label = ttk.Label(progress_dialog, text="正在导入词典文件...")
                progress_label.pack(pady=20)

                def import_file():
                    try:
                        success = local_dict.import_from_json_file(file_path)
                        if success:
                            # 重新加载词典
                            local_dict.dictionary = local_dict.load_dictionary()
                            messagebox.showinfo(
                                "导入成功", 
                                f"成功导入词典文件，包含 {local_dict.get_dictionary_size()} 个单词"
                            )
                        else:
                            messagebox.showerror("导入失败", "无法解析词典文件格式")
                    except Exception as e:
                        messagebox.showerror("错误", f"导入过程中出现错误：{e}")
                    finally:
                        progress_dialog.destroy()

                # 在新线程中执行导入
                import threading
                thread = threading.Thread(target=import_file)
                thread.daemon = True
                thread.start()

        except Exception as e:
            messagebox.showerror("错误", f"启动导入失败：{e}")

    def reset_word_database(self):
        """重置单词数据库"""
        # 显示确认对话框
        result = messagebox.askyesno(
            "确认重置", 
            "确定要重置单词数据库吗？\n\n这将删除：\n- 所有导入的单词\n- 学习记录\n- 学习统计\n\n此操作不可恢复！"
        )
        
        if result:
            try:
                # 使用数据库类的重置方法
                if self.db.reset_database():
                    # 刷新单词列表
                    self.refresh_word_list()
                    
                    messagebox.showinfo(
                        "重置成功", 
                        "单词数据库已成功重置！\n\n已删除：\n- 所有导入的单词\n- 学习记录\n- 学习统计\n\n数据库已重新初始化。"
                    )
                else:
                    messagebox.showerror("错误", "重置数据库失败")
                
            except Exception as e:
                messagebox.showerror("错误", f"重置数据库失败：{e}")
                print(f"重置数据库时出错: {e}")

    def rebuild_dictionary(self):
        """重建基础词典"""
        try:
            # 重新创建基础词典
            local_dict.dictionary = local_dict.create_basic_dictionary()
            local_dict.save_dictionary()
            
            messagebox.showinfo("成功", f"基础词典重建成功！\n包含 {local_dict.get_dictionary_size()} 个单词")
        except Exception as e:
            messagebox.showerror("错误", f"重建词典失败：{e}")

# 初始化全局本地词典实例
def init_local_dictionary():
    """初始化全局本地词典实例，并自动导入当前目录下的JSON词典文件"""
    global local_dict
    local_dict = LocalDictionary()
    
    # 自动导入当前目录下的JSON词典文件
    auto_import_json_from_current_directory()

def auto_import_json_from_current_directory():
    """自动导入当前目录下的JSON词典文件"""
    try:
        current_dir = os.getcwd()
        json_files = []
        
        # 扫描当前目录下的所有JSON文件
        for file in os.listdir(current_dir):
            if file.endswith('.json') and file != 'gaokao_dictionary.json':
                json_files.append(os.path.join(current_dir, file))
        
        if json_files:
            print(f"发现 {len(json_files)} 个JSON词典文件，正在自动导入...")
            
            # 按文件名排序，优先导入包含"词典"、"dictionary"、"vocabulary"等关键词的文件
            def get_priority_score(filename):
                filename_lower = filename.lower()
                priority = 0
                if any(keyword in filename_lower for keyword in ['词典', 'dictionary', 'vocabulary', 'gaokao', '高考']):
                    priority += 10
                if 'english' in filename_lower:
                    priority += 5
                return priority
            
            json_files.sort(key=lambda x: get_priority_score(os.path.basename(x)), reverse=True)
            
            # 尝试导入第一个文件
            for json_file in json_files:
                print(f"尝试导入: {os.path.basename(json_file)}")
                if local_dict.import_from_json_file(json_file):
                    print(f"成功自动导入词典文件: {os.path.basename(json_file)}")
                    print(f"词典包含 {local_dict.get_dictionary_size()} 个单词")
                    return
                else:
                    print(f"导入失败: {os.path.basename(json_file)}")
            
            print("所有JSON文件导入失败，使用基础词典")
        else:
            print("当前目录下未发现JSON词典文件，使用基础词典")
            
    except Exception as e:
        print(f"自动导入JSON文件时出错: {e}")
        print("使用基础词典")

def main():
    """主函数"""
    # 初始化本地词典
    init_local_dictionary()
    
    root = tk.Tk()
    app = VocabularyApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()