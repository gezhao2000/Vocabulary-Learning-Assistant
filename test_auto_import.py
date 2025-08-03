import os
import sys

# Add the current directory to the path so we can import from Vocabulary.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_auto_import():
    """测试自动导入功能"""
    print("开始测试自动导入功能...")
    
    # 检查当前目录下的JSON文件
    current_dir = os.getcwd()
    json_files = []
    
    for file in os.listdir(current_dir):
        if file.endswith('.json') and file != 'gaokao_dictionary.json':
            json_files.append(os.path.join(current_dir, file))
    
    print(f"发现 {len(json_files)} 个JSON文件:")
    for file in json_files:
        print(f"  - {os.path.basename(file)}")
    
    # 测试优先级排序
    def get_priority_score(filename):
        filename_lower = filename.lower()
        priority = 0
        if any(keyword in filename_lower for keyword in ['词典', 'dictionary', 'vocabulary', 'gaokao', '高考']):
            priority += 10
        if 'english' in filename_lower:
            priority += 5
        return priority
    
    if json_files:
        json_files.sort(key=lambda x: get_priority_score(os.path.basename(x)), reverse=True)
        print(f"\n按优先级排序后的文件:")
        for file in json_files:
            score = get_priority_score(os.path.basename(file))
            print(f"  - {os.path.basename(file)} (优先级: {score})")
    
    print("\n测试完成!")

if __name__ == "__main__":
    test_auto_import() 