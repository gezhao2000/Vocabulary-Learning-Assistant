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
import urllib.request
from io import BytesIO
import threading
import atexit
import base64
import pyttsx3

from datetime import datetime, timedelta
import sqlite3

# 全局引擎变量
engine = None
engine_lock = threading.Lock()

# 创建全局本地词典实例
local_dict = None

def cleanup_engine():
    """清理语音引擎资源"""
    global engine
    try:
        with engine_lock:
            if engine is not None:
                engine.stop()
                del engine
                engine = None
                print("语音引擎已清理")
    except:
        pass  # 忽略清理时的错误

# 注册程序退出时的清理函数
atexit.register(cleanup_engine)

def init_engine():
    """初始化语音引擎"""
    global engine
    try:
        with engine_lock:
            if engine is None:
                engine = pyttsx3.init()
                # 设置语音属性
                voices = engine.getProperty('voices')
                # 尝试设置英语语音
                for voice in voices:
                    if 'english' in voice.name.lower() or 'en' in voice.id.lower():
                        engine.setProperty('voice', voice.id)
                        break
                
                # 设置语速和音量
                engine.setProperty('rate', 150)  # 语速
                engine.setProperty('volume', 0.8)  # 音量
                print("语音引擎初始化成功")
    except Exception as e:
        print(f"语音引擎初始化失败: {e}")

