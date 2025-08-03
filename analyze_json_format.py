import json
import os

def analyze_json_format(file_path):
    """分析JSON文件的格式"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"\n=== 分析文件: {os.path.basename(file_path)} ===")
        print(f"数据类型: {type(data)}")
        
        if isinstance(data, dict):
            print(f"字典键数量: {len(data)}")
            if data:
                # 获取前几个键值对作为示例
                sample_items = list(data.items())[:3]
                print("示例键值对:")
                for key, value in sample_items:
                    print(f"  键: {key}")
                    print(f"  值类型: {type(value)}")
                    print(f"  值: {value}")
                    print()
        
        elif isinstance(data, list):
            print(f"列表长度: {len(data)}")
            if data:
                print("示例项目:")
                for i, item in enumerate(data[:3]):
                    print(f"  项目 {i+1}:")
                    print(f"    类型: {type(item)}")
                    print(f"    内容: {item}")
                    print()
        
        # 尝试识别词典结构
        if isinstance(data, dict):
            # 检查是否是单词词典格式
            sample_key = next(iter(data.keys()))
            sample_value = data[sample_key]
            
            if isinstance(sample_value, dict):
                print("检测到词典格式:")
                print(f"  单词: {sample_key}")
                print(f"  单词信息: {sample_value}")
                
                # 检查常见字段
                common_fields = ['definition', 'translation', 'pronunciation', 'phonetic', 'phrases', 'examples']
                found_fields = []
                for field in common_fields:
                    if field in sample_value:
                        found_fields.append(field)
                
                if found_fields:
                    print(f"  包含字段: {found_fields}")
                else:
                    print("  未识别到常见词典字段")
        
        elif isinstance(data, list) and data:
            # 检查列表中的项目结构
            sample_item = data[0]
            if isinstance(sample_item, dict):
                print("检测到列表词典格式:")
                print(f"  项目结构: {sample_item}")
                
                # 检查常见字段
                common_fields = ['word', 'Word', 'name', 'translations', 'translation', 'definition', 'phrases']
                found_fields = []
                for field in common_fields:
                    if field in sample_item:
                        found_fields.append(field)
                
                if found_fields:
                    print(f"  包含字段: {found_fields}")
                else:
                    print("  未识别到常见词典字段")
        
        return True
        
    except Exception as e:
        print(f"分析文件 {file_path} 时出错: {e}")
        return False

def main():
    """主函数"""
    current_dir = os.getcwd()
    json_files = []
    
    # 扫描当前目录下的所有JSON文件
    for file in os.listdir(current_dir):
        if file.endswith('.json'):
            json_files.append(os.path.join(current_dir, file))
    
    if not json_files:
        print("当前目录下未发现JSON文件")
        return
    
    print(f"发现 {len(json_files)} 个JSON文件:")
    for file in json_files:
        print(f"  - {os.path.basename(file)}")
    
    print("\n开始分析...")
    
    for json_file in json_files:
        analyze_json_format(json_file)

if __name__ == "__main__":
    main() 