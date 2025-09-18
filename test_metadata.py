#!/usr/bin/env python3
"""
测试元数据提取功能 - 使用文件浏览器选择图片
"""
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
from app.utils_metadata import extract_people_and_tags, _HAS_EXIFTOOL

def test_metadata_extraction():
    """测试元数据提取功能"""
    
    # 创建隐藏的根窗口
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    
    # 打开文件选择对话框
    file_types = [
        ("图片文件", "*.jpg *.jpeg *.png *.tiff *.tif *.gif *.bmp *.webp"),
        ("JPEG文件", "*.jpg *.jpeg"),
        ("PNG文件", "*.png"),
        ("TIFF文件", "*.tiff *.tif"),
        ("所有文件", "*.*")
    ]
    
    selected_file = filedialog.askopenfilename(
        title="选择要分析的图片文件",
        filetypes=file_types,
        initialdir=os.getcwd()
    )
    
    if not selected_file:
        print("没有选择文件，退出程序")
        root.destroy()
        return
    
    print("=" * 60)
    print("图片元数据分析结果")
    print("=" * 60)
    print(f"选择的文件: {selected_file}")
    print(f"文件大小: {os.path.getsize(selected_file) / 1024:.2f} KB")
    
    # 显示基本图片信息
    show_additional_metadata(selected_file)
    print()
    
    # 显示库可用性状态
    print("可用的元数据库:")
    print(f"  - ExifTool CLI: {'✅ 可用' if _HAS_EXIFTOOL else '❌ 不可用'}")
    
    if not _HAS_EXIFTOOL:
        print("\n💡 提示: 安装 ExifTool 可获得最全面的 metadata 支持")
        print("   下载地址: https://exiftool.org/")
    
    print()
    
    try:
        # 提取元数据
        print("正在提取元数据...")
        people, tags = extract_people_and_tags(selected_file)
        
        print("-" * 40)
        print("提取结果:")
        print("-" * 40)
        
        if people:
            print(f"检测到的人员 ({len(people)} 个):")
            for i, person in enumerate(people, 1):
                print(f"  {i}. {person}")
        else:
            print("未检测到人员信息")
        
        print()
        
        if tags:
            print(f"检测到的标签 ({len(tags)} 个):")
            for i, tag in enumerate(tags, 1):
                print(f"  {i}. {tag}")
        else:
            print("未检测到标签信息")
        
        print()
        print("✅ 元数据提取完成!")
        
        # # 显示结果对话框
        # result_message = f"文件: {os.path.basename(selected_file)}\n\n"
        # result_message += f"人员 ({len(people)} 个): {', '.join(people) if people else '无'}\n\n"
        # result_message += f"标签 ({len(tags)} 个): {', '.join(tags) if tags else '无'}"
        
        # messagebox.showinfo("元数据提取结果", result_message)
        
        # # 询问是否保存结果到文件
        # if people or tags:
        #     save_result = messagebox.askyesno("保存结果", "是否将分析结果保存到文本文件？")
        #     if save_result:
        #         save_results_to_file(selected_file, people, tags)
        
    except Exception as e:
        error_msg = f"提取元数据时发生错误: {e}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        messagebox.showerror("错误", error_msg)
    
    root.destroy()

def save_results_to_file(image_path, people, tags):
    """保存分析结果到文件"""
    try:
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        output_file = f"{base_name}_metadata_analysis.txt"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("图片元数据分析结果\n")
            f.write("=" * 40 + "\n")
            f.write(f"原始文件: {image_path}\n")
            f.write(f"分析时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"文件大小: {os.path.getsize(image_path) / 1024:.2f} KB\n\n")
            
            f.write(f"检测到的人员 ({len(people)} 个):\n")
            if people:
                for i, person in enumerate(people, 1):
                    f.write(f"  {i}. {person}\n")
            else:
                f.write("  无\n")
            
            f.write(f"\n检测到的标签 ({len(tags)} 个):\n")
            if tags:
                for i, tag in enumerate(tags, 1):
                    f.write(f"  {i}. {tag}\n")
            else:
                f.write("  无\n")
        
        print(f"✅ 结果已保存到: {output_file}")
        messagebox.showinfo("保存成功", f"分析结果已保存到:\n{output_file}")
        
    except Exception as e:
        error_msg = f"保存文件时发生错误: {e}"
        print(f"❌ {error_msg}")
        messagebox.showerror("保存失败", error_msg)

def show_additional_metadata(file_path):
    """显示额外的图片信息"""
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        
        with Image.open(file_path) as img:
            print(f"图片尺寸: {img.size[0]} x {img.size[1]} 像素")
            print(f"图片模式: {img.mode}")
            print(f"图片格式: {img.format}")
            
            # 显示EXIF信息（如果有）
            try:
                exif_data = img.getexif()
                if exif_data:
                    print("基本EXIF信息:")
                    # 显示一些常见的EXIF标签
                    interesting_tags = {
                        271: "制造商",
                        272: "型号", 
                        306: "拍摄时间",
                        36867: "拍摄时间(原始)",
                        33434: "曝光时间",
                        33437: "光圈值",
                        34855: "ISO感光度"
                    }
                    
                    for tag_id, tag_name in interesting_tags.items():
                        if tag_id in exif_data:
                            value = exif_data[tag_id]
                            print(f"  {tag_name}: {value}")
            except Exception:
                pass
            
            # 显示其他嵌入信息
            if hasattr(img, 'info') and img.info:
                interesting_keys = ['dpi', 'quality', 'comment', 'description']
                info_found = False
                for key in interesting_keys:
                    if key in img.info:
                        if not info_found:
                            print("其他信息:")
                            info_found = True
                        print(f"  {key}: {img.info[key]}")
                        
    except Exception as e:
        print(f"无法读取图片基本信息: {e}")

if __name__ == "__main__":
    test_metadata_extraction()