def speak(text):
    """播放文本语音"""
    global engine
    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()
    engine.stop()
    del engine


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
                                                            created_date DATE DEFAULT CURRENT_DATE,
                                                            image_path TEXT,
                                                            image_url TEXT,
                                                            image_service TEXT,
                                                            phonetic TEXT,
                                                            part_of_speech TEXT,
                                                            pronunciation TEXT,
                                                            detailed_info TEXT
                       )
                       ''')

        # 检查并添加新列（如果不存在）
        try:
            cursor.execute('ALTER TABLE words ADD COLUMN image_path TEXT')
        except sqlite3.OperationalError:
            pass  # 列已存在
        
        try:
            cursor.execute('ALTER TABLE words ADD COLUMN image_url TEXT')
        except sqlite3.OperationalError:
            pass  # 列已存在
        
        try:
            cursor.execute('ALTER TABLE words ADD COLUMN image_service TEXT')
        except sqlite3.OperationalError:
            pass  # 列已存在

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
        
    def update_database_schema(self):
        """更新数据库结构，添加新列"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        try:
            # 检查并添加新列（如果不存在）
            new_columns = [
                ('image_path', 'TEXT'),
                ('image_url', 'TEXT'),
                ('image_service', 'TEXT'),
                ('phonetic', 'TEXT'),
                ('part_of_speech', 'TEXT'),
                ('pronunciation', 'TEXT'),
                ('detailed_info', 'TEXT')
            ]
            
            for column_name, column_type in new_columns:
                try:
                    cursor.execute(f'ALTER TABLE words ADD COLUMN {column_name} {column_type}')
                    print(f"已添加 {column_name} 列")
                except sqlite3.OperationalError:
                    pass  # 列已存在
            
            conn.commit()
            print("数据库结构更新完成")
        except Exception as e:
            print(f"更新数据库结构失败: {e}")
        finally:
            conn.close()

    def add_word(self, word, definition="", phrases=None, category="", image_path="", image_url="", image_service="", phonetic="", part_of_speech="", pronunciation="", detailed_info=""):
        """添加单词到数据库"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        try:
            if phrases is None:
                phrases = ""
            phrases_str = json.dumps(phrases, ensure_ascii=False)
            cursor.execute('''
                           INSERT OR IGNORE INTO words (word, definition, phrases, category, image_path, image_url, image_service, phonetic, part_of_speech, pronunciation, detailed_info)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ''', (word.lower(), definition, phrases_str, category, image_path, image_url, image_service, phonetic, part_of_speech, pronunciation, detailed_info))
            conn.commit()
            return True
        except Exception as e:
            print(f"添加单词失败: {e}")
            return False
        finally:
            conn.close()

    def add_or_update_word(self, word, definition="", phrases=None, category="", image_path="", image_url="", image_service="", phonetic="", part_of_speech="", pronunciation="", detailed_info=""):
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
                # 单词已存在，更新所有字段
                cursor.execute('''
                               UPDATE words 
                               SET definition = ?, phrases = ?, category = ?, image_path = ?, image_url = ?, image_service = ?, phonetic = ?, part_of_speech = ?, pronunciation = ?, detailed_info = ?
                               WHERE word = ?
                               ''', (definition, phrases_str, category, image_path, image_url, image_service, phonetic, part_of_speech, pronunciation, detailed_info, word.lower()))
                conn.commit()
                return "updated"
            else:
                # 单词不存在，插入新单词
                cursor.execute('''
                               INSERT INTO words (word, definition, phrases, category, image_path, image_url, image_service, phonetic, part_of_speech, pronunciation, detailed_info)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                               ''', (word.lower(), definition, phrases_str, category, image_path, image_url, image_service, phonetic, part_of_speech, pronunciation, detailed_info))
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
                SELECT word, definition, phrases, difficulty, correct_count, wrong_count, image_path, image_url, image_service, phonetic, part_of_speech, pronunciation, detailed_info
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
            word, definition, phrases_str, difficulty, correct_count, wrong_count, image_path, image_url, image_service, phonetic, part_of_speech, pronunciation, detailed_info = word_data
            try:
                phrases = json.loads(phrases_str) if phrases_str else []
            except:
                phrases = []
            processed_words.append((word, definition, phrases, difficulty, correct_count, wrong_count, image_path, image_url, image_service, phonetic, part_of_speech, pronunciation, detailed_info))

        return processed_words

    def save_word_image_info(self, word, image_path="", image_url="", image_service=""):
        """保存单词的图片信息到数据库"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                           UPDATE words
                           SET image_path = ?, image_url = ?, image_service = ?
                           WHERE word = ?
                           ''', (image_path, image_url, image_service, word.lower()))
            conn.commit()
            return True
        except Exception as e:
            print(f"保存图片信息失败: {e}")
            return False
        finally:
            conn.close()

    def get_word_image_info(self, word):
        """获取单词的图片信息"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                           SELECT image_path, image_url, image_service
                           FROM words
                           WHERE word = ?
                           ''', (word.lower(),))
            result = cursor.fetchone()
            if result:
                return {
                    'image_path': result[0],
                    'image_url': result[1],
                    'image_service': result[2]
                }
            return None
        except Exception as e:
            print(f"获取图片信息失败: {e}")
            return None
        finally:
            conn.close()

    def word_exists(self, word):
        """检查单词是否已存在于数据库中"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT COUNT(*) FROM words WHERE word = ?', (word.lower(),))
            count = cursor.fetchone()[0]
            return count > 0
        except Exception as e:
            print(f"检查单词是否存在失败: {e}")
            return False
        finally:
            conn.close()

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
        """从PDF提取单词并自动获取翻译和音标"""
        words_with_categories = PDFWordExtractor.extract_words_from_pdf(pdf_path)
        
        # 创建在线翻译器实例
        translator = OnlineTranslator()
        
        # 为每个单词获取翻译和音标
        try:
            for i, word_data in enumerate(words_with_categories):
                word = word_data['word']
                
                if local_dict is not None:
                    # 优先从本地词典库获取信息
                    word_lower = word.lower()
                    local_word_info = local_dict.dictionary.get(word_lower, {})
                    
                    # 检查本地词典是否已有完整信息
                    if local_word_info.get('definition') and local_word_info.get('phonetic'):
                        # 本地已有完整信息，直接使用
                        word_data['definition'] = local_word_info.get('definition', '')
                        word_data['phrases'] = local_word_info.get('phrases', '')
                        word_data['phonetic'] = local_word_info.get('phonetic', '')
                        word_data['part_of_speech'] = local_word_info.get('part_of_speech', '')
                        word_data['pronunciation'] = local_word_info.get('pronunciation', '')
                        word_data['detailed_info'] = local_word_info.get('detailed_info', '')
                        print(f"从本地词典库获取单词 '{word}' 的完整信息")
                    else:
                        # 本地词典库没有完整信息，获取并保存
                        print(f"本地词典库没有单词 '{word}' 的完整信息，正在获取...")
                        
                        # 获取翻译和音标信息
                        definition, phrases = local_dict.get_word_definition(word, auto_translate=True)
                        word_data['definition'] = definition
                        word_data['phrases'] = phrases
                        
                        # 获取音标信息
                        phonetic = ""
                        part_of_speech = ""
                        pronunciation = ""
                        detailed_info = ""
                        
                        # 如果本地词典中没有音标信息，尝试获取
                        if local_word_info.get('phonetic', ''):
                            # 本地已有音标，使用本地数据
                            phonetic = local_word_info.get('phonetic', '')
                            part_of_speech = local_word_info.get('part_of_speech', '')
                            pronunciation = local_word_info.get('pronunciation', '')
                            detailed_info = local_word_info.get('detailed_info', '')
                        else:
                            # 本地没有音标，尝试从在线API获取
                            try:
                                print(f"正在为单词 '{word}' 获取音标信息...")
                                definition_result, phrases_result, detailed_info_result = translator.translate_word(word)
                                
                                if isinstance(detailed_info_result, dict):
                                    phonetic = detailed_info_result.get('phonetic', '')
                                    part_of_speech = detailed_info_result.get('part_of_speech', '')
                                    pronunciation = detailed_info_result.get('pronunciation', '')
                                    detailed_info = detailed_info_result.get('detailed_info', '')
                                    
                                    # 如果获取到了音标信息，保存到本地词典
                                    if phonetic or part_of_speech:
                                        local_dict.add_word(
                                            word, 
                                            definition, 
                                            phrases, 
                                            phonetic=phonetic,
                                            part_of_speech=part_of_speech,
                                            pronunciation=pronunciation,
                                            detailed_info=detailed_info
                                        )
                                        print(f"已为单词 '{word}' 获取并保存音标信息: {phonetic}")
                                
                            except Exception as e:
                                print(f"获取单词 '{word}' 的音标信息失败: {e}")
                        
                        # 保存音标信息到word_data
                        word_data['phonetic'] = phonetic
                        word_data['part_of_speech'] = part_of_speech
                        word_data['pronunciation'] = pronunciation
                        word_data['detailed_info'] = detailed_info
                    
                    # 添加延迟以避免API请求过于频繁
                    if i > 0 and i % 5 == 0:  # 每5个单词暂停一下
                        time.sleep(0.5)
                else:
                    word_data['definition'] = ""
                    word_data['phrases'] = []
                    word_data['phonetic'] = ""
                    word_data['part_of_speech'] = ""
                    word_data['pronunciation'] = ""
                    word_data['detailed_info'] = ""
        except Exception as e:
            print(f"获取单词释义和音标时出错: {e}")
            # 如果出错，设置默认值
            for word_data in words_with_categories:
                word_data['definition'] = ""
                word_data['phrases'] = []
                word_data['phonetic'] = ""
                word_data['part_of_speech'] = ""
                word_data['pronunciation'] = ""
                word_data['detailed_info'] = ""
        
        return words_with_categories

    @staticmethod
    def extract_words_with_smart_translation(pdf_path, db_instance):
        """从PDF提取单词并智能获取翻译和音标（优化版）"""
        words_with_categories = PDFWordExtractor.extract_words_from_pdf(pdf_path)
        
        # 创建在线翻译器实例
        translator = OnlineTranslator()
        
        # 为每个单词获取翻译和音标
        try:
            for i, word_data in enumerate(words_with_categories):
                word = word_data['word']
                word_lower = word.lower()
                
                # 1. 首先检查本地单词库是否已有这个单词
                if db_instance.word_exists(word):
                    print(f"单词 '{word}' 已存在于本地单词库，跳过处理")
                    # 跳过这个单词，不添加到结果中
                    continue
                
                # 2. 检查本地词典库是否有这个单词
                if local_dict is not None:
                    local_word_info = local_dict.dictionary.get(word_lower, {})
                    
                    if local_word_info.get('definition') and local_word_info.get('phonetic'):
                        # 本地词典库有完整信息，直接使用
                        word_data['definition'] = local_word_info.get('definition', '')
                        word_data['phrases'] = local_word_info.get('phrases', '')
                        word_data['phonetic'] = local_word_info.get('phonetic', '')
                        word_data['part_of_speech'] = local_word_info.get('part_of_speech', '')
                        word_data['pronunciation'] = local_word_info.get('pronunciation', '')
                        word_data['detailed_info'] = local_word_info.get('detailed_info', '')
                        print(f"从本地词典库获取单词 '{word}' 的完整信息")
                    else:
                        # 本地词典库没有完整信息，需要在线获取
                        print(f"本地词典库没有单词 '{word}' 的完整信息，正在在线获取...")
                        
                        # 获取翻译和音标信息
                        definition, phrases = local_dict.get_word_definition(word, auto_translate=True)
                        word_data['definition'] = definition
                        word_data['phrases'] = phrases
                        
                        # 获取音标信息
                        phonetic = ""
                        part_of_speech = ""
                        pronunciation = ""
                        detailed_info = ""
                        
                        # 如果本地词典中没有音标信息，尝试获取
                        if local_word_info.get('phonetic', ''):
                            # 本地已有音标，使用本地数据
                            phonetic = local_word_info.get('phonetic', '')
                            part_of_speech = local_word_info.get('part_of_speech', '')
                            pronunciation = local_word_info.get('pronunciation', '')
                            detailed_info = local_word_info.get('detailed_info', '')
                        else:
                            # 本地没有音标，尝试从在线API获取
                            try:
                                print(f"正在为单词 '{word}' 获取音标信息...")
                                definition_result, phrases_result, detailed_info_result = translator.translate_word(word)
                                
                                if isinstance(detailed_info_result, dict):
                                    phonetic = detailed_info_result.get('phonetic', '')
                                    part_of_speech = detailed_info_result.get('part_of_speech', '')
                                    pronunciation = detailed_info_result.get('pronunciation', '')
                                    detailed_info = detailed_info_result.get('detailed_info', '')
                                    
                                    # 如果获取到了音标信息，保存到本地词典
                                    if phonetic or part_of_speech:
                                        local_dict.add_word(
                                            word, 
                                            definition, 
                                            phrases, 
                                            phonetic=phonetic,
                                            part_of_speech=part_of_speech,
                                            pronunciation=pronunciation,
                                            detailed_info=detailed_info
                                        )
                                        print(f"已为单词 '{word}' 获取并保存音标信息: {phonetic}")
                                
                            except Exception as e:
                                print(f"获取单词 '{word}' 的音标信息失败: {e}")
                        
                        # 保存音标信息到word_data
                        word_data['phonetic'] = phonetic
                        word_data['part_of_speech'] = part_of_speech
                        word_data['pronunciation'] = pronunciation
                        word_data['detailed_info'] = detailed_info
                    
                    # 添加延迟以避免API请求过于频繁
                    if i > 0 and i % 5 == 0:  # 每5个单词暂停一下
                        time.sleep(0.5)
                else:
                    word_data['definition'] = ""
                    word_data['phrases'] = []
                    word_data['phonetic'] = ""
                    word_data['part_of_speech'] = ""
                    word_data['pronunciation'] = ""
                    word_data['detailed_info'] = ""
        except Exception as e:
            print(f"获取单词释义和音标时出错: {e}")
            # 如果出错，设置默认值
            for word_data in words_with_categories:
                word_data['definition'] = ""
                word_data['phrases'] = []
                word_data['phonetic'] = ""
                word_data['part_of_speech'] = ""
                word_data['pronunciation'] = ""
                word_data['detailed_info'] = ""
        
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
    def batch_extract_from_folder_smart(folder_path, db_instance):
        """批量从文件夹中的PDF提取单词（智能版，支持跳过已存在的单词）"""
        all_words = {}

        for filename in os.listdir(folder_path):
            if filename.lower().endswith('.pdf'):
                pdf_path = os.path.join(folder_path, filename)
                words_with_categories = PDFWordExtractor.extract_words_with_smart_translation(pdf_path, db_instance)
                
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
            
            # 创建词典表（包含音标和词性字段）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS dictionary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word TEXT UNIQUE NOT NULL,
                    definition TEXT,
                    phrases TEXT,
                    phonetic TEXT,
                    part_of_speech TEXT,
                    pronunciation TEXT,
                    detailed_info TEXT,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 检查是否需要添加新字段（兼容旧版本）
            cursor.execute("PRAGMA table_info(dictionary)")
            columns = [column[1] for column in cursor.fetchall()]
            
            # 添加缺失的字段
            if 'phonetic' not in columns:
                cursor.execute('ALTER TABLE dictionary ADD COLUMN phonetic TEXT')
                print("添加 phonetic 字段到词典表")
            
            if 'part_of_speech' not in columns:
                cursor.execute('ALTER TABLE dictionary ADD COLUMN part_of_speech TEXT')
                print("添加 part_of_speech 字段到词典表")
            
            if 'pronunciation' not in columns:
                cursor.execute('ALTER TABLE dictionary ADD COLUMN pronunciation TEXT')
                print("添加 pronunciation 字段到词典表")
            
            if 'detailed_info' not in columns:
                cursor.execute('ALTER TABLE dictionary ADD COLUMN detailed_info TEXT')
                print("添加 detailed_info 字段到词典表")
            
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
            
            cursor.execute('SELECT word, definition, phrases, phonetic, part_of_speech, pronunciation, detailed_info FROM dictionary')
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                return {}
            
            dictionary = {}
            for row in rows:
                word, definition, phrases_str, phonetic, part_of_speech, pronunciation, detailed_info = row
                try:
                    phrases = json.loads(phrases_str) if phrases_str else []
                except:
                    phrases = []
                
                dictionary[word] = {
                    'definition': definition or '',
                    'phrases': phrases,
                    'phonetic': phonetic or '',
                    'part_of_speech': part_of_speech or '',
                    'pronunciation': pronunciation or '',
                    'detailed_info': detailed_info or ''
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
                    phonetic = info.get('phonetic', '')
                    part_of_speech = info.get('part_of_speech', '')
                    pronunciation = info.get('pronunciation', '')
                    detailed_info = info.get('detailed_info', '')
                    
                    phrases_str = json.dumps(phrases, ensure_ascii=False)
                    
                    cursor.execute('''
                        INSERT INTO dictionary (word, definition, phrases, phonetic, part_of_speech, pronunciation, detailed_info)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (word, definition, phrases_str, phonetic, part_of_speech, pronunciation, detailed_info))
            
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
        """获取单词定义（支持音标和词性）"""
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
                definition, phrases, detailed_info = translator.translate_word(word)
                
                # 如果在线翻译成功，保存到本地词典
                if definition and definition != "暂无释义" and definition != word:
                    # 提取详细信息
                    phonetic = ""
                    part_of_speech = ""
                    pronunciation = ""
                    detailed_text = ""
                    
                    if isinstance(detailed_info, dict):
                        phonetic = detailed_info.get('phonetic', '')
                        part_of_speech = detailed_info.get('part_of_speech', '')
                        pronunciation = detailed_info.get('pronunciation', '')
                        detailed_text = detailed_info.get('detailed_info', '')
                    
                    # 确保翻译结果有效
                    self.add_word(word, definition, phrases, phonetic=phonetic, part_of_speech=part_of_speech, pronunciation=pronunciation, detailed_info=detailed_text)
                    print(f"已通过在线翻译获取并保存单词 '{word}' 的释义: {definition}")
                    
                    # 立即保存到数据库
                    self.save_word_to_database(word_lower, definition, phrases, phonetic, part_of_speech, pronunciation, detailed_text)
                    
                    return definition, phrases
                else:
                    print(f"翻译结果无效或为空: {word} -> {definition}")
                    return "暂无释义", ""
            except Exception as e:
                print(f"在线翻译单词 '{word}' 失败: {e}")
                return "暂无释义", ""
        
        return "暂无释义", ""

    def add_word(self, word, definition, phrases=None, phonetic="", part_of_speech="", pronunciation="", detailed_info=""):
        """添加单词到词典（支持音标和词性）"""
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
            'phrases': phrases,
            'phonetic': phonetic,
            'part_of_speech': part_of_speech,
            'pronunciation': pronunciation,
            'detailed_info': detailed_info
        }
        
        # 保存到数据库
        self.save_word_to_database(word_lower, definition, phrases, phonetic, part_of_speech, pronunciation, detailed_info)
        
        print(f"单词 '{word}' 已添加到本地词典: {definition}")

    def save_word_to_database(self, word, definition, phrases, phonetic="", part_of_speech="", pronunciation="", detailed_info=""):
        """保存单个单词到数据库（支持音标和词性）"""
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
                INSERT OR REPLACE INTO dictionary (word, definition, phrases, phonetic, part_of_speech, pronunciation, detailed_info, updated_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (word, definition, phrases, phonetic, part_of_speech, pronunciation, detailed_info))
            
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
                    phonetic = info.get('phonetic', '')
                    part_of_speech = info.get('part_of_speech', '')
                    pronunciation = info.get('pronunciation', '')
                    detailed_info = info.get('detailed_info', '')
                    
                    # 确保phrases是字符串格式
                    if isinstance(phrases, list):
                        phrases = json.dumps(phrases, ensure_ascii=False)
                    elif not isinstance(phrases, str):
                        phrases = str(phrases)
                    
                    cursor.execute('''
                        INSERT OR REPLACE INTO dictionary (word, definition, phrases, phonetic, part_of_speech, pronunciation, detailed_info, updated_date)
                        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (word, definition, phrases, phonetic, part_of_speech, pronunciation, detailed_info))
            
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

    def clear_dictionary_database(self):
        """清空词典数据库"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # 清空词典表
            cursor.execute('DELETE FROM dictionary')
            conn.commit()
            conn.close()
            
            print(f"已清空词典数据库: {self.db_file}")
            return True
        except Exception as e:
            print(f"清空词典数据库失败: {e}")
            return False

    def clear_dictionary_file(self):
        """清空词典JSON文件"""
        try:
            # 创建空的词典文件
            empty_dict = {}
            with open(self.dict_file, 'w', encoding='utf-8') as f:
                json.dump(empty_dict, f, ensure_ascii=False, indent=2)
            
            print(f"已清空词典文件: {self.dict_file}")
            return True
        except Exception as e:
            print(f"清空词典文件失败: {e}")
            return False

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
        """翻译单词（使用百度翻译API，支持音标和词性）"""
        try:
            # 使用增强版百度翻译API
            translation_result = self._translate_with_baidu(word)
            
            # 尝试获取音标信息
            phonetic_info = self._get_phonetic_from_api(word)
            if phonetic_info:
                return translation_result, [], phonetic_info
            
            # 如果所有翻译服务都失败，返回空结果
            return translation_result, [], {}
            
        except Exception as e:
            print(f"在线翻译失败: {e}")
            return "", [], {}
    
    def _translate_with_baidu(self, word):
        """使用百度翻译API翻译单词（增强版，支持音标和词性）"""
        try:
            # 首先尝试获取详细翻译信息
            detailed_info = self._get_detailed_translation(word)
            if detailed_info:
                return detailed_info
            
            # 如果详细翻译失败，使用基础翻译
            return self._get_basic_translation(word)
                
        except Exception as e:
            print(f"百度翻译失败: {e}")
            return ""
    
    def _get_basic_translation(self, word):
        """获取基础翻译"""
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
            
            if 'trans_result' in result:
                translation = result['trans_result'][0]['dst']
                print(f"百度基础翻译成功: {word} -> {translation}")
                return translation
            else:
                print(f"百度翻译API响应错误: {result}")
                return ""
                
        except Exception as e:
            print(f"百度基础翻译失败: {e}")
            return ""
    
    def _get_detailed_translation(self, word):
        """获取详细翻译信息（包括音标、词性等）"""
        try:
            # 使用百度翻译API的详细模式
            url = "http://api.fanyi.baidu.com/api/trans/vip/translate"
            salt = str(time.time())
            sign = hashlib.md5((self.APP_ID + word + salt + self.SECRET_KEY).encode('utf-8')).hexdigest()
            
            # 构建包含详细信息的查询
            detailed_query = f"{word} [详细释义]"
            
            params = {
                'q': detailed_query,
                'from': 'en',
                'to': 'zh',
                'appid': self.APP_ID,
                'salt': salt,
                'sign': sign
            }
            
            response = self.session.get(url, params=params, timeout=15)
            result = response.json()
            
            if 'trans_result' in result:
                translation = result['trans_result'][0]['dst']
                
                # 解析详细翻译结果，提取音标、词性等信息
                detailed_info = self._parse_detailed_translation(word, translation)
                if detailed_info:
                    print(f"百度详细翻译成功: {word} -> {detailed_info}")
                    return detailed_info
                
                # 如果解析失败，返回基础翻译
                return translation
            else:
                print(f"百度详细翻译API响应错误: {result}")
                return ""
                
        except Exception as e:
            print(f"百度详细翻译失败: {e}")
            return ""
    
    def _parse_detailed_translation(self, word, translation):
        """解析详细翻译结果，提取音标、词性等信息"""
        try:
            # 尝试从翻译结果中提取音标和词性信息
            # 百度翻译可能会返回包含音标的格式，如：apple [ˈæpl] n. 苹果
            
            # 提取音标（通常在方括号中）
            phonetic = ""
            phonetic_match = re.search(r'\[([^\]]+)\]', translation)
            if phonetic_match:
                phonetic = phonetic_match.group(1)
            
            # 提取词性（通常在音标后，如 n. v. adj. 等）
            part_of_speech = ""
            pos_match = re.search(r'\[[^\]]+\]\s*([a-z]+\.)', translation, re.IGNORECASE)
            if pos_match:
                part_of_speech = pos_match.group(1)
            
            # 提取中文释义（通常在词性后）
            chinese_definition = ""
            if part_of_speech:
                # 移除音标和词性，获取中文释义
                definition_match = re.search(r'\[[^\]]+\]\s*[a-z]+\.\s*(.+)', translation, re.IGNORECASE)
                if definition_match:
                    chinese_definition = definition_match.group(1).strip()
            else:
                # 如果没有词性，直接使用翻译结果
                chinese_definition = translation
            
            # 构建详细信息字典
            detailed_info = {
                'word': word,
                'translation': chinese_definition,
                'phonetic': phonetic,
                'part_of_speech': part_of_speech,
                'pronunciation': f"/{phonetic}/" if phonetic else "",
                'detailed_info': translation
            }
            
            return detailed_info
            
        except Exception as e:
            print(f"解析详细翻译失败: {e}")
            return None
    
    def _get_phonetic_from_api(self, word):
        """从其他API获取音标信息"""
        try:
            # 使用免费的词典API获取音标
            url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word.lower()}"
            
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data and isinstance(data, list) and len(data) > 0:
                    word_data = data[0]
                    
                    # 提取音标
                    phonetic = ""
                    if 'phonetic' in word_data and word_data['phonetic']:
                        phonetic = word_data['phonetic']
                    elif 'phonetics' in word_data and word_data['phonetics']:
                        for phonetic_data in word_data['phonetics']:
                            if 'text' in phonetic_data and phonetic_data['text']:
                                phonetic = phonetic_data['text']
                                break
                    
                    # 提取词性
                    part_of_speech = ""
                    if 'meanings' in word_data and word_data['meanings']:
                        meanings = word_data['meanings']
                        if len(meanings) > 0:
                            part_of_speech = meanings[0].get('partOfSpeech', '')
                    
                    return {
                        'phonetic': phonetic,
                        'part_of_speech': part_of_speech
                    }
            
            return None
            
        except Exception as e:
            print(f"获取音标信息失败: {e}")
            return None





class ImageFetcher:
    """图片获取类 - 支持多种免费图片生成服务"""
    
    def __init__(self):
        self.cache_dir = "image_cache"
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
        
        # 服务配置
        self.service_type = "unsplash"  # 默认使用 unsplash
        self.api_key = ""  # 部分服务不需要API密钥
        
        # 图片搜索服务配置
        self.services = {
            "unsplash": {
                "name": "Unsplash (免费)",
                "url": "https://api.unsplash.com/search/photos",
                "headers": {"Content-Type": "application/json"},
                "needs_key": True,
                "key_name": "Authorization",
                "key_prefix": "Client-ID "
            },
            "pixabay": {
                "name": "Pixabay (免费)",
                "url": "https://pixabay.com/api/",
                "headers": {"Content-Type": "application/json"},
                "needs_key": True,
                "key_name": "key",
                "key_prefix": ""
            },
            "pexels": {
                "name": "Pexels (免费)",
                "url": "https://api.pexels.com/v1/search",
                "headers": {"Content-Type": "application/json"},
                "needs_key": True,
                "key_name": "Authorization",
                "key_prefix": ""
            },
            "flickr": {
                "name": "Flickr (免费)",
                "url": "https://www.flickr.com/services/rest/",
                "headers": {"Content-Type": "application/json"},
                "needs_key": True,
                "key_name": "api_key",
                "key_prefix": ""
            }
        }
    
    def get_word_image(self, word, db_instance=None):
        """获取单词对应的图片"""
        try:
            # 首先尝试从数据库获取图片信息
            if db_instance:
                image_info = db_instance.get_word_image_info(word)
                if image_info and image_info.get('image_path'):
                    cache_file = image_info['image_path']
                    if os.path.exists(cache_file):
                        print(f"从数据库加载图片: {cache_file}")
                        return self.load_and_resize_image(cache_file)
            
            # 然后尝试从缓存加载
            cache_file = os.path.join(self.cache_dir, f"{word.lower()}.png")
            if os.path.exists(cache_file):
                print(f"从缓存加载图片: {cache_file}")
                return self.load_and_resize_image(cache_file)
            
            # 最后使用配置的服务搜索图片
            print(f"从网络搜索图片: {word}")
            image_data = self._search_image_with_service(word)
            if image_data:
                # 保存图片信息到数据库
                if db_instance:
                    image_path = os.path.join(self.cache_dir, f"{word.lower()}.png")
                    db_instance.save_word_image_info(word, image_path, "", self.service_type)
                return self._save_and_load_image(word, image_data)
            
            return None
        except Exception as e:
            print(f"获取图片失败: {e}")
            return None
    
    def _search_image_with_service(self, word):
        """使用配置的服务搜索图片"""
        try:
            service = self.services.get(self.service_type)
            if not service:
                print(f"未知的服务类型: {self.service_type}")
                return None
            
            # 准备请求头
            headers = service["headers"].copy()
            if service["needs_key"] and self.api_key:
                headers[service["key_name"]] = service["key_prefix"] + self.api_key
            
            # 根据服务类型构建请求
            if self.service_type == "unsplash":
                return self._call_unsplash(headers, word)
            elif self.service_type == "pixabay":
                return self._call_pixabay(headers, word)
            elif self.service_type == "pexels":
                return self._call_pexels(headers, word)
            elif self.service_type == "flickr":
                return self._call_flickr(headers, word)
            else:
                print(f"不支持的服务类型: {self.service_type}")
                return None
                
        except Exception as e:
            print(f"图片搜索失败: {e}")
            return None
    
    def _call_unsplash(self, headers, word):
        """调用 Unsplash API"""
        try:
            params = {
                "query": word,
                "per_page": 1,
                "orientation": "landscape"
            }
            
            response = requests.get(
                self.services["unsplash"]["url"],
                headers=headers,
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("results") and len(result["results"]) > 0:
                    # 获取图片URL
                    photo = result["results"][0]
                    image_url = photo["urls"]["regular"]
                    return self._download_image_data(image_url)
            elif response.status_code == 401:
                print("Unsplash Client ID无效或已过期")
            elif response.status_code == 403:
                print("Unsplash API访问被拒绝，请检查Client ID权限")
            else:
                print(f"Unsplash API错误，状态码: {response.status_code}")
            
            return None
        except Exception as e:
            print(f"Unsplash 调用失败: {e}")
            return None
    
    def _call_pixabay(self, headers, word):
        """调用 Pixabay API"""
        try:
            params = {
                "key": self.api_key,
                "q": word,
                "per_page": 1,
                "orientation": "horizontal"
            }
            
            response = requests.get(
                self.services["pixabay"]["url"],
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("hits") and len(result["hits"]) > 0:
                    image_url = result["hits"][0]["webformatURL"]
                    return self._download_image_data(image_url)
            
            return None
        except Exception as e:
            print(f"Pixabay 调用失败: {e}")
            return None
    
    def _call_pexels(self, headers, word):
        """调用 Pexels API"""
        try:
            params = {
                "query": word,
                "per_page": 1,
                "orientation": "landscape"
            }
            
            response = requests.get(
                self.services["pexels"]["url"],
                headers=headers,
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("photos") and len(result["photos"]) > 0:
                    image_url = result["photos"][0]["src"]["large"]
                    return self._download_image_data(image_url)
            
            return None
        except Exception as e:
            print(f"Pexels 调用失败: {e}")
            return None
    
    def _call_flickr(self, headers, word):
        """调用 Flickr API"""
        try:
            params = {
                "method": "flickr.photos.search",
                "api_key": self.api_key,
                "text": word,
                "per_page": 1,
                "format": "json",
                "nojsoncallback": 1,
                "sort": "relevance"
            }
            
            response = requests.get(
                self.services["flickr"]["url"],
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("photos", {}).get("photo") and len(result["photos"]["photo"]) > 0:
                    photo = result["photos"]["photo"][0]
                    image_url = f"https://live.staticflickr.com/{photo['server']}/{photo['id']}_{photo['secret']}_w.jpg"
                    return self._download_image_data(image_url)
            
            return None
        except Exception as e:
            print(f"Flickr 调用失败: {e}")
            return None
    
    def _download_image_data(self, image_url):
        """下载图片数据"""
        try:
            response = requests.get(image_url, timeout=15)
            if response.status_code == 200:
                return response.content
            return None
        except Exception as e:
            print(f"下载图片数据失败: {e}")
            return None
    
    def _save_and_load_image(self, word, image_data):
        """保存图片数据并加载"""
        try:
            cache_file = os.path.join(self.cache_dir, f"{word.lower()}.png")
            
            # 保存图片到缓存
            with open(cache_file, 'wb') as f:
                f.write(image_data)
            
            return self.load_and_resize_image(cache_file)
        except Exception as e:
            print(f"保存图片失败: {e}")
            return None
    
    def load_and_resize_image(self, image_path, max_width=300, max_height=200):
        """加载并调整图片大小"""
        try:
            image = Image.open(image_path)
            
            # 计算新的尺寸，保持宽高比
            width, height = image.size
            if width > max_width or height > max_height:
                ratio = min(max_width / width, max_height / height)
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            return ImageTk.PhotoImage(image)
        except Exception as e:
            print(f"处理图片失败: {e}")
            return None

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
        self.root.geometry("800x1100")
        self.root.configure(bg='#f0f0f0')

        self.db = WordDatabase()
        self.db.init_database()
        # 更新数据库结构（添加图片相关字段）
        self.db.update_database_schema()
        self.image_fetcher = ImageFetcher()
        self.current_word = None
        self.current_options = []
        self.study_session = []
        self.current_index = 0
        self.correct_count = 0

        # 加载MCP配置
        self.load_mcp_config()

        # 设置自定义样式
        self.setup_styles()
        self.setup_ui()
        
        # 初始化语音引擎
        init_engine()
        
        # 程序首次运行时自动刷新列表
        self.root.after(1000, self.auto_refresh_on_startup)

    def auto_refresh_on_startup(self):
        """程序启动时自动刷新列表"""
        try:
            # 检查是否有单词数据
            conn = sqlite3.connect(self.db.db_name)
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM words')
            word_count = cursor.fetchone()[0]
            conn.close()
            
            if word_count > 0:
                print("程序启动，自动刷新单词列表...")
                # 在新线程中执行刷新，避免阻塞UI
                import threading
                thread = threading.Thread(target=self.refresh_word_list, daemon=True)
                thread.start()
            else:
                print("词库为空，跳过自动刷新")
                
        except Exception as e:
            print(f"自动刷新失败: {e}")

    def setup_styles(self):
        """设置自定义样式"""
        style = ttk.Style()
        
        # 创建选项按钮样式
        style.configure(
            "Option.TButton",
            font=("Arial", 14),
            padding=(15, 12),
            relief="flat",
            background="#e8f4fd",
            foreground="#2c3e50"
        )
        
        # 创建强调按钮样式
        style.configure(
            "Accent.TButton",
            font=("Arial", 12, "bold"),
            padding=(15, 10),
            relief="flat",
            background="#3498db",
            foreground="white"
        )
        
        # 播放按钮样式
        style.configure(
            "Play.TButton",
            font=("Arial", 12),
            padding=(5, 5),
            relief="flat",
            background="#27ae60",
            foreground="white"
        )
        
        # 按钮悬停效果
        style.map(
            "Option.TButton",
            background=[("active", "#d1ecf1"), ("pressed", "#bee5eb")],
            relief=[("pressed", "sunken"), ("active", "raised")]
        )
        
        style.map(
            "Accent.TButton",
            background=[("active", "#2980b9"), ("pressed", "#21618c")],
            relief=[("pressed", "sunken"), ("active", "raised")]
        )
        
        style.map(
            "Play.TButton",
            background=[("active", "#2ecc71"), ("pressed", "#229954")],
            relief=[("pressed", "sunken"), ("active", "raised")]
        )
        
        # 黑色文字按钮样式
        style.configure(
            "BlackText.TButton",
            font=("Arial", 12, "bold"),
            padding=(15, 10),
            relief="flat",
            background="#3498db",
            foreground="black"
        )
        
        # 黑色图标按钮样式
        style.configure(
            "BlackIcon.TButton",
            font=("Arial", 12),
            padding=(5, 5),
            relief="flat",
            background="#27ae60",
            foreground="black"
        )

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
        
        # 设置选项卡
        self.setup_settings_tab(notebook)

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
        columns = ('单词', '音标', '释义', '分类', '正确率')
        self.word_tree = ttk.Treeview(list_frame, columns=columns, show='headings')

        # 设置列宽
        column_widths = {
            '单词': 120,
            '音标': 100,
            '释义': 200,
            '分类': 100,
            '正确率': 80
        }
        
        for col in columns:
            self.word_tree.heading(col, text=col)
            self.word_tree.column(col, width=column_widths.get(col, 150))

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
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            dict_frame,
            text="保存内存词典",
            command=self.save_memory_dictionary
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
        self.word_count_var = tk.StringVar(value="80")
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

        # 开始学习按钮 - 移动到最前面
        self.start_study_button = ttk.Button(
            self.scrollable_frame,
            text="开始学习",
            command=self.start_study,
            style="Accent.TButton"
        )
        self.start_study_button.pack(pady=20)
        
        # 设置开始学习按钮字体为黑色
        self.start_study_button.configure(style="BlackText.TButton")

        # 进度显示
        self.progress_label = ttk.Label(
            self.scrollable_frame,
            text="点击'开始学习'开始背单词",
            font=("Arial", 14)
        )
        self.progress_label.pack(pady=10)

        # 创建单词和图片的水平布局框架
        self.word_image_frame = ttk.Frame(self.scrollable_frame)
        self.word_image_frame.pack(pady=20, fill=tk.X, padx=20)
        
        # 左侧：单词显示
        self.word_left_frame = ttk.Frame(self.word_image_frame)
        self.word_left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.word_label = ttk.Label(
            self.word_left_frame,
            text="",
            font=("Arial", 48, "bold"),
            foreground="#2c3e50"
        )
        self.word_label.pack(pady=10)
        
        # 音标和播放按钮的水平布局
        self.phonetic_frame = ttk.Frame(self.word_left_frame)
        self.phonetic_frame.pack(pady=2)
        
        # 音标显示
        self.phonetic_label = ttk.Label(
            self.phonetic_frame,
            text="",
            font=("Arial", 16),
            foreground="#e74c3c"
        )
        self.phonetic_label.pack(side=tk.LEFT, padx=(0, 10))
        
        # 播放按钮
        self.play_button = ttk.Button(
            self.phonetic_frame,
            text="🔊",
            command=self.play_word_pronunciation,
            width=3,
            style="Play.TButton"
        )
        self.play_button.pack(side=tk.LEFT)
        
        # 设置播放按钮图标为黑色
        self.play_button.configure(style="BlackIcon.TButton")
        
        # 词性显示
        self.pos_label = ttk.Label(
            self.word_left_frame,
            text="",
            font=("Arial", 12, "italic"),
            foreground="#9b59b6"
        )
        self.pos_label.pack(pady=2)
        
        # 短语显示
        self.phrases_label = ttk.Label(
            self.word_left_frame,
            text="",
            font=("Arial", 14),
            foreground="#7f8c8d"
        )
        self.phrases_label.pack(pady=5)
        
        # 右侧：图片显示
        self.image_right_frame = ttk.Frame(self.word_image_frame)
        self.image_right_frame.pack(side=tk.RIGHT, padx=(20, 0))
        
        self.image_label = ttk.Label(
            self.image_right_frame,
            text="",
            font=("Arial", 10),
            foreground="#95a5a6"
        )
        self.image_label.pack()

        # 选项按钮框架
        self.options_frame = ttk.Frame(self.scrollable_frame)
        self.options_frame.pack(pady=20, fill=tk.X, padx=20)

        # 结果反馈
        self.feedback_label = ttk.Label(
            self.scrollable_frame,
            text="",
            font=("Arial", 18, "bold")
        )
        self.feedback_label.pack(pady=15)

        # 下一题按钮
        self.next_button = ttk.Button(
            self.scrollable_frame,
            text="下一题",
            command=self.next_question,
            state='disabled'
        )
        self.next_button.pack(pady=10)
        
        # 键盘提示
        self.keyboard_hint = ttk.Label(
            self.scrollable_frame,
            text="💡 提示：按空格键可快速切换到下一题",
            font=("Arial", 10),
            foreground="#7f8c8d"
        )
        self.keyboard_hint.pack(pady=5)

        # 布局滚动组件
        self.main_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 绑定鼠标滚轮事件
        def _on_mousewheel(event):
            self.main_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        self.main_canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        # 绑定键盘事件
        self.root.bind("<space>", self.on_space_key)

    def load_mcp_config(self):
        """加载图片生成服务配置"""
        try:
            config_file = "image_service_config.json"
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.image_fetcher.service_type = config.get('service_type', 'stable_diffusion')
                    self.image_fetcher.api_key = config.get('api_key', '')
            else:
                # 创建默认配置
                self.save_mcp_config()
        except Exception as e:
            print(f"加载配置失败: {e}")

    def save_mcp_config(self):
        """保存图片生成服务配置"""
        try:
            config = {
                'service_type': self.image_fetcher.service_type,
                'api_key': self.image_fetcher.api_key
            }
            with open("image_service_config.json", 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")

    def setup_settings_tab(self, notebook):
        """设置配置选项卡"""
        settings_frame = ttk.Frame(notebook, padding="20")
        notebook.add(settings_frame, text="设置")

        # 图片生成服务配置区域
        service_frame = ttk.LabelFrame(settings_frame, text="图片生成服务配置", padding="10")
        service_frame.pack(fill=tk.X, pady=10)

        # 服务选择
        ttk.Label(service_frame, text="选择图片生成服务:").pack(anchor=tk.W, pady=5)
        self.service_var = tk.StringVar(value=self.image_fetcher.service_type)
        service_combo = ttk.Combobox(service_frame, textvariable=self.service_var, state="readonly", width=30)
        service_combo['values'] = list(self.image_fetcher.services.keys())
        service_combo.pack(anchor=tk.W, pady=5)
        service_combo.bind('<<ComboboxSelected>>', self.on_service_changed)

        # API密钥
        ttk.Label(service_frame, text="API密钥 (部分服务需要):").pack(anchor=tk.W, pady=5)
        self.api_key_entry = ttk.Entry(service_frame, width=50, show="*")
        self.api_key_entry.insert(0, self.image_fetcher.api_key)
        self.api_key_entry.pack(fill=tk.X, pady=5)

        # 保存按钮
        ttk.Button(service_frame, text="保存配置", command=self.save_service_settings).pack(pady=10)

        # 测试连接按钮
        ttk.Button(service_frame, text="测试服务连接", command=self.test_service_connection).pack(pady=5)

        # 服务说明
        info_text = """
免费图片搜索服务说明：

1. **Unsplash (免费)** - 高质量免费图片
   - 注册地址: https://unsplash.com/developers
   - 需要Client ID，每月5000次免费请求
   - 获取Client ID步骤：
     a) 访问 https://unsplash.com/developers
     b) 注册开发者账号
     c) 创建新应用
     d) 复制Client ID

