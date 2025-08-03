import os
import json

def test_auto_import_logic():
    """测试自动导入逻辑"""
    print("=== 测试自动导入逻辑 ===")
    
    # 检查当前目录下的JSON文件
    current_dir = os.getcwd()
    print(f"当前目录: {current_dir}")
    
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
        
        # 尝试读取第一个文件的前几行
        first_file = json_files[0]
        print(f"\n尝试读取文件: {os.path.basename(first_file)}")
        try:
            with open(first_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    print(f"文件包含 {len(data)} 个条目")
                    if len(data) > 0:
                        print(f"第一个条目: {data[0]}")
                elif isinstance(data, dict):
                    print(f"文件包含 {len(data)} 个键值对")
                    if len(data) > 0:
                        first_key = list(data.keys())[0]
                        print(f"第一个键值对: {first_key} -> {data[first_key]}")
        except Exception as e:
            print(f"读取文件失败: {e}")
    
    print("\n=== 测试完成 ===")

if __name__ == "__main__":
    test_auto_import_logic() 