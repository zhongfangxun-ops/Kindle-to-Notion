#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试脚本 - 验证文件解析功能（不连接 Notion）
"""

import sys
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# 导入主脚本的函数
from kindle_to_notion import check_files, parse_txt_file, parse_html_file, deduplicate_and_sort

def test_parsing():
    print("=" * 60)
    print("测试模式 - 验证文件解析功能")
    print("=" * 60)
    
    # 检查文件
    print("\n[1] 检查文件...")
    txt_exists, html_files = check_files()
    
    if not txt_exists and not html_files:
        print("[提示] 当前目录下没有找到笔记文件")
        return
    
    print(f"   TXT 文件: {'存在' if txt_exists else '不存在'}")
    print(f"   HTML 文件: {len(html_files)} 个")
    
    # 解析文件
    print("\n[2] 解析文件...")
    all_clippings = []
    
    if txt_exists:
        print("   -> 解析 My Clippings.txt")
        txt_clips = parse_txt_file("My Clippings.txt")
        all_clippings.extend(txt_clips)
        
        if txt_clips:
            print(f"\n   示例笔记（TXT）:")
            clip = txt_clips[0]
            print(f"   书名: {clip.book_title}")
            print(f"   作者: {clip.author}")
            print(f"   位置: {clip.location}")
            print(f"   位置编号: {clip.location_num}")
            print(f"   正文: {clip.content[:50]}...")
    
    for html_file in html_files:
        print(f"\n   -> 解析 {html_file}")
        html_clips = parse_html_file(html_file)
        all_clippings.extend(html_clips)
        
        if html_clips:
            print(f"\n   示例笔记（HTML）:")
            clip = html_clips[0]
            print(f"   书名: {clip.book_title}")
            print(f"   作者: {clip.author}")
            print(f"   位置: {clip.location}")
            print(f"   位置编号: {clip.location_num}")
            print(f"   正文: {clip.content[:50]}...")
    
    if not all_clippings:
        print("\n[提示] 没有解析到任何笔记")
        return
    
    print(f"\n[3] 总计: {len(all_clippings)} 条原始笔记")
    
    # 去重和排序
    print("\n[4] 去重和排序...")
    grouped = deduplicate_and_sort(all_clippings)
    
    print(f"\n[5] 最终结果:")
    print(f"   共 {len(grouped)} 本书")
    total_notes = sum(len(clips) for clips in grouped.values())
    print(f"   共 {total_notes} 条去重后的笔记")
    
    print("\n[6] 详细信息:")
    for book_title, clips in grouped.items():
        print(f"\n   《{book_title}》")
        print(f"   - 作者: {clips[0].author if clips else '未知'}")
        print(f"   - 笔记数: {len(clips)}")
        print(f"   - 位置范围: {clips[0].location_num} ~ {clips[-1].location_num}")
        
        # 显示前3条笔记
        print(f"   - 前3条笔记:")
        for i, clip in enumerate(clips[:3], 1):
            print(f"      {i}. [{clip.location_num}] {clip.content[:40]}...")
    
    print("\n" + "=" * 60)
    print("测试完成！解析功能正常")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_parsing()
    except Exception as e:
        print(f"\n[错误] {e}")
        import traceback
        traceback.print_exc()