2. **Pixabay (免费)** - 免费图片和视频
   - 注册地址: https://pixabay.com/api/docs/
   - 需要API密钥，每日5000次免费请求

3. **Pexels (免费)** - 免费高质量图片
   - 注册地址: https://www.pexels.com/api/
   - 需要API密钥，每月200次免费请求

4. **Flickr (免费)** - 大量用户上传图片
   - 注册地址: https://www.flickr.com/services/api/
   - 需要API密钥，每日3600次免费请求

选择服务后，系统会根据英文单词搜索相关图片。
        """
        info_label = ttk.Label(settings_frame, text=info_text, justify=tk.LEFT, foreground="#666")
        info_label.pack(pady=20, anchor=tk.W)

    def on_service_changed(self, event=None):
        """服务选择改变时的处理"""
        selected_service = self.service_var.get()
        if selected_service in self.image_fetcher.services:
            service_info = self.image_fetcher.services[selected_service]
            print(f"切换到服务: {service_info['name']}")

    def save_service_settings(self):
        """保存服务设置"""
        try:
            self.image_fetcher.service_type = self.service_var.get()
            self.image_fetcher.api_key = self.api_key_entry.get().strip()
            self.save_mcp_config()
            messagebox.showinfo("成功", "服务配置已保存")
        except Exception as e:
            messagebox.showerror("错误", f"保存配置失败: {e}")

    def test_service_connection(self):
        """测试服务连接"""
        try:
            # 更新配置
            self.image_fetcher.service_type = self.service_var.get()
            self.image_fetcher.api_key = self.api_key_entry.get().strip()
            
            # 测试连接
            service = self.image_fetcher.services.get(self.image_fetcher.service_type)
            if not service:
                messagebox.showerror("错误", "未知的服务类型")
                return
            
            headers = service["headers"].copy()
            if service["needs_key"] and self.image_fetcher.api_key:
                headers[service["key_name"]] = service["key_prefix"] + self.image_fetcher.api_key
            
            # 简单的连接测试
            if self.image_fetcher.service_type == "unsplash":
                response = requests.get(
                    "https://api.unsplash.com/search/photos",
                    headers=headers,
                    params={"query": "test", "per_page": 1},
                    timeout=10
                )
            elif self.image_fetcher.service_type == "pixabay":
                response = requests.get(
                    "https://pixabay.com/api/",
                    params={"key": self.image_fetcher.api_key, "q": "test"},
                    timeout=10
                )
            elif self.image_fetcher.service_type == "pexels":
                response = requests.get(
                    "https://api.pexels.com/v1/search",
                    headers=headers,
                    params={"query": "test", "per_page": 1},
                    timeout=10
                )
            elif self.image_fetcher.service_type == "flickr":
                response = requests.get(
                    "https://www.flickr.com/services/rest/",
                    params={
                        "method": "flickr.test.echo",
                        "api_key": self.image_fetcher.api_key,
                        "format": "json",
                        "nojsoncallback": 1
                    },
                    timeout=10
                )
            else:
                messagebox.showinfo("提示", "该服务的连接测试功能暂未实现")
                return
            
            if response.status_code == 200:
                messagebox.showinfo("成功", "服务连接测试成功！")
            else:
                messagebox.showerror("错误", f"服务连接失败，状态码: {response.status_code}")
        except Exception as e:
            messagebox.showerror("错误", f"服务连接测试失败: {e}")

    def on_space_key(self, event):
        """处理空格键事件"""
        # 如果下一题按钮可用，则切换到下一题
        if hasattr(self, 'next_button') and self.next_button.cget('state') == 'normal':
            self.next_question()
        # 阻止默认的空格键行为（如滚动）
        return "break"
    
    def play_word_pronunciation(self):
        """播放单词发音"""
        if not self.current_word:
            print("当前单词为空，无法播放")
            return
        
        print(f"尝试播放单词: {self.current_word}")
        
        try:
            # 检查按钮是否已经被禁用
            if self.play_button.cget('state') == 'disabled':
                print("播放按钮已被禁用，忽略重复点击")
                return
            
            # 禁用播放按钮，防止重复点击
            self.play_button.config(state='disabled', text="⏸️")
            print(f"按钮已禁用，开始播放: {self.current_word}")
            
            # 直接播放单词发音
            speak(self.current_word)
            print(f"播放完成: {self.current_word}")
            # 播放完成后恢复按钮
            self.restore_play_button()
                
        except Exception as e:
            print(f"播放发音时出错: {e}")
            # 出错时恢复按钮状态
            self.restore_play_button()
    


    def restore_play_button(self):
        """恢复播放按钮状态"""
        try:
            # 检查按钮是否存在
            if hasattr(self, 'play_button') and self.play_button.winfo_exists():
                # 直接恢复按钮状态
                self.play_button.config(state='normal', text="🔊")
                print("播放按钮已恢复")
            else:
                print("播放按钮不存在或已销毁")
        except Exception as e:
            print(f"恢复播放按钮失败: {e}")
            # 出错时尝试强制恢复
            try:
                if hasattr(self, 'play_button') and self.play_button.winfo_exists():
                    self.play_button.config(state='normal', text="🔊")
                    print("出错后强制恢复播放按钮")
            except Exception as e2:
                print(f"强制恢复也失败: {e2}")
    
    def cleanup_tts(self):
        """清理语音引擎资源"""
        cleanup_engine()
        print("语音引擎资源已清理")

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
            
            def update_progress(message, current_words=0, total_processed=0, current_file="", current_word="", word_info=""):
                """更新进度显示"""
                progress_label.config(text=message)
                
                # 显示当前处理的文件和单词
                if current_file and current_word:
                    detail_text = f"当前文件: {current_file}\n当前单词: {current_word}"
                    if word_info:
                        detail_text += f"\n单词信息: {word_info}"
                    detail_text += f"\n已处理单词: {current_words}"
                elif current_file:
                    detail_text = f"当前文件: {current_file}\n已处理单词: {current_words}"
                else:
                    detail_text = f"已处理单词: {current_words}"
                
                detail_label.config(text=detail_text)
                stats_label.config(text=f"新增: {inserted_count} | 更新: {updated_count} | 翻译: {translated_count} | 音标: {phonetic_count}")
                progress_dialog.update()
            
            total_words = 0
            inserted_count = 0
            updated_count = 0
            translated_count = 0
            phonetic_count = 0
            
            try:
                # 第一阶段：扫描文件夹
                update_progress("正在扫描PDF文件...")
                all_words = PDFWordExtractor.batch_extract_from_folder_smart(folder_path, self.db)
                
                # 计算总单词数
                total_word_count = sum(len(words) for words in all_words.values())
                progress_bar.stop()
                progress_bar.config(mode='determinate', maximum=total_word_count)
                
                # 第二阶段：处理单词
                processed_words = 0
                for category, words in all_words.items():
                    update_progress(f"正在处理分类: {category}", processed_words)
                    
                    for word_data in words:
                        # 更新进度，显示当前处理的单词
                        current_word = word_data['word']
                        
                        # 构建单词信息字符串
                        word_info_parts = []
                        if word_data.get('phonetic'):
                            word_info_parts.append(f"音标: {word_data['phonetic']}")
                        if word_data.get('part_of_speech'):
                            word_info_parts.append(f"词性: {word_data['part_of_speech']}")
                        if word_data.get('definition') and word_data['definition'] != "暂无释义":
                            # 截取前30个字符的释义
                            definition_preview = word_data['definition'][:30] + "..." if len(word_data['definition']) > 30 else word_data['definition']
                            word_info_parts.append(f"释义: {definition_preview}")
                        
                        word_info = " | ".join(word_info_parts) if word_info_parts else "基本信息"
                        
                        update_progress(f"正在处理分类: {category}", processed_words, current_word=current_word, word_info=word_info)
                        # 检查是否是通过在线翻译获取的释义
                        if word_data['definition'] and word_data['definition'] != "暂无释义":
                            # 检查是否是新翻译的（通过检查本地词典中是否已有该单词）
                            if local_dict and word_data['word'].lower() not in local_dict.dictionary:
                                translated_count += 1
                        
                        # 检查是否获取到了音标信息
                        if word_data.get('phonetic', '') or word_data.get('part_of_speech', ''):
                            phonetic_count += 1
                        
                        result = self.db.add_or_update_word(
                            word_data['word'], 
                            word_data['definition'], 
                            word_data['phrases'], 
                            word_data['category'],
                            word_data.get('image_path', ''),
                            word_data.get('image_url', ''),
                            word_data.get('image_service', ''),
                            word_data.get('phonetic', ''),
                            word_data.get('part_of_speech', ''),
                            word_data.get('pronunciation', ''),
                            word_data.get('detailed_info', '')
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
                stats_label.config(text=f"新增: {inserted_count} | 更新: {updated_count} | 翻译: {translated_count} | 音标: {phonetic_count}")
                
                # 延迟显示完成消息
                progress_dialog.after(2000, lambda: self._show_folder_import_complete(progress_dialog, total_words, inserted_count, updated_count, translated_count, phonetic_count))
                
            except Exception as e:
                progress_dialog.destroy()
                messagebox.showerror("导入错误", f"批量导入过程中出现错误：{e}")
                print(f"批量导入错误: {e}")
    
    def _show_folder_import_complete(self, progress_dialog, total_words, inserted_count, updated_count, translated_count, phonetic_count=0):
        """显示文件夹导入完成消息"""
        progress_dialog.destroy()
        
        # 显示详细的导入结果
        result_message = f"批量导入完成！\n\n"
        result_message += f"总处理单词数: {total_words}\n"
        result_message += f"新增单词数: {inserted_count}\n"
        result_message += f"更新单词数: {updated_count}\n"
        result_message += f"在线翻译单词数: {translated_count}\n"
        result_message += f"获取音标单词数: {phonetic_count}"
        
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
        phonetic_count = 0
        
        # 计算总文件数
        total_files = len(file_paths)
        progress_bar['maximum'] = total_files
        
        def update_progress(file_index, filename, current_words, total_processed, current_word="", word_info=""):
            """更新进度显示"""
            progress = (file_index + 1) / total_files * 100
            progress_bar['value'] = file_index + 1
            
            progress_label.config(text=f"正在处理文件 {file_index + 1}/{total_files}")
            
            # 显示当前处理的文件和单词
            if current_word:
                detail_text = f"当前文件: {filename}\n当前单词: {current_word}"
                if word_info:
                    detail_text += f"\n单词信息: {word_info}"
                detail_text += f"\n已处理单词: {current_words}"
            else:
                detail_text = f"当前文件: {filename}\n已处理单词: {current_words}"
            
            detail_label.config(text=detail_text)
            stats_label.config(text=f"新增: {inserted_count} | 更新: {updated_count} | 翻译: {translated_count} | 音标: {phonetic_count}")
            
            progress_dialog.update()

        try:
            for file_index, file_path in enumerate(file_paths):
                filename = os.path.basename(file_path)
                update_progress(file_index, filename, 0, total_words)
                
                # 提取单词（使用智能翻译方法）
                words_with_categories = PDFWordExtractor.extract_words_with_smart_translation(file_path, self.db)
                
                # 处理单词
                for word_index, word_data in enumerate(words_with_categories):
                    current_word = word_data['word']
                    
                    # 构建单词信息字符串
                    word_info_parts = []
                    if word_data.get('phonetic'):
                        word_info_parts.append(f"音标: {word_data['phonetic']}")
                    if word_data.get('part_of_speech'):
                        word_info_parts.append(f"词性: {word_data['part_of_speech']}")
                    if word_data.get('definition') and word_data['definition'] != "暂无释义":
                        # 截取前30个字符的释义
                        definition_preview = word_data['definition'][:30] + "..." if len(word_data['definition']) > 30 else word_data['definition']
                        word_info_parts.append(f"释义: {definition_preview}")
                    
                    word_info = " | ".join(word_info_parts) if word_info_parts else "基本信息"
                    
                    # 更新进度，显示当前处理的单词
                    update_progress(file_index, filename, word_index, total_words, current_word, word_info)
                    
                    # 检查是否是通过在线翻译获取的释义
                    if word_data['definition'] and word_data['definition'] != "暂无释义":
                        # 检查是否是新翻译的（通过检查本地词典中是否已有该单词）
                        if local_dict and word_data['word'].lower() not in local_dict.dictionary:
                            translated_count += 1
                    
                    # 检查是否获取到了音标信息
                    if word_data.get('phonetic', '') or word_data.get('part_of_speech', ''):
                        phonetic_count += 1
                    
                    result = self.db.add_or_update_word(
                        word_data['word'], 
                        word_data['definition'], 
                        word_data['phrases'], 
                        word_data['category'],
                        word_data.get('image_path', ''),
                        word_data.get('image_url', ''),
                        word_data.get('image_service', ''),
                        word_data.get('phonetic', ''),
                        word_data.get('part_of_speech', ''),
                        word_data.get('pronunciation', ''),
                        word_data.get('detailed_info', '')
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
            stats_label.config(text=f"新增: {inserted_count} | 更新: {updated_count} | 翻译: {translated_count} | 音标: {phonetic_count}")
            
            # 延迟显示完成消息
            progress_dialog.after(2000, lambda: self._show_import_complete(progress_dialog, total_words, inserted_count, updated_count, translated_count, phonetic_count))
            
        except Exception as e:
            progress_dialog.destroy()
            messagebox.showerror("导入错误", f"导入过程中出现错误：{e}")
            print(f"导入错误: {e}")
    
    def _show_import_complete(self, progress_dialog, total_words, inserted_count, updated_count, translated_count, phonetic_count=0):
        """显示导入完成消息"""
        progress_dialog.destroy()
        
        # 显示详细的导入结果
        result_message = f"导入完成！\n\n"
        result_message += f"总处理单词数: {total_words}\n"
        result_message += f"新增单词数: {inserted_count}\n"
        result_message += f"更新单词数: {updated_count}\n"
        result_message += f"在线翻译单词数: {translated_count}\n"
        result_message += f"获取音标单词数: {phonetic_count}"
        
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
                       SELECT word, definition, category, correct_count, wrong_count, phonetic
                       FROM words
                       ORDER BY word
                       ''')

        # 创建进度对话框
        progress_dialog = tk.Toplevel(self.root)
        progress_dialog.title("刷新单词列表")
        progress_dialog.geometry("300x150")
        progress_dialog.transient(self.root)
        progress_dialog.grab_set()
        
        # 居中显示
        progress_dialog.update_idletasks()
        x = (progress_dialog.winfo_screenwidth() // 2) - (300 // 2)
        y = (progress_dialog.winfo_screenheight() // 2) - (150 // 2)
        progress_dialog.geometry(f"300x150+{x}+{y}")
        
        # 进度标签
        progress_label = ttk.Label(progress_dialog, text="正在刷新单词列表...", font=("Arial", 12))
        progress_label.pack(pady=20)
        
        # 详细进度标签
        detail_label = ttk.Label(progress_dialog, text="", font=("Arial", 10))
        detail_label.pack(pady=10)
        
        # 统计标签
        stats_label = ttk.Label(progress_dialog, text="", font=("Arial", 10))
        stats_label.pack(pady=10)
        
        def update_progress(message, current_word="", updated_count=0, total_count=0):
            """更新进度显示"""
            progress_label.config(text=message)
            if current_word:
                detail_label.config(text=f"当前处理: {current_word}")
            stats_label.config(text=f"已更新: {updated_count} / 总计: {total_count}")
            progress_dialog.update()
        
        try:
            rows = cursor.fetchall()
            total_words = len(rows)
            updated_count = 0
            local_dict_count = 0
            online_translate_count = 0
            
            update_progress("开始刷新单词列表", total_count=total_words)
            
            for i, row in enumerate(rows):
                word, definition, category, correct, wrong, phonetic = row
                
                # 更新进度
                update_progress(f"正在处理第 {i+1}/{total_words} 个单词", word, updated_count, total_words)
                
                # 检查是否需要获取音标和释义
                if not phonetic or not definition or definition == "":
                    word_lower = word.lower()
                    
                    # 首先尝试从本地词典库获取信息
                    if local_dict is not None:
                        local_word_info = local_dict.dictionary.get(word_lower, {})
                        
                        # 如果本地词典库有信息，更新数据库
                        if local_word_info.get('definition') or local_word_info.get('phonetic'):
                            new_definition = local_word_info.get('definition', definition)
                            new_phonetic = local_word_info.get('phonetic', phonetic)
                            new_part_of_speech = local_word_info.get('part_of_speech', '')
                            
                            # 更新数据库
                            cursor.execute('''
                                           UPDATE words 
                                           SET definition = ?, phonetic = ?, part_of_speech = ?
                                           WHERE word = ?
                                           ''', (new_definition, new_phonetic, new_part_of_speech, word))
                            
                            definition = new_definition
                            phonetic = new_phonetic
                            updated_count += 1
                            local_dict_count += 1
                            
                            print(f"已为单词 '{word}' 从本地词典库更新信息")
                    
                    # 如果本地词典库没有信息，且单词暂无释义，调用百度API
                    if not definition or definition == "暂无释义":
                        try:
                            update_progress(f"正在为 '{word}' 调用百度API获取释义", word, updated_count, total_words)
                            
                            # 创建在线翻译器实例
                            translator = OnlineTranslator()
                            new_definition, phrases, detailed_info = translator.translate_word(word)
                            
                            # 如果在线翻译成功，更新数据库
                            if new_definition and new_definition != "暂无释义" and new_definition != word:
                                # 提取详细信息
                                new_phonetic = ""
                                new_part_of_speech = ""
                                pronunciation = ""
                                detailed_text = ""
                                
                                if isinstance(detailed_info, dict):
                                    new_phonetic = detailed_info.get('phonetic', '')
                                    new_part_of_speech = detailed_info.get('part_of_speech', '')
                                    pronunciation = detailed_info.get('pronunciation', '')
                                    detailed_text = detailed_info.get('detailed_info', '')
                                
                                # 更新数据库
                                cursor.execute('''
                                               UPDATE words 
                                               SET definition = ?, phonetic = ?, part_of_speech = ?
                                               WHERE word = ?
                                               ''', (new_definition, new_phonetic, new_part_of_speech, word))
                                
                                # 同时保存到本地词典库
                                if local_dict is not None:
                                    local_dict.add_word(word, new_definition, phrases, new_phonetic, new_part_of_speech, pronunciation, detailed_text)
                                
                                definition = new_definition
                                phonetic = new_phonetic
                                updated_count += 1
                                online_translate_count += 1
                                
                                print(f"已为单词 '{word}' 通过百度API获取释义: {new_definition}")
                            else:
                                print(f"百度API翻译结果无效或为空: {word} -> {new_definition}")
                                
                        except Exception as e:
                            print(f"为单词 '{word}' 调用百度API失败: {e}")
                            # 继续处理下一个单词，不中断整个流程
                
                # 计算正确率
                total = correct + wrong
                accuracy = f"{correct/total*100:.1f}%" if total > 0 else "未测试"

                # 截短释义
                short_def = definition[:30] + "..." if len(definition) > 30 else definition if definition else ""

                # 格式化音标显示
                phonetic_display = f"/{phonetic}/" if phonetic else ""
                
                # 插入到表格
                self.word_tree.insert('', 'end', values=(word, phonetic_display, short_def, category, accuracy))
                
                # 每处理10个单词更新一次进度
                if (i + 1) % 10 == 0:
                    update_progress(f"已处理 {i+1}/{total_words} 个单词", word, updated_count, total_words)
            
            # 提交数据库更改
            conn.commit()
            
            # 显示完成消息
            update_progress("刷新完成！", updated_count=updated_count, total_count=total_words)
            
            # 显示详细统计信息
            stats_message = f"刷新完成！\n\n"
            stats_message += f"总单词数: {total_words}\n"
            stats_message += f"从本地词典库更新: {local_dict_count} 个单词\n"
            stats_message += f"通过百度API获取: {online_translate_count} 个单词\n"
            stats_message += f"总计更新: {updated_count} 个单词"
            
            # 延迟显示统计信息
            progress_dialog.after(1000, lambda: messagebox.showinfo("刷新完成", stats_message))
            
            # 延迟关闭进度对话框
            progress_dialog.after(2000, progress_dialog.destroy)
            
        except Exception as e:
            progress_dialog.destroy()
            messagebox.showerror("错误", f"刷新单词列表时出错：{e}")
            print(f"刷新单词列表错误: {e}")
        finally:
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

        # 隐藏开始学习按钮
        if hasattr(self, 'start_study_button'):
            self.start_study_button.pack_forget()
        
        # 隐藏键盘提示
        if hasattr(self, 'keyboard_hint'):
            self.keyboard_hint.pack_forget()

        self.show_question()

    def show_question(self):
        """显示题目"""
        if self.current_index >= len(self.study_session):
            self.show_study_results()
            return

        word_data = self.study_session[self.current_index]
        self.current_word = word_data[0]
        correct_definition = word_data[1]
        
        print(f"显示新题目，当前单词: {self.current_word}")

        # 更新进度
        progress = f"第 {self.current_index + 1} 题 / 共 {len(self.study_session)} 题"
        self.progress_label.config(text=progress)

        # 显示单词
        self.word_label.config(text=self.current_word.lower())
        
        # 显示音标和词性
        phonetic = word_data[9] if len(word_data) > 9 else ""  # phonetic
        part_of_speech = word_data[10] if len(word_data) > 10 else ""  # part_of_speech
        
        if phonetic:
            self.phonetic_label.config(text=f"/{phonetic}/")
            self.play_button.config(state='normal')  # 启用播放按钮
        else:
            self.phonetic_label.config(text="")
            self.play_button.config(state='disabled')  # 禁用播放按钮
            
        if part_of_speech:
            self.pos_label.config(text=f"({part_of_speech})")
        else:
            self.pos_label.config(text="")
        
        # 显示短语
        phrases = word_data[2] if isinstance(word_data[2], list) else []
        if phrases:
            phrases_text = "; ".join([f"{p.get('phrase', '')}: {p.get('translation', '')}" for p in phrases[:3]])
            self.phrases_label.config(text=phrases_text)
        else:
            self.phrases_label.config(text="")

        # 加载并显示图片
        self.load_word_image(self.current_word)

        # 生成选项
        self.generate_options(correct_definition)

        # 重置反馈和按钮
        self.feedback_label.config(text="", foreground="black")
        self.next_button.config(state='disabled')
        
        # 清空选项按钮列表
        if hasattr(self, 'option_buttons'):
            self.option_buttons.clear()
        
        # 滚动到顶部
        if hasattr(self, 'main_canvas'):
            self.main_canvas.update_idletasks()
            self.main_canvas.yview_moveto(0)

    def load_word_image(self, word):
        """加载并显示单词对应的图片"""
        try:
            print(f"开始加载单词 '{word}' 的图片...")
            # 显示加载提示
            self.image_label.config(text="🖼️ 加载图片中...", image="")
            
            # 在后台线程中加载图片
            def load_image_thread():
                try:
                    print(f"后台线程开始搜索图片: {word}")
                    image = self.image_fetcher.get_word_image(word, self.db)
                    if image:
                        print(f"图片加载成功，类型: {type(image)}")
                        # 保存图片引用，防止被垃圾回收
                        self.current_image = image
                        # 在主线程中更新UI
                        self.root.after(0, lambda: self.update_image_display(image))
                    else:
                        print(f"图片加载失败，未找到图片")
                        # 显示默认图标
                        self.root.after(0, lambda: self.update_image_display(None))
                except Exception as e:
                    print(f"加载图片失败: {e}")
                    self.root.after(0, lambda: self.update_image_display(None))
            
            # 启动后台线程
            threading.Thread(target=load_image_thread, daemon=True).start()
            
        except Exception as e:
            print(f"加载图片失败: {e}")
            self.image_label.config(text="🖼️", image="")
    
    def update_image_display(self, image):
        """更新图片显示"""
        try:
            print(f"更新图片显示，图片对象: {image}")
            if image:
                print(f"设置图片到标签，图片类型: {type(image)}")
                self.image_label.config(image=image, text="")
                print(f"图片显示成功，尺寸: {image.width()}x{image.height()}")
                # 强制更新界面
                self.image_label.update()
            else:
                print("设置默认图标")
                self.image_label.config(text="🖼️", image="")
                self.image_label.update()
        except Exception as e:
            print(f"更新图片显示失败: {e}")
            self.image_label.config(text="🖼️", image="")
            self.image_label.update()

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
            # 截短选项文本，增加显示长度
            display_text = option[:80] + "..." if len(option) > 80 else option

            # 创建选项按钮框架
            option_frame = ttk.Frame(self.options_frame)
            option_frame.pack(pady=8, fill=tk.X, padx=10)
            
            btn = ttk.Button(
                option_frame,
                text=f"{chr(65+i)}. {display_text}",
                command=lambda opt=option: self.check_answer(opt),
                style="Option.TButton"
            )
            btn.pack(fill=tk.X, padx=5)
            
            # 存储按钮引用以便后续禁用
            if not hasattr(self, 'option_buttons'):
                self.option_buttons = []
            self.option_buttons.append(btn)

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
        if hasattr(self, 'option_buttons'):
            for button in self.option_buttons:
                button.config(state='disabled')
        else:
            # 备用方案：禁用所有子组件
            for widget in self.options_frame.winfo_children():
                widget.config(state='disabled')

        # 启用下一题按钮
        self.next_button.config(state='normal')

    def next_question(self):
        """下一题"""
        self.current_index += 1
        print(f"切换到下一题，索引: {self.current_index}")
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
        self.phonetic_label.config(text="")
        self.play_button.config(state='disabled')  # 禁用播放按钮
        self.pos_label.config(text="")
        self.phrases_label.config(text="")
        self.image_label.config(text="", image="")
        # 清理图片引用
        if hasattr(self, 'current_image'):
            delattr(self, 'current_image')
        self.feedback_label.config(text=result_text, foreground="blue")

        # 清空选项
        for widget in self.options_frame.winfo_children():
            widget.destroy()

        self.next_button.config(text="重新开始", state='normal', command=self.reset_study)

    def reset_study(self):
        """重置学习"""
        self.progress_label.config(text="点击'开始学习'开始背单词")
        self.word_label.config(text="")
        self.phonetic_label.config(text="")
        self.play_button.config(state='disabled')  # 禁用播放按钮
        self.pos_label.config(text="")
        self.phrases_label.config(text="")
        self.image_label.config(text="", image="")
        # 清理图片引用
        if hasattr(self, 'current_image'):
            delattr(self, 'current_image')
        self.feedback_label.config(text="")

        for widget in self.options_frame.winfo_children():
            widget.destroy()

        self.next_button.config(text="下一题", state='disabled', command=self.next_question)
        
        # 重新显示开始学习按钮
        if hasattr(self, 'start_study_button'):
            self.start_study_button.pack(pady=20)
        
        # 显示键盘提示
        if hasattr(self, 'keyboard_hint'):
            self.keyboard_hint.pack(pady=5)
        
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
        # 显示确认对话框
        result = messagebox.askyesno(
            "确认重建", 
            "确定要重建基础词典吗？\n\n这将：\n- 清空本地词典库数据库\n- 清空本地词典库JSON文件\n- 重新创建基础词典\n\n此操作不可恢复！"
        )
        
        if result:
            try:
                # 清空本地词典库数据库
                local_dict.clear_dictionary_database()
                
                # 清空本地词典库JSON文件
                local_dict.clear_dictionary_file()
                
                # 重新创建基础词典
                local_dict.dictionary = local_dict.create_basic_dictionary()
                local_dict.save_dictionary()
                
                messagebox.showinfo("成功", f"基础词典重建成功！\n\n已清空：\n- 本地词典库数据库\n- 本地词典库JSON文件\n\n新词典包含 {local_dict.get_dictionary_size()} 个单词")
            except Exception as e:
                messagebox.showerror("错误", f"重建词典失败：{e}")
                print(f"重建词典时出错: {e}")

    def save_memory_dictionary(self):
        """保存内存词典到本地词典库"""
        try:
            # 获取内存中的词典大小
            memory_size = len(local_dict.dictionary)
            
            if memory_size == 0:
                messagebox.showwarning("警告", "内存词典为空，没有可保存的内容")
                return
            
            # 保存内存词典到数据库
            saved_count = local_dict.save_to_database()
            
            # 显示保存结果
            result_message = f"内存词典保存成功！\n\n"
            result_message += f"内存中单词数: {memory_size}\n"
            result_message += f"成功保存到数据库: {saved_count} 个单词\n"
            result_message += f"词典文件: {local_dict.dict_file}\n"
            result_message += f"数据库文件: {local_dict.db_file}"
            
            messagebox.showinfo("保存成功", result_message)
            
        except Exception as e:
            messagebox.showerror("错误", f"保存内存词典失败：{e}")

# 初始化全局本地词典实例
def init_local_dictionary():
    """初始化全局本地词典实例"""
    global local_dict
    local_dict = LocalDictionary()



def main():
    """主函数"""
    # 初始化本地词典
    init_local_dictionary()
    
    root = tk.Tk()
    app = VocabularyApp(root)
    
    # 设置窗口关闭事件处理
    def on_closing():
        try:
            app.cleanup_tts()  # 清理语音引擎资源
            print("程序退出，已清理语音引擎资源")
        except Exception as e:
            print(f"清理语音引擎资源时出错: {e}")
        finally:
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()