#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kindle 笔记导入 Notion 脚本
极致健壮版本 - 支持 TXT 和 HTML 多源弹性读取
"""

import os
import sys
import re
import time
from typing import List, Dict, Optional
from collections import defaultdict

# 修复 Windows 控制台 UTF-8 输出
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("缺少必要的依赖库，请先安装：")
    print("   pip install requests beautifulsoup4")
    sys.exit(1)

# ==================== 配置区 ====================
NOTION_TOKEN = "enter your Notion token"
DATABASE_ID = "Enter your Database id"

NOTION_VERSION = "2022-06-28"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": NOTION_VERSION
}

# API 限制
MAX_BLOCKS_PER_REQUEST = 100
API_DELAY = 0.3  # 秒
MAX_RETRIES = 3  # 最大重试次数
RETRY_DELAY = 2  # 重试延迟（秒）


# ==================== 数据结构 ====================
class Clipping:
    """笔记条目"""
    def __init__(self, book_title: str, author: str, location: str, content: str, chapter: str = ""):
        self.book_title = book_title.strip()
        self.author = author.strip()
        self.location = location.strip()
        self.content = content.strip()
        self.chapter = chapter.strip()  # 章节信息
        self.location_num = self._extract_location_number()
    
    def _extract_location_number(self) -> int:
        """从位置信息中提取位置编号，失败则返回 999999"""
        try:
            # 优先匹配"位置 XXX"或"#XXX"格式
            # HTML: "第 37 頁 位置 569" -> 提取 569
            # TXT: "位置 #395-396" -> 提取 395
            
            # 先尝试匹配"位置"后面的数字
            match = re.search(r'位置[^\d]*(\d+)', self.location)
            if match:
                return int(match.group(1))
            
            # 再尝试匹配 #数字 格式
            match = re.search(r'#(\d+)', self.location)
            if match:
                return int(match.group(1))
            
            # 最后尝试提取第一个数字（兜底）
            match = re.search(r'\d+', self.location)
            if match:
                return int(match.group())
            
            return 999999
        except Exception:
            return 999999
    
    def __repr__(self):
        return f"<Clipping: {self.book_title[:20]}... loc={self.location_num}>"


# ==================== 文件读取与解析 ====================
def normalize_book_title(title: str) -> str:
    """标准化书名，去除 BOM、多余空格、括号内容等"""
    # 去除 BOM
    title = title.replace('\ufeff', '').replace('﻿', '')
    # 去除括号及其内容（如作者、出版社等）
    title = re.sub(r'\s*\([^)]*\)\s*', '', title)
    # 去除多余空格
    title = ' '.join(title.split())
    return title.strip()


def check_files() -> tuple:
    """检查当前目录下的文件，返回 (txt_exists, html_files)"""
    txt_file = "My Clippings.txt"
    txt_exists = os.path.exists(txt_file)
    
    html_files = [f for f in os.listdir('.') if f.endswith('.html')]
    
    return txt_exists, html_files


def parse_txt_file(filename: str) -> List[Clipping]:
    """解析 TXT 格式的 Kindle 笔记"""
    clippings = []
    
    try:
        with open(filename, 'r', encoding='utf-8-sig') as f:
            content = f.read()
        
        # 以 ========== 分割
        entries = content.split('==========')
        
        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue
            
            lines = entry.split('\n')
            if len(lines) < 3:
                continue
            
            try:
                # 第一行：书名和作者
                title_line = lines[0].strip()
                # 提取书名（括号前）和作者（括号内）
                match = re.match(r'^(.+?)\s*\((.+?)\)\s*$', title_line)
                if match:
                    book_title = match.group(1).strip()
                    author = match.group(2).strip()
                else:
                    book_title = title_line
                    author = "未知作者"
                
                # 标准化书名
                book_title = normalize_book_title(book_title)
                
                # 第二行：位置信息
                location_line = lines[1].strip()
                
                # 第三行及之后：正文
                text_content = '\n'.join(lines[2:]).strip()
                
                if text_content:  # 只保留有正文的笔记
                    clipping = Clipping(book_title, author, location_line, text_content, "")
                    clippings.append(clipping)
            
            except Exception as e:
                print(f"[警告] 解析 TXT 条目时出错（已跳过）: {str(e)[:50]}")
                continue
        
        print(f"[成功] 从 {filename} 解析出 {len(clippings)} 条笔记")
        return clippings
    
    except Exception as e:
        print(f"[错误] 读取 TXT 文件失败: {e}")
        return []


def parse_html_file(filename: str) -> List[Clipping]:
    """解析 HTML 格式的笔记"""
    clippings = []
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 提取书名和作者
        book_title_tag = soup.find('div', class_='bookTitle')
        author_tag = soup.find('div', class_='authors')
        
        book_title = book_title_tag.get_text(strip=True) if book_title_tag else "未知书名"
        book_title = normalize_book_title(book_title)  # 标准化书名
        author = author_tag.get_text(strip=True) if author_tag else "未知作者"
        
        # 提取所有章节和笔记
        current_chapter = ""
        body_container = soup.find('div', class_='bodyContainer')
        
        if body_container:
            for element in body_container.find_all(['div']):
                # 检查是否是章节标题
                if 'sectionHeading' in element.get('class', []):
                    current_chapter = element.get_text(strip=True)
                
                # 检查是否是笔记标题
                elif 'noteHeading' in element.get('class', []):
                    location = element.get_text(strip=True)
                    # 提取小节信息（如"看清理性化的世界"）
                    section_match = re.search(r'-\s*([^>]+)\s*>', location)
                    section_title = section_match.group(1).strip() if section_match else ""
                    
                    # 查找对应的笔记正文
                    next_sibling = element.find_next_sibling('div', class_='noteText')
                    if next_sibling:
                        content = next_sibling.get_text(strip=True)
                        if content:
                            # 组合章节信息
                            chapter_info = current_chapter
                            if section_title:
                                chapter_info = f"{current_chapter} > {section_title}" if current_chapter else section_title
                            
                            clipping = Clipping(book_title, author, location, content, chapter_info)
                            clippings.append(clipping)
        
        print(f"[成功] 从 {filename} 解析出 {len(clippings)} 条笔记")
        return clippings
    
    except Exception as e:
        print(f"[错误] 读取 HTML 文件失败: {e}")
        return []


# ==================== 数据处理 ====================
def deduplicate_and_sort(clippings: List[Clipping]) -> Dict[str, List[Clipping]]:
    """
    全局去重和排序
    返回：{书名: [排序后的笔记列表]}
    """
    # 按标准化后的书名分组
    grouped = defaultdict(list)
    for clip in clippings:
        normalized_title = normalize_book_title(clip.book_title)
        grouped[normalized_title].append(clip)
    
    # 对每本书的笔记进行去重和排序
    result = {}
    for book_title, clips in grouped.items():
        # 去重：如果两条笔记正文存在包含关系，保留最长的
        unique_clips = []
        for clip in clips:
            is_duplicate = False
            for existing in unique_clips:
                # 检查包含关系
                if clip.content in existing.content:
                    is_duplicate = True
                    break
                elif existing.content in clip.content:
                    # 当前笔记更长，替换已有的
                    unique_clips.remove(existing)
                    break
            
            if not is_duplicate:
                unique_clips.append(clip)
        
        # 按位置排序
        unique_clips.sort(key=lambda x: x.location_num)
        result[book_title] = unique_clips
        
        print(f"[书籍] 《{book_title}》: {len(clips)} 条 -> 去重后 {len(unique_clips)} 条")
    
    return result


# ==================== Notion API 操作 ====================
def search_page_by_title(book_title: str) -> Optional[str]:
    """在数据库中搜索指定书名的页面，返回 page_id"""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    payload = {
        "filter": {
            "property": "Names",
            "title": {
                "equals": book_title
            }
        }
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(url, headers=HEADERS, json=payload, timeout=30)
            time.sleep(API_DELAY)
            
            if response.status_code == 200:
                results = response.json().get('results', [])
                if results:
                    page_id = results[0]['id']
                    print(f"   [找到] 已有页面: {page_id}")
                    return page_id
                return None
            elif response.status_code == 429:
                # 速率限制
                wait_time = RETRY_DELAY * (attempt + 1)
                print(f"   [限流] 等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                continue
            else:
                print(f"   [警告] 搜索失败: {response.status_code}")
                return None
        
        except (requests.exceptions.ConnectionError, ConnectionResetError) as e:
            if attempt < MAX_RETRIES - 1:
                print(f"   [重试] 网络连接失败，{RETRY_DELAY}秒后重试 ({attempt + 1}/{MAX_RETRIES})...")
                time.sleep(RETRY_DELAY)
            else:
                print(f"   [错误] 网络连接失败，已重试 {MAX_RETRIES} 次: {type(e).__name__}")
                return None
        
        except Exception as e:
            print(f"   [警告] 搜索页面时出错: {type(e).__name__}: {str(e)[:100]}")
            return None
    
    return None


def create_page(book_title: str, author: str) -> Optional[str]:
    """创建新页面，只填写书名和作者"""
    url = "https://api.notion.com/v1/pages"
    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "Names": {
                "title": [
                    {
                        "text": {"content": book_title}
                    }
                ]
            },
            "Author": {
                "rich_text": [
                    {
                        "text": {"content": author}
                    }
                ]
            }
        }
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(url, headers=HEADERS, json=payload, timeout=30)
            time.sleep(API_DELAY)
            
            if response.status_code == 200:
                page_id = response.json()['id']
                print(f"   [创建] 新页面成功: {page_id}")
                return page_id
            elif response.status_code == 429:
                wait_time = RETRY_DELAY * (attempt + 1)
                print(f"   [限流] 等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                continue
            else:
                print(f"   [错误] 创建页面失败: {response.status_code} - {response.text[:200]}")
                return None
        
        except (requests.exceptions.ConnectionError, ConnectionResetError) as e:
            if attempt < MAX_RETRIES - 1:
                print(f"   [重试] 网络连接失败，{RETRY_DELAY}秒后重试 ({attempt + 1}/{MAX_RETRIES})...")
                time.sleep(RETRY_DELAY)
            else:
                print(f"   [错误] 网络连接失败，已重试 {MAX_RETRIES} 次: {type(e).__name__}")
                return None
        
        except Exception as e:
            print(f"   [错误] 创建页面时出错: {type(e).__name__}: {str(e)[:100]}")
            return None
    
    return None


def get_existing_quote_count(page_id: str) -> int:
    """获取页面中已有的 quote block 数量"""
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            time.sleep(API_DELAY)
            
            if response.status_code == 200:
                blocks = response.json().get('results', [])
                quote_count = sum(1 for block in blocks if block.get('type') == 'quote')
                print(f"   [信息] 页面已有 {quote_count} 个 quote block")
                return quote_count
            elif response.status_code == 429:
                wait_time = RETRY_DELAY * (attempt + 1)
                print(f"   [限流] 等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                continue
            else:
                return 0
        
        except (requests.exceptions.ConnectionError, ConnectionResetError) as e:
            if attempt < MAX_RETRIES - 1:
                print(f"   [重试] 网络连接失败，{RETRY_DELAY}秒后重试 ({attempt + 1}/{MAX_RETRIES})...")
                time.sleep(RETRY_DELAY)
            else:
                print(f"   [警告] 获取已有笔记数量失败: {type(e).__name__}")
                return 0
        
        except Exception as e:
            print(f"   [警告] 获取已有笔记数量时出错: {type(e).__name__}")
            return 0
    
    return 0


def create_quote_block(index: int, content: str, location: str, chapter: str = "") -> dict:
    """创建一个 quote block"""
    rich_text = []
    
    # 序号和正文
    rich_text.append({
        "type": "text",
        "text": {"content": f"{index}. {content}"}
    })
    
    # 章节信息（如果有）
    if chapter:
        rich_text.append({
            "type": "text",
            "text": {"content": f"\n📖 {chapter}"},
            "annotations": {
                "color": "blue",
                "italic": True
            }
        })
    
    # 位置信息
    rich_text.append({
        "type": "text",
        "text": {"content": f"\n[{location}]"},
        "annotations": {
            "color": "gray",
            "italic": True
        }
    })
    
    return {
        "object": "block",
        "type": "quote",
        "quote": {
            "rich_text": rich_text
        }
    }


def append_blocks_to_page(page_id: str, blocks: List[dict]) -> bool:
    """追加 blocks 到页面（分批处理）"""
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    
    # 分批追加
    for i in range(0, len(blocks), MAX_BLOCKS_PER_REQUEST):
        batch = blocks[i:i + MAX_BLOCKS_PER_REQUEST]
        payload = {"children": batch}
        
        for attempt in range(MAX_RETRIES):
            try:
                response = requests.patch(url, headers=HEADERS, json=payload, timeout=60)
                time.sleep(API_DELAY)
                
                if response.status_code == 200:
                    print(f"   [成功] 追加 {len(batch)} 条笔记")
                    break
                elif response.status_code == 429:
                    wait_time = RETRY_DELAY * (attempt + 1)
                    print(f"   [限流] 等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"   [错误] 追加 blocks 失败: {response.status_code} - {response.text[:200]}")
                    return False
            
            except (requests.exceptions.ConnectionError, ConnectionResetError) as e:
                if attempt < MAX_RETRIES - 1:
                    print(f"   [重试] 网络连接失败，{RETRY_DELAY}秒后重试 ({attempt + 1}/{MAX_RETRIES})...")
                    time.sleep(RETRY_DELAY)
                else:
                    print(f"   [错误] 追加 blocks 失败，已重试 {MAX_RETRIES} 次: {type(e).__name__}")
                    return False
            
            except Exception as e:
                print(f"   [错误] 追加 blocks 时出错: {type(e).__name__}: {str(e)[:100]}")
                return False
        else:
            # 如果所有重试都失败
            return False
    
    return True


# ==================== 主流程 ====================
def main():
    print("=" * 60)
    print("Kindle 笔记导入 Notion - 极致健壮版")
    print("=" * 60)
    
    # 1. 检查配置
    if NOTION_TOKEN == "your_notion_integration_token_here" or DATABASE_ID == "your_database_id_here":
        print("[错误] 请先在脚本中配置 NOTION_TOKEN 和 DATABASE_ID")
        sys.exit(1)
    
    # 2. 检查文件
    print("\n[步骤1] 检查当前目录...")
    txt_exists, html_files = check_files()
    
    if not txt_exists and not html_files:
        print("[提示] 当前目录下没有找到 My Clippings.txt 或 .html 文件")
        print("       请将笔记文件放在脚本同目录下，然后重新运行")
        sys.exit(0)
    
    # 3. 读取和解析文件
    print("\n[步骤2] 读取笔记文件...")
    all_clippings = []
    
    if txt_exists:
        print("   -> 处理 My Clippings.txt")
        all_clippings.extend(parse_txt_file("My Clippings.txt"))
    
    for html_file in html_files:
        print(f"   -> 处理 {html_file}")
        all_clippings.extend(parse_html_file(html_file))
    
    if not all_clippings:
        print("\n[提示] 没有解析到任何有效笔记")
        sys.exit(0)
    
    print(f"\n[统计] 总共读取到 {len(all_clippings)} 条原始笔记")
    
    # 4. 去重和排序
    print("\n[步骤3] 进行去重和排序...")
    grouped_clippings = deduplicate_and_sort(all_clippings)
    
    # 5. 写入 Notion
    print("\n[步骤4] 开始写入 Notion...")
    total_books = len(grouped_clippings)
    success_count = 0
    
    for idx, (book_title, clippings) in enumerate(grouped_clippings.items(), 1):
        print(f"\n[{idx}/{total_books}] 处理《{book_title}》({len(clippings)} 条笔记)")
        
        try:
            # 搜索或创建页面
            page_id = search_page_by_title(book_title)
            start_index = 1
            
            if page_id:
                # 已有页面，获取现有笔记数量
                existing_count = get_existing_quote_count(page_id)
                start_index = existing_count + 1
            else:
                # 创建新页面
                author = clippings[0].author if clippings else "未知作者"
                page_id = create_page(book_title, author)
                if not page_id:
                    print(f"   [跳过] 无法创建页面")
                    continue
            
            # 创建 quote blocks
            blocks = []
            for i, clip in enumerate(clippings, start=start_index):
                block = create_quote_block(i, clip.content, clip.location, clip.chapter)
                blocks.append(block)
            
            # 追加到页面
            if append_blocks_to_page(page_id, blocks):
                success_count += 1
                print(f"   [完成] 《{book_title}》处理完成")
            else:
                print(f"   [失败] 《{book_title}》写入失败")
        
        except Exception as e:
            print(f"   [错误] 处理《{book_title}》时出错: {e}")
            continue
    
    # 6. 完成
    print("\n" + "=" * 60)
    print(f"导入完成！成功处理 {success_count}/{total_books} 本书")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[中断] 用户中断操作")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n[异常] 程序异常退出: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)