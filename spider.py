import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timedelta
import time
import random
import argparse
import sys
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

def create_directory(date):
    """创建日期目录"""
    dir_path = os.path.join('data', date)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
    return dir_path

def get_match_data(date):
    """获取指定日期的比赛数据"""
    url = f'https://trade.500.com/jczq/index.php?playid=312&g=2&date={date}'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    try:
        print(f"正在获取 {date} 的比赛数据...")
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'gb2312'
        
        if response.status_code != 200:
            print(f"请求失败，状态码: {response.status_code}")
            return []
            
        soup = BeautifulSoup(response.text, 'lxml')
        
        # 保存HTML以供调试
        with open('debug.html', 'w', encoding='utf-8') as f:
            f.write(response.text)
        print("已保存HTML到debug.html文件")
        
        matches = []
        # 查找所有比赛行
        match_rows = soup.select('tr.bet-tb-tr')
        print(f"找到 {len(match_rows)} 场比赛")
        
        for row in match_rows:
            match_info = {}
            
            # 获取比赛编号
            match_id = row.select_one('td.td-no a')
            if match_id:
                match_info['match_id'] = match_id.text.strip()
            
            # 获取比赛ID
            fixture_id = row.get('data-fixtureid')
            if fixture_id:
                match_info['fixture_id'] = fixture_id
            
            # 获取联赛名称
            league = row.select_one('td.td-evt a')
            if league:
                match_info['league'] = league.text.strip()
            
            # 获取比赛时间
            match_time = row.select_one('td.td-endtime')
            if match_time:
                match_info['match_time'] = match_time.text.strip()
            
            # 获取主客队信息
            home_team = row.select_one('td.td-team .team-l a')
            away_team = row.select_one('td.td-team .team-r a')
            
            if home_team:
                match_info['home_team'] = home_team.text.strip()
            if away_team:
                match_info['away_team'] = away_team.text.strip()
            
            # 获取比赛结果
            result_elem = row.select_one('td.td-team .team-vs .score')
            if result_elem:
                match_info['result'] = result_elem.text.strip()
            
            if match_info:
                matches.append(match_info)
                print(f"已解析比赛: {match_info.get('match_id', '')} - {match_info.get('home_team', '')} vs {match_info.get('away_team', '')}")
        
        return matches
    
    except requests.exceptions.RequestException as e:
        print(f"网络请求错误: {str(e)}")
        return []
    except Exception as e:
        print(f"获取数据时出错: {str(e)}")
        return []

def save_to_json(data, date):
    """保存数据到JSON文件"""
    if not data:
        print("没有数据需要保存")
        return
        
    dir_path = create_directory(date)
    file_path = os.path.join(dir_path, f'{date}_main.json')
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"数据已保存到: {file_path}")
    except Exception as e:
        print(f"保存数据时出错: {str(e)}")

def parse_odds_data(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    odds_data = {}

    # 初始化存储公司数据的列表
    companies = []
    
    # 查找所有赔率行
    rows = soup.select('tr[id][ttl="zy"]')
    if not rows:
        print("未找到赔率行数据")
    
    for row in rows:
        company_name_elem = row.select_one('td.tb_plgs p a span.quancheng')
        if company_name_elem:
            company_name = company_name_elem.text.strip()
        else:
            company_name = "未知公司"
        
        # 初始化该公司的数据结构
        company_data = {
            'initial_odds': [],
            'current_odds': [],
            'initial_probabilities': [],
            'current_probabilities': [],
            'initial_return_rate': 0,
            'current_return_rate': 0,
            'initial_kelly': [],
            'current_kelly': []
        }
        
        try:
            # 解析欧赔数据
            odds_tables = row.select('td table.pl_table_data')
            if len(odds_tables) > 0:
                odds_table = odds_tables[0]
                # 尝试找到所有行
                all_rows = odds_table.select('tr')
                
                # 初盘赔率（第一行）
                if len(all_rows) > 0:
                    initial_odds_cells = all_rows[0].select('td')
                    for cell in initial_odds_cells:
                        if cell.text.strip() and cell.text.strip().replace('.', '', 1).isdigit():
                            company_data['initial_odds'].append(round(float(cell.text.strip()), 4))
                
                # 即时赔率（第二行）
                if len(all_rows) > 1:
                    current_odds_cells = all_rows[1].select('td')
                    for cell in current_odds_cells:
                        if cell.text.strip() and cell.text.strip().replace('.', '', 1).isdigit():
                            company_data['current_odds'].append(round(float(cell.text.strip()), 4))
            
            # 解析概率数据
            if len(odds_tables) > 1:
                prob_table = odds_tables[1]
                all_rows = prob_table.select('tr')
                
                # 初盘概率（第一行）
                if len(all_rows) > 0:
                    initial_prob_cells = all_rows[0].select('td')
                    for cell in initial_prob_cells:
                        text = cell.text.strip()
                        if text and text.replace('.', '', 1).replace('%', '').isdigit():
                            company_data['initial_probabilities'].append(round(float(text.strip('%')) / 100, 4))
                
                # 即时概率（第二行）
                if len(all_rows) > 1:
                    current_prob_cells = all_rows[1].select('td')
                    for cell in current_prob_cells:
                        text = cell.text.strip()
                        if text and text.replace('.', '', 1).replace('%', '').isdigit():
                            company_data['current_probabilities'].append(round(float(text.strip('%')) / 100, 4))
            
            # 解析返还率数据
            if len(odds_tables) > 2:
                return_rate_table = odds_tables[2]
                all_rows = return_rate_table.select('tr')
                
                # 初盘返还率（第一行）
                if len(all_rows) > 0:
                    initial_return_rate_cell = all_rows[0].select_one('td')
                    if initial_return_rate_cell:
                        text = initial_return_rate_cell.text.strip()
                        if text and text.replace('.', '', 1).replace('%', '').isdigit():
                            company_data['initial_return_rate'] = round(float(text.strip('%')) / 100, 4)
                
                # 即时返还率（第二行）
                if len(all_rows) > 1:
                    current_return_rate_cell = all_rows[1].select_one('td')
                    if current_return_rate_cell:
                        text = current_return_rate_cell.text.strip()
                        if text and text.replace('.', '', 1).replace('%', '').isdigit():
                            company_data['current_return_rate'] = round(float(text.strip('%')) / 100, 4)
                        else:
                            # 如果无法解析即时返还率，则使用初始返还率
                            company_data['current_return_rate'] = company_data['initial_return_rate']
            
            # 解析凯利指数数据
            if len(odds_tables) > 3:
                kelly_table = odds_tables[3]
                all_rows = kelly_table.select('tr')
                
                # 初盘凯利指数（第一行）
                if len(all_rows) > 0:
                    initial_kelly_cells = all_rows[0].select('td')
                    for cell in initial_kelly_cells:
                        if cell.text.strip() and cell.text.strip().replace('.', '', 1).isdigit():
                            company_data['initial_kelly'].append(round(float(cell.text.strip()), 4))
                
                # 即时凯利指数（第二行）
                if len(all_rows) > 1:
                    current_kelly_cells = all_rows[1].select('td')
                    for cell in current_kelly_cells:
                        if cell.text.strip() and cell.text.strip().replace('.', '', 1).isdigit():
                            company_data['current_kelly'].append(round(float(cell.text.strip()), 4))
                
        except Exception as e:
            print(f"解析公司 {company_name} 数据时出错: {str(e)}")
        
        # 添加该公司的数据
        odds_data[company_name] = company_data
        companies.append(company_name)
    
    # 如果没有解析到任何公司数据，使用默认值
    if not odds_data:
        odds_data["未知公司"] = {
            'initial_odds': [],
            'current_odds': [],
            'initial_probabilities': [],
            'current_probabilities': [],
            'initial_return_rate': 0,
            'current_return_rate': 0,
            'initial_kelly': [],
            'current_kelly': []
        }
    
    return odds_data

def parse_size_data(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    size_data = {}

    # 查找表格行，尝试不同的选择器
    rows = soup.select('tr[class*="tr"][id]')  # 查找带id属性的tr行
    if not rows:
        print("未找到tr[class*='tr'][id]格式的行，尝试其他选择器")
        rows = soup.select('tr.tableline')
        if not rows:
            print("未找到大小球数据，尝试其他选择器")
            # 尝试其他可能的选择器
            rows = soup.select('tr[class*="line"]')
        
        if not rows:
            print("仍未找到大小球数据，尝试查找所有行")
            # 更彻底的方法：查找表格中的所有行
            rows = soup.select('table.pub_table tr:not(:first-child)')
        
        if not rows:
            # 最后尝试：直接查找表格的所有行
            rows = soup.select('table tr')
            print(f"尝试最基本的选择器，找到 {len(rows)} 行")
    else:
        print(f"找到 {len(rows)} 行带ID的tr行")
    
    if not rows:
        print("未找到任何可能的大小球数据行")
        return size_data
    
    print(f"找到 {len(rows)} 行大小球数据")
    
    for row in rows:
        # 获取公司名称
        company_name_elem = row.select_one('td.tb_plgs')
        
        # 尝试不同的方式获取公司名称
        if company_name_elem:
            # 尝试方式1：通过 span.quancheng
            quancheng = company_name_elem.select_one('span.quancheng')
            if quancheng:
                company_name = quancheng.text.strip()
            else:
                # 尝试方式2：直接获取 td.tb_plgs 的文本
                company_name = company_name_elem.text.strip()
                # 清理文本中可能的多余内容
                company_name = company_name.split('\n')[0].strip()
        else:
            # 尝试使用第一个单元格作为公司名称
            first_td = row.select_one('td')
            if first_td and first_td.text.strip() and len(first_td.text.strip()) < 30:  # 限制长度以避免选中非公司名称的内容
                company_name = first_td.text.strip()
                # 检查是否是可能的公司名称（例如不包含特殊字符或数字）
                if any(keyword in company_name for keyword in ['bet', 'Bet', '威廉', '澳门', '皇冠', '易胜博']):
                    print(f"通过内容匹配找到可能的公司名称: {company_name}")
                else:
                    # 如果找不到公司名称，跳过该行
                    print(f"跳过非公司名称的行: {company_name[:20]}...")
                    continue
            else:
                # 如果找不到公司名称，跳过该行
                print("未找到公司名称，跳过该行")
                continue
            
        print(f"解析公司: {company_name}")
        
        # 初始化该公司的数据结构
        company_data = {
            'current_size': {
                'over': '',
                'size': '',
                'under': '',
                'update_time': ''
            },
            'initial_size': {
                'over': '',
                'size': '',
                'under': '',
                'update_time': ''
            }
        }
        
        try:
            # 所有表格数据
            tables = row.select('table.pl_table_data')
            
            # 判断是否找到了表格
            if len(tables) >= 1:
                # 解析即时大小球数据（通常是第一个表格）
                current_table = tables[0]
                current_cells = current_table.select_one('tr').select('td')
                
                if len(current_cells) >= 3:
                    # 去掉箭头符号
                    over_text = current_cells[0].text.strip()
                    over_value = over_text.replace('↑', '').replace('↓', '')
                    
                    size_text = current_cells[1].text.strip()
                    
                    under_text = current_cells[2].text.strip()
                    under_value = under_text.replace('↑', '').replace('↓', '')
                    
                    company_data['current_size']['over'] = over_value
                    company_data['current_size']['size'] = size_text
                    company_data['current_size']['under'] = under_value
                    print(f"即时大小球数据: {company_data['current_size']}")
                
                # 获取时间数据（更新时间通常位于表格后的单元格）
                time_td = row.select_one('td time')
                if time_td:
                    company_data['current_size']['update_time'] = time_td.text.strip()
                    print(f"即时更新时间: {company_data['current_size']['update_time']}")
                
                # 解析初始大小球数据（通常是第二个表格）
                if len(tables) >= 2:
                    initial_table = tables[1]
                    initial_cells = initial_table.select_one('tr').select('td')
                    
                    if len(initial_cells) >= 3:
                        # 去掉箭头符号
                        over_text = initial_cells[0].text.strip()
                        over_value = over_text.replace('↑', '').replace('↓', '')
                        
                        size_text = initial_cells[1].text.strip()
                        
                        under_text = initial_cells[2].text.strip()
                        under_value = under_text.replace('↑', '').replace('↓', '')
                        
                        company_data['initial_size']['over'] = over_value
                        company_data['initial_size']['size'] = size_text
                        company_data['initial_size']['under'] = under_value
                        print(f"初始大小球数据: {company_data['initial_size']}")
                    
                    # 获取初始更新时间
                    initial_time_tds = row.select('td time')
                    if len(initial_time_tds) > 1:
                        company_data['initial_size']['update_time'] = initial_time_tds[1].text.strip()
                        print(f"初始更新时间: {company_data['initial_size']['update_time']}")
            else:
                print(f"未找到公司 {company_name} 的表格数据")
        
        except Exception as e:
            print(f"解析公司 {company_name} 数据时出错: {str(e)}")
            continue
        
        # 只有当成功解析到数据时，才添加该公司的数据
        if (company_data['current_size']['over'] or company_data['initial_size']['over']):
            size_data[company_name] = company_data
        else:
            print(f"未能解析到公司 {company_name} 的有效数据，跳过")
    
    if not size_data:
        print("未能从HTML中解析到任何大小球数据")
    
    return size_data

def parse_handicap_data(html_content):
    """解析让球数据"""
    soup = BeautifulSoup(html_content, 'lxml')
    data = {}

    # 获取所有赔率行
    rows = soup.select('tr[id][ttl="zy"]')
    if not rows:
        print("未找到让球赔率行数据")
        # 无数据时返回默认结构
        data["未知公司"] = {
            'handicap_list': [
                {
                    'handicap': "",
                    'initial_odds': [],
                    'current_odds': [],
                    'initial_probabilities': [],
                    'current_probabilities': [],
                    'initial_return_rate': 0,
                    'current_return_rate': 0,
                    'initial_kelly': [],
                    'current_kelly': []
                }
            ]
        }
        return data
    
    for row in rows:
        # 获取公司名称
        company_name_elem = row.select_one('td.tb_plgs span.quancheng')
        company_name = "未知公司"
        if company_name_elem:
            company_name = company_name_elem.text.strip()
            print(f"找到公司名称: {company_name}")
        
        # 获取让球值
        handicap_value = ""
        handicap_td = row.select_one('td[row="1"]:nth-of-type(3)')
        if handicap_td:
            handicap_value = handicap_td.text.strip()
            print(f"找到让球值: {handicap_value}")
        
        # 初始化该公司的数据结构（如果不存在）
        if company_name not in data:
            data[company_name] = {'handicap_list': []}
        
        # 创建当前让球值的数据
        handicap_data = {
            'handicap': handicap_value,
            'initial_odds': [],
            'current_odds': [],
            'initial_probabilities': [],
            'current_probabilities': [],
            'initial_return_rate': 0,
            'current_return_rate': 0,
            'initial_kelly': [],
            'current_kelly': []
        }
        
        try:
            # 解析让球赔率数据
            odds_tables = row.select('td table.pl_table_data')
            if len(odds_tables) > 0:
                odds_table = odds_tables[0]
                # 尝试找到所有行
                all_rows = odds_table.select('tr')
                
                # 初盘赔率（第一行）
                if len(all_rows) > 0:
                    initial_odds_cells = all_rows[0].select('td')
                    for cell in initial_odds_cells:
                        if cell.text.strip() and cell.text.strip().replace('.', '', 1).isdigit():
                            handicap_data['initial_odds'].append(round(float(cell.text.strip()), 2))
                
                # 即时赔率（第二行）
                if len(all_rows) > 1:
                    current_odds_cells = all_rows[1].select('td')
                    for cell in current_odds_cells:
                        if cell.text.strip() and cell.text.strip().replace('.', '', 1).isdigit():
                            handicap_data['current_odds'].append(round(float(cell.text.strip()), 2))
            
            # 解析概率数据
            if len(odds_tables) > 1:
                prob_table = odds_tables[1]
                all_rows = prob_table.select('tr')
                
                # 初盘概率（第一行）
                if len(all_rows) > 0:
                    initial_prob_cells = all_rows[0].select('td')
                    for cell in initial_prob_cells:
                        text = cell.text.strip()
                        if text and text.replace('.', '', 1).replace('%', '').isdigit():
                            value = text.rstrip('%') if '%' in text else text
                            handicap_data['initial_probabilities'].append(round(float(value) / 100, 4))
                
                # 即时概率（第二行）
                if len(all_rows) > 1:
                    current_prob_cells = all_rows[1].select('td')
                    for cell in current_prob_cells:
                        text = cell.text.strip()
                        if text and text.replace('.', '', 1).replace('%', '').isdigit():
                            value = text.rstrip('%') if '%' in text else text
                            handicap_data['current_probabilities'].append(round(float(value) / 100, 4))
            
            # 解析返还率数据
            if len(odds_tables) > 2:
                return_rate_table = odds_tables[2]
                all_rows = return_rate_table.select('tr')
                
                # 初盘返还率（第一行）
                if len(all_rows) > 0:
                    initial_return_rate_cell = all_rows[0].select_one('td')
                    if initial_return_rate_cell:
                        text = initial_return_rate_cell.text.strip()
                        if text and text.replace('.', '', 1).replace('%', '').isdigit():
                            value = text.rstrip('%') if '%' in text else text
                            handicap_data['initial_return_rate'] = round(float(value) / 100, 4)
                
                # 即时返还率（第二行）
                if len(all_rows) > 1:
                    current_return_rate_cell = all_rows[1].select_one('td')
                    if current_return_rate_cell:
                        text = current_return_rate_cell.text.strip()
                        if text and text.replace('.', '', 1).replace('%', '').isdigit():
                            value = text.rstrip('%') if '%' in text else text
                            handicap_data['current_return_rate'] = round(float(value) / 100, 4)
            
            # 解析凯利指数数据
            if len(odds_tables) > 3:
                kelly_table = odds_tables[3]
                all_rows = kelly_table.select('tr')
                
                # 初盘凯利指数（第一行）
                if len(all_rows) > 0:
                    initial_kelly_cells = all_rows[0].select('td')
                    for cell in initial_kelly_cells:
                        if cell.text.strip() and cell.text.strip().replace('.', '', 1).isdigit():
                            handicap_data['initial_kelly'].append(round(float(cell.text.strip()), 2))
                
                # 即时凯利指数（第二行）
                if len(all_rows) > 1:
                    current_kelly_cells = all_rows[1].select('td')
                    for cell in current_kelly_cells:
                        if cell.text.strip() and cell.text.strip().replace('.', '', 1).isdigit():
                            handicap_data['current_kelly'].append(round(float(cell.text.strip()), 2))
                
        except Exception as e:
            print(f"解析公司 {company_name} 让球数据时出错: {str(e)}")
        
        # 添加该让球值的数据到公司数据中
        # 检查是否已存在相同让球值的数据
        found = False
        for existing_handicap in data[company_name]['handicap_list']:
            if existing_handicap['handicap'] == handicap_value:
                found = True
                # 更新已存在的让球值数据（如果需要的话）
                break
        
        if not found:
            data[company_name]['handicap_list'].append(handicap_data)
    
    return data

def parse_asian_handicap_data(html_content):
    """解析亚盘数据"""
    soup = BeautifulSoup(html_content, 'html.parser')
    asian_data = {}

    # 尝试多种选择器来匹配亚盘公司行
    rows = soup.select('tr[id][ttl="zy"]')
    if not rows:
        print("未找到tr[id][ttl='zy']格式的行，尝试其他选择器")
        rows = soup.select('tr.tableline')
        if not rows:
            print("未找到tr.tableline格式的行，尝试其他选择器")
            rows = soup.select('tr[class*="tr"][id]')
            if not rows:
                print("未找到tr[class*='tr'][id]格式的行，尝试其他选择器")
                rows = soup.select('tr[id]')
                if not rows:
                    print("未找到任何带id的tr行，尝试查找所有可能的行")
                    rows = soup.select('table.pub_table tr:not(:first-child)')
    
    # 如果仍未找到，记录情况但不再生成调试文件
    if not rows:
        print("未找到任何可能的亚盘数据行")
        return asian_data
    
    print(f"找到 {len(rows)} 行亚盘数据")
    
    for row in rows:
        # 获取公司名称，尝试多种方式
        company_name = "未知公司"
        company_name_elem = row.select_one('td.tb_plgs span.quancheng')
        if company_name_elem:
            company_name = company_name_elem.text.strip()
        else:
            # 尝试其他方式获取公司名称
            company_td = row.select_one('td.tb_plgs')
            if company_td:
                company_name = company_td.text.strip().split('\n')[0].strip()
            else:
                # 尝试从第一个单元格获取公司名称
                first_td = row.select_one('td')
                if first_td and first_td.text.strip() and len(first_td.text.strip()) < 30:
                    company_name = first_td.text.strip()
                    # 检查是否是可能的公司名称
                    if not any(keyword in company_name for keyword in ['bet', 'Bet', '威廉', '澳门', '皇冠', '易胜博']):
                        print(f"跳过非公司名称的行: {company_name[:20]}...")
                        continue
        
        print(f"解析公司: {company_name}")
        
        # 初始化该公司的数据结构
        company_data = {
            'current_asian': {
                'home_odds': '',
                'handicap': '',
                'away_odds': '',
                'update_time': '',
                'status': ''  # 升降状态
            },
            'initial_asian': {
                'home_odds': '',
                'handicap': '',
                'away_odds': '',
                'update_time': ''
            }
        }
        
        try:
            # 所有表格数据
            tables = row.select('table.pl_table_data')
            if not tables:
                tables = row.select('table')
            
            # 判断是否找到了表格
            if len(tables) >= 1:
                # 解析即时亚盘数据（通常是第一个表格）
                current_table = tables[0]
                current_rows = current_table.select('tr')
                
                if len(current_rows) > 0:
                    current_cells = current_rows[0].select('td')
                    
                    if len(current_cells) >= 3:
                        # 解析主队赔率
                        home_odds_text = current_cells[0].text.strip()
                        company_data['current_asian']['home_odds'] = home_odds_text.replace('↑', '').replace('↓', '')
                        
                        # 解析盘口值和状态
                        handicap_text = current_cells[1].text.strip()
                        # 检查是否有升降状态
                        if '升' in handicap_text:
                            company_data['current_asian']['handicap'] = handicap_text.replace('升', '')
                            company_data['current_asian']['status'] = '升'
                        elif '降' in handicap_text:
                            company_data['current_asian']['handicap'] = handicap_text.replace('降', '')
                            company_data['current_asian']['status'] = '降'
                        else:
                            company_data['current_asian']['handicap'] = handicap_text
                            company_data['current_asian']['status'] = ''
                        
                        # 解析客队赔率
                        away_odds_text = current_cells[2].text.strip()
                        company_data['current_asian']['away_odds'] = away_odds_text.replace('↑', '').replace('↓', '')
                        
                        print(f"解析到即时亚盘数据: {company_data['current_asian']}")
                
                # 获取时间数据（更新时间通常位于表格后的单元格）
                time_td = row.select_one('td time')
                if time_td:
                    company_data['current_asian']['update_time'] = time_td.text.strip()
                    print(f"解析到更新时间: {company_data['current_asian']['update_time']}")
                
                # 解析初始亚盘数据（通常是第二个表格）
                if len(tables) >= 2:
                    initial_table = tables[1]
                    initial_rows = initial_table.select('tr')
                    
                    if len(initial_rows) > 0:
                        initial_cells = initial_rows[0].select('td')
                        
                        if len(initial_cells) >= 3:
                            # 解析主队赔率
                            home_odds_text = initial_cells[0].text.strip()
                            company_data['initial_asian']['home_odds'] = home_odds_text.replace('↑', '').replace('↓', '')
                            
                            # 解析盘口值
                            handicap_text = initial_cells[1].text.strip()
                            company_data['initial_asian']['handicap'] = handicap_text
                            
                            # 解析客队赔率
                            away_odds_text = initial_cells[2].text.strip()
                            company_data['initial_asian']['away_odds'] = away_odds_text.replace('↑', '').replace('↓', '')
                            
                            print(f"解析到初始亚盘数据: {company_data['initial_asian']}")
                    
                    # 获取初始更新时间
                    initial_time_tds = row.select('td time')
                    if len(initial_time_tds) > 1:
                        company_data['initial_asian']['update_time'] = initial_time_tds[1].text.strip()
                        print(f"解析到初始更新时间: {company_data['initial_asian']['update_time']}")
            else:
                print(f"未找到公司 {company_name} 的表格数据")
                
                # 尝试查找整个row中的数据
                all_cells = row.select('td')
                if len(all_cells) >= 7:  # 假设格式为: 公司名|主队赔率|盘口|客队赔率|时间|...
                    try:
                        # 解析主队赔率(可能是第2个单元格)
                        home_odds_text = all_cells[1].text.strip()
                        company_data['current_asian']['home_odds'] = home_odds_text.replace('↑', '').replace('↓', '')
                        
                        # 解析盘口值(可能是第3个单元格)
                        handicap_text = all_cells[2].text.strip()
                        if '升' in handicap_text:
                            company_data['current_asian']['handicap'] = handicap_text.replace('升', '')
                            company_data['current_asian']['status'] = '升'
                        elif '降' in handicap_text:
                            company_data['current_asian']['handicap'] = handicap_text.replace('降', '')
                            company_data['current_asian']['status'] = '降'
                        else:
                            company_data['current_asian']['handicap'] = handicap_text
                        
                        # 解析客队赔率(可能是第4个单元格)
                        away_odds_text = all_cells[3].text.strip()
                        company_data['current_asian']['away_odds'] = away_odds_text.replace('↑', '').replace('↓', '')
                        
                        # 解析时间(可能是第5个单元格)
                        if len(all_cells) > 4:
                            time_text = all_cells[4].text.strip()
                            company_data['current_asian']['update_time'] = time_text
                        
                        print(f"从行单元格解析到亚盘数据: {company_data['current_asian']}")
                    except Exception as e:
                        print(f"从行单元格解析数据时出错: {str(e)}")
        
        except Exception as e:
            print(f"解析公司 {company_name} 数据时出错: {str(e)}")
            continue
        
        # 只有当成功解析到数据时，才添加该公司的数据
        if company_data['current_asian']['home_odds'] or company_data['initial_asian']['home_odds']:
            asian_data[company_name] = company_data
            print(f"成功解析公司 {company_name} 的亚盘数据")
        else:
            print(f"未能解析到公司 {company_name} 的有效数据，跳过")
    
    if not asian_data:
        print("警告：未能从HTML中解析到任何亚盘数据")
        # 创建一个样例数据作为默认值
        asian_data["未知公司"] = {
            'current_asian': {
                'home_odds': '0.90',
                'handicap': '受半球',
                'away_odds': '0.90',
                'update_time': '',
                'status': ''
            },
            'initial_asian': {
                'home_odds': '0.90',
                'handicap': '受半球',
                'away_odds': '0.90',
                'update_time': ''
            }
        }
        print("已创建默认亚盘数据结构")
    
    return asian_data

def parse_asian_history(html_content, fixture_id):
    """解析亚盘历史变化数据"""
    print("开始解析亚盘历史变化数据...")
    
    soup = BeautifulSoup(html_content, 'html.parser')
    asian_history_data = {}
    
    try:
        # 查找所有亚盘公司行，尝试多种选择器
        company_rows = soup.select('tr[id][ttl="zy"]')
        if not company_rows:
            print("未找到tr[id][ttl='zy']格式的行，尝试其他选择器")
            company_rows = soup.select('tr.tableline')
            if not company_rows:
                print("未找到tr.tableline格式的行，尝试其他选择器")
                company_rows = soup.select('tr[class*="tr"][id]')
                if not company_rows:
                    print("未找到tr[class*='tr'][id]格式的行，尝试其他选择器")
                    company_rows = soup.select('tr[id]')
        
        if not company_rows:
            print("未找到任何亚盘公司行，无法获取历史数据")
            return asian_history_data
        
        print(f"找到 {len(company_rows)} 个亚盘公司行")
        
        for row in company_rows:
            try:
                # 获取公司名称，尝试多种方式
                company_name = "未知公司"
                company_name_elem = row.select_one('td.tb_plgs span.quancheng')
                if company_name_elem:
                    company_name = company_name_elem.text.strip()
                else:
                    # 尝试其他方式获取公司名称
                    company_td = row.select_one('td.tb_plgs')
                    if company_td:
                        company_name = company_td.text.strip().split('\n')[0].strip()
                    else:
                        # 尝试从第一个单元格获取公司名称
                        first_td = row.select_one('td')
                        if first_td and first_td.text.strip() and len(first_td.text.strip()) < 30:
                            company_name = first_td.text.strip()
                            # 检查是否是可能的公司名称
                            if not any(keyword in company_name for keyword in ['bet', 'Bet', '威廉', '澳门', '皇冠', '易胜博']):
                                continue
                
                print(f"处理公司历史数据: {company_name}")
                
                # 获取公司ID
                company_id = None
                
                # 尝试从行ID获取
                row_id = row.get('id')
                if row_id and row_id.startswith('tr'):
                    company_id = row_id[2:]
                    print(f"从行ID获取到公司ID: {company_id}")
                
                # 尝试从链接中获取
                if not company_id:
                    company_link = row.select_one('td.tb_plgs a')
                    if company_link and company_link.get('href'):
                        href = company_link.get('href')
                        if 'cid=' in href:
                            company_id = href.split('cid=')[1].split('&')[0] if '&' in href.split('cid=')[1] else href.split('cid=')[1]
                            print(f"从链接获取到公司ID: {company_id}")
                
                # 尝试从tr的cid属性获取
                if not company_id:
                    cid_attr = row.get('cid')
                    if cid_attr:
                        company_id = cid_attr
                        print(f"从tr标签的cid属性获取到公司ID: {company_id}")
                
                # 尝试从任意链接中获取id参数
                if not company_id:
                    any_link = row.select_one('a[href*="id="]')
                    if any_link and any_link.get('href'):
                        href = any_link.get('href')
                        if 'id=' in href:
                            company_id = href.split('id=')[1].split('&')[0] if '&' in href.split('id=')[1] else href.split('id=')[1]
                            print(f"从链接id参数获取到公司ID: {company_id}")
                
                # 尝试从复选框ID获取
                if not company_id:
                    checkbox = row.select_one('input[type="checkbox"]')
                    if checkbox and checkbox.get('value'):
                        company_id = checkbox.get('value')
                        print(f"从复选框value获取到公司ID: {company_id}")
                    elif checkbox and checkbox.get('id'):
                        checkbox_id = checkbox.get('id')
                        if checkbox_id.startswith('ck'):
                            company_id = checkbox_id[2:]
                            print(f"从复选框id获取到公司ID: {company_id}")
                
                if company_id:
                    # 构建历史亚盘数据URL
                    timestamp = int(time.time() * 1000)  # 当前毫秒时间戳
                    history_url = f"https://odds.500.com/fenxi1/inc/yazhiajax.php?fid={fixture_id}&id={company_id}&t={timestamp}"
                    
                    print(f"尝试获取 {company_name} 的历史亚盘数据: {history_url}")
                    
                    # 设置请求头
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept': 'application/json, text/javascript, */*; q=0.01',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                        'Referer': f'https://odds.500.com/fenxi/yazhi-{fixture_id}.shtml',
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                    
                    try:
                        # 添加随机延迟避免被限制
                        time.sleep(random.uniform(0.5, 1.5))
                        
                        # 发送请求获取历史数据
                        response = requests.get(history_url, headers=headers, timeout=10)
                        
                        if response.status_code == 200:
                            print(f"请求历史数据成功，响应长度: {len(response.text)}")
                            
                            # 解析JSON响应
                            try:
                                # 有时响应可能为HTML或其他格式，尝试使用不同的解析方式
                                try:
                                    history_data = response.json()
                                except:
                                    print(f"响应不是有效的JSON，尝试解析HTML")
                                    history_data = response.text.replace('\n', '').replace('\r', '')
                                    if history_data.startswith('[') and history_data.endswith(']'):
                                        # 手动解析类JSON格式
                                        history_data = eval(history_data)
                                
                                if history_data and (isinstance(history_data, list) or isinstance(history_data, str)):
                                    # 解析历史数据
                                    parsed_history = []
                                    
                                    # 处理不同类型的响应
                                    if isinstance(history_data, list):
                                        items_to_process = history_data
                                    elif isinstance(history_data, str):
                                        # 尝试从HTML字符串中提取表格行
                                        soup_history = BeautifulSoup(history_data, 'html.parser')
                                        items_to_process = [str(tr) for tr in soup_history.select('tr')]
                                    else:
                                        items_to_process = []
                                    
                                    for html_item in items_to_process:
                                        try:
                                            # 解析HTML片段
                                            item_soup = BeautifulSoup(html_item, 'html.parser')
                                            cells = item_soup.select('td')
                                            
                                            if len(cells) >= 4:
                                                # 解析数据
                                                home_odds = cells[0].text.strip()
                                                handicap = cells[1].text.strip()
                                                away_odds = cells[2].text.strip()
                                                update_time = cells[3].text.strip()
                                                
                                                # 判断是否有上升下降指示
                                                home_cell_class = cells[0].get('class', [])
                                                home_change = 0  # 默认不变
                                                if 'tips_up' in home_cell_class:
                                                    home_change = 1  # 上升
                                                elif 'tips_down' in home_cell_class:
                                                    home_change = -1  # 下降
                                                
                                                away_cell_class = cells[2].get('class', [])
                                                away_change = 0  # 默认不变
                                                if 'tips_up' in away_cell_class:
                                                    away_change = 1  # 上升
                                                elif 'tips_down' in away_cell_class:
                                                    away_change = -1  # 下降
                                                
                                                history_item = {
                                                    'home_odds': home_odds,
                                                    'handicap': handicap,
                                                    'away_odds': away_odds,
                                                    'update_time': update_time,
                                                    'home_change': home_change,
                                                    'away_change': away_change
                                                }
                                                parsed_history.append(history_item)
                                        except Exception as e:
                                            print(f"解析单条历史记录时出错: {str(e)}")
                                            continue
                                    
                                    if parsed_history:
                                        asian_history_data[company_name] = parsed_history
                                        print(f"成功获取 {company_name} 的历史亚盘数据, 共 {len(parsed_history)} 条记录")
                                    else:
                                        print(f"未解析到 {company_name} 的有效历史亚盘数据记录")
                                else:
                                    print(f"未获取到 {company_name} 的有效历史亚盘数据, 响应类型: {type(history_data)}")
                            except Exception as e:
                                print(f"解析 {company_name} 历史亚盘JSON响应时出错: {str(e)}")
                        else:
                            print(f"请求 {company_name} 历史亚盘数据失败, 状态码: {response.status_code}")
                    
                    except Exception as e:
                        print(f"获取 {company_name} 历史亚盘数据时出错: {str(e)}")
                        continue
                else:
                    print(f"未能获取 {company_name} 的公司ID，无法请求历史数据")
            
            except Exception as e:
                print(f"解析公司行时出错: {str(e)}")
                continue
    
    except Exception as e:
        print(f"解析历史亚盘数据时出错: {str(e)}")
    
    return asian_history_data

def debug_match(fixture_id, match_id, date):
    # 创建欧赔文件夹
    odds_dir = os.path.join('data', date, 'ou_odds')
    os.makedirs(odds_dir, exist_ok=True)
    
    # 创建大小球文件夹
    size_dir = os.path.join('data', date, 'size_odds')
    os.makedirs(size_dir, exist_ok=True)
    
    # 创建让球文件夹
    handicap_dir = os.path.join('data', date, 'handicap_odds')
    os.makedirs(handicap_dir, exist_ok=True)
    
    # 创建亚盘文件夹
    asian_dir = os.path.join('data', date, 'asian_odds')
    os.makedirs(asian_dir, exist_ok=True)
    
    # 欧赔URL
    odds_url = f'https://odds.500.com/fenxi/ouzhi-{fixture_id}.shtml?ctype=2'
    
    # 大小球URL
    size_url = f'https://odds.500.com/fenxi/daxiao-{fixture_id}.shtml'
    
    # 让球URL
    handicap_url = f'https://odds.500.com/fenxi/rangqiu-{fixture_id}.shtml'
    
    # 亚盘URL
    asian_url = f'https://odds.500.com/fenxi/yazhi-{fixture_id}.shtml'
    
    # 模拟浏览器请求头
    headers = {
        'User-Agent': f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(80, 110)}.0.{random.randint(1000, 9999)}.{random.randint(10, 999)} Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Connection': 'keep-alive',
        'Referer': 'https://odds.500.com/',
        'Upgrade-Insecure-Requests': '1'
    }
    
    success_count = 0
    error_count = 0
    
    try:
        # 使用会话保持
        session = requests.Session()
        
        print(f"[{match_id}] 开始获取数据...")
        
        # 获取欧赔数据
        print(f"[{match_id}] 正在获取欧赔数据")
        try:
            response = session.get(odds_url, headers=headers, timeout=10)
            response.encoding = 'gb2312'
            
            # 添加随机延迟，减轻并发压力
            time.sleep(random.uniform(0.5, 2))
            
            if response.status_code == 403:
                print(f"[{match_id}] 访问被拒绝 (403 Forbidden): {odds_url}")
                error_count += 1
            else:
                # 临时保存HTML文件
                temp_html_path = os.path.join(odds_dir, f'temp_{match_id}.html')
                with open(temp_html_path, 'w', encoding='utf-8') as f:
                    f.write(response.text)
                
                # 解析HTML内容
                with open(temp_html_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                    odds_data = parse_odds_data(html_content)
                    
                    # 获取历史赔率变化数据
                    odds_history = parse_odds_history(html_content, fixture_id, date)
                    
                    # 将历史赔率数据添加到欧赔数据中
                    if odds_history:
                        for company_name, history_data in odds_history.items():
                            if company_name in odds_data:
                                odds_data[company_name]['odds_history'] = history_data
                
                # 保存欧赔数据
                file_path = os.path.join(odds_dir, f'{match_id}.json')
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(odds_data, f, ensure_ascii=False, indent=2)
                
                if odds_data:
                    success_count += 1
                else:
                    print(f"[{match_id}] 警告：未解析到欧赔数据")
                    error_count += 1
        except Exception as e:
            print(f"[{match_id}] 获取欧赔数据出错: {str(e)}")
            error_count += 1
        
        # 获取大小球数据
        print(f"[{match_id}] 正在获取大小球数据")
        try:
            response = session.get(size_url, headers=headers, timeout=10)
            response.encoding = 'gb2312'
            
            # 添加随机延迟，减轻并发压力
            time.sleep(random.uniform(0.5, 2))
            
            if response.status_code == 403:
                print(f"[{match_id}] 访问被拒绝 (403 Forbidden): {size_url}")
                error_count += 1
            else:
                # 临时保存大小球HTML文件
                temp_size_html_path = os.path.join(size_dir, f'temp_{match_id}.html')
                with open(temp_size_html_path, 'w', encoding='utf-8') as f:
                    f.write(response.text)
                
                # 解析大小球HTML内容
                with open(temp_size_html_path, 'r', encoding='utf-8') as f:
                    size_html_content = f.read()
                    size_data = parse_size_data(size_html_content)
                    
                    # 获取大小球历史赔率变化数据
                    size_history = parse_size_history(size_html_content, fixture_id)
                    
                    # 将历史赔率数据添加到大小球数据中
                    if size_history:
                        for company_name, history_data in size_history.items():
                            if company_name in size_data:
                                size_data[company_name]['size_history'] = history_data
                
                # 保存大小球数据
                size_file_path = os.path.join(size_dir, f'{match_id}.json')
                with open(size_file_path, 'w', encoding='utf-8') as f:
                    json.dump(size_data, f, ensure_ascii=False, indent=2)
                
                if size_data:
                    success_count += 1
                else:
                    print(f"[{match_id}] 警告：未解析到大小球数据")
                    error_count += 1
        except Exception as e:
            print(f"[{match_id}] 获取大小球数据出错: {str(e)}")
            error_count += 1
        
        # 获取让球数据
        print(f"[{match_id}] 正在获取让球数据")
        try:
            response = session.get(handicap_url, headers=headers, timeout=10)
            response.encoding = 'gb2312'
            
            # 添加随机延迟，减轻并发压力
            time.sleep(random.uniform(0.5, 2))
            
            if response.status_code == 403:
                print(f"[{match_id}] 访问被拒绝 (403 Forbidden): {handicap_url}")
                error_count += 1
            else:
                # 临时保存让球HTML文件
                temp_handicap_html_path = os.path.join(handicap_dir, f'temp_{match_id}.html')
                with open(temp_handicap_html_path, 'w', encoding='utf-8') as f:
                    f.write(response.text)
                
                # 解析让球HTML内容
                with open(temp_handicap_html_path, 'r', encoding='utf-8') as f:
                    handicap_html_content = f.read()
                    handicap_data = parse_handicap_data(handicap_html_content)
                    
                    # 获取让球历史赔率变化数据
                    handicap_history = parse_handicap_history(handicap_html_content, fixture_id)
                    
                    # 将历史赔率数据添加到让球数据中
                    if handicap_history:
                        for company_name, handicap_values in handicap_history.items():
                            if company_name in handicap_data:
                                for handicap_value, history_data in handicap_values.items():
                                    # 查找对应让球值的数据
                                    for handicap_item in handicap_data[company_name]['handicap_list']:
                                        if handicap_item['handicap'] == handicap_value:
                                            handicap_item['handicap_history'] = history_data
                                            break
                
                # 保存让球数据
                handicap_file_path = os.path.join(handicap_dir, f'{match_id}.json')
                with open(handicap_file_path, 'w', encoding='utf-8') as f:
                    json.dump(handicap_data, f, ensure_ascii=False, indent=2)
                
                if handicap_data:
                    success_count += 1
                else:
                    print(f"[{match_id}] 警告：未解析到让球数据")
                    error_count += 1
        except Exception as e:
            print(f"[{match_id}] 获取让球数据出错: {str(e)}")
            error_count += 1
        
        # 获取亚盘数据
        print(f"[{match_id}] 正在获取亚盘数据")
        try:
            response = session.get(asian_url, headers=headers, timeout=10)
            response.encoding = 'gb2312'
            
            # 添加随机延迟，减轻并发压力
            time.sleep(random.uniform(0.5, 2))
            
            if response.status_code == 403:
                print(f"[{match_id}] 访问被拒绝 (403 Forbidden): {asian_url}")
                error_count += 1
            else:
                # 临时保存亚盘HTML文件
                temp_asian_html_path = os.path.join(asian_dir, f'temp_{match_id}.html')
                with open(temp_asian_html_path, 'w', encoding='utf-8') as f:
                    f.write(response.text)
                
                # 解析亚盘HTML内容
                with open(temp_asian_html_path, 'r', encoding='utf-8') as f:
                    asian_html_content = f.read()
                    asian_data = parse_asian_handicap_data(asian_html_content)
                    
                    # 获取亚盘历史变化数据
                    asian_history = parse_asian_history(asian_html_content, fixture_id)
                    
                    # 将历史数据添加到亚盘数据中
                    if asian_history:
                        for company_name, company_history in asian_history.items():
                            if company_name in asian_data:
                                asian_data[company_name]['asian_history'] = company_history
                
                # 保存亚盘数据
                asian_file_path = os.path.join(asian_dir, f'{match_id}.json')
                with open(asian_file_path, 'w', encoding='utf-8') as f:
                    json.dump(asian_data, f, ensure_ascii=False, indent=2)
                
                if asian_data:
                    success_count += 1
                else:
                    print(f"[{match_id}] 警告：未解析到亚盘数据")
                    error_count += 1
        except Exception as e:
            print(f"[{match_id}] 获取亚盘数据出错: {str(e)}")
            error_count += 1
        
        # 返回处理结果
        print(f"[{match_id}] 数据获取完成: 成功 {success_count}/4, 失败 {error_count}/4")
        return success_count > 0
    
    except Exception as e:
        print(f"[{match_id}] 处理比赛时出错: {str(e)}")
        return False

def clean_temp_html_files(date):
    """清理临时HTML文件"""
    print(f"开始清理 {date} 的临时HTML文件...")
    
    # 清理欧赔文件夹中的临时HTML文件
    odds_dir = os.path.join('data', date, 'ou_odds')
    if os.path.exists(odds_dir):
        for file in os.listdir(odds_dir):
            if file.startswith('temp_') and file.endswith('.html'):
                file_path = os.path.join(odds_dir, file)
                try:
                    os.remove(file_path)
                    print(f"已删除欧赔临时文件: {file_path}")
                except Exception as e:
                    print(f"删除文件 {file_path} 时出错: {str(e)}")
    
    # 清理大小球文件夹中的临时HTML文件
    size_dir = os.path.join('data', date, 'size_odds')
    if os.path.exists(size_dir):
        for file in os.listdir(size_dir):
            if file.startswith('temp_') and file.endswith('.html'):
                file_path = os.path.join(size_dir, file)
                try:
                    os.remove(file_path)
                    print(f"已删除大小球临时文件: {file_path}")
                except Exception as e:
                    print(f"删除文件 {file_path} 时出错: {str(e)}")
    
    # 清理让球文件夹中的临时HTML文件
    handicap_dir = os.path.join('data', date, 'handicap_odds')
    if os.path.exists(handicap_dir):
        for file in os.listdir(handicap_dir):
            if file.startswith('temp_') and file.endswith('.html'):
                file_path = os.path.join(handicap_dir, file)
                try:
                    os.remove(file_path)
                    print(f"已删除让球临时文件: {file_path}")
                except Exception as e:
                    print(f"删除文件 {file_path} 时出错: {str(e)}")
    
    # 清理亚盘文件夹中的临时HTML文件
    asian_dir = os.path.join('data', date, 'asian_odds')
    if os.path.exists(asian_dir):
        for file in os.listdir(asian_dir):
            if file.startswith('temp_') and file.endswith('.html'):
                file_path = os.path.join(asian_dir, file)
                try:
                    os.remove(file_path)
                    print(f"已删除亚盘临时文件: {file_path}")
                except Exception as e:
                    print(f"删除文件 {file_path} 时出错: {str(e)}")
    
    print(f"清理临时HTML文件完成")

def add_handicap_to_main_json(date):
    """将让球赔率数据添加到main.json文件中"""
    print(f"开始将让球值添加到main.json文件...")
    
    # 读取main.json文件
    main_file_path = os.path.join('data', date, f'{date}_main.json')
    if not os.path.exists(main_file_path):
        print(f"未找到main.json文件: {main_file_path}")
        return False
    
    try:
        with open(main_file_path, 'r', encoding='utf-8') as f:
            main_data = json.load(f)
        
        # 让球赔率文件夹路径
        handicap_dir = os.path.join('data', date, 'handicap_odds')
        if not os.path.exists(handicap_dir):
            print(f"未找到让球赔率文件夹: {handicap_dir}")
            return False
        
        # 遍历所有比赛
        for match in main_data:
            match_id = match.get('match_id')
            if not match_id:
                continue
            
            # 让球赔率文件路径
            handicap_file_path = os.path.join(handicap_dir, f'{match_id}.json')
            if not os.path.exists(handicap_file_path):
                print(f"未找到让球赔率文件: {handicap_file_path}")
                continue
            
            try:
                with open(handicap_file_path, 'r', encoding='utf-8') as f:
                    handicap_data = json.load(f)
                
                # 获取竞彩官方的让球值
                if "竞彩官方" in handicap_data and "handicap_list" in handicap_data["竞彩官方"]:
                    handicap_list = handicap_data["竞彩官方"]["handicap_list"]
                    if handicap_list and len(handicap_list) > 0:
                        handicap_value = handicap_list[0].get("handicap", "")
                        
                        # 添加让球值到main数据中
                        match["handicap"] = handicap_value
                        print(f"已为 {match_id} 添加让球值: {handicap_value}")
                    else:
                        print(f"未找到 {match_id} 的让球值数据")
                else:
                    print(f"未找到 {match_id} 的竞彩官方让球数据")
            
            except Exception as e:
                print(f"处理 {match_id} 的让球数据时出错: {str(e)}")
                continue
        
        # 保存更新后的main.json文件
        with open(main_file_path, 'w', encoding='utf-8') as f:
            json.dump(main_data, f, ensure_ascii=False, indent=2)
        
        print(f"让球值已成功添加到main.json文件")
        return True
    
    except Exception as e:
        print(f"处理main.json文件时出错: {str(e)}")
        return False

def remove_jingcai_data(date):
    """
    从ou_odds和handicap_odds文件夹中的所有JSON文件中删除竞彩官方数据
    """
    print(f"开始删除{date}的竞彩官方数据...")
    
    # 欧赔文件夹
    ou_odds_dir = os.path.join('data', date, 'ou_odds')
    # 让球文件夹
    handicap_dir = os.path.join('data', date, 'handicap_odds')
    
    # 处理欧赔文件夹
    if os.path.exists(ou_odds_dir):
        for file_name in os.listdir(ou_odds_dir):
            if file_name.endswith('.json'):
                file_path = os.path.join(ou_odds_dir, file_name)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # 删除竞彩官方数据
                    if "竞彩官方" in data:
                        del data["竞彩官方"]
                        print(f"已从{file_path}删除竞彩官方数据")
                        
                        # 保存更新后的JSON
                        with open(file_path, 'w', encoding='utf-8') as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"处理文件{file_path}时出错: {str(e)}")
    else:
        print(f"未找到欧赔文件夹: {ou_odds_dir}")
    
    # 处理让球文件夹
    if os.path.exists(handicap_dir):
        for file_name in os.listdir(handicap_dir):
            if file_name.endswith('.json'):
                file_path = os.path.join(handicap_dir, file_name)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # 删除竞彩官方数据
                    if "竞彩官方" in data:
                        del data["竞彩官方"]
                        print(f"已从{file_path}删除竞彩官方数据")
                        
                        # 保存更新后的JSON
                        with open(file_path, 'w', encoding='utf-8') as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"处理文件{file_path}时出错: {str(e)}")
    else:
        print(f"未找到让球文件夹: {handicap_dir}")
    
    print(f"删除{date}的竞彩官方数据完成")

def main():
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='爬取足球比赛赔率数据')
    parser.add_argument('-d', '--date', help='指定日期 (格式: YYYY-MM-DD)', default=datetime.now().strftime('%Y-%m-%d'))
    parser.add_argument('--keep-html', action='store_true', help='保留临时HTML文件')
    parser.add_argument('-m', '--match', help='只处理指定的比赛编号 (例如: 周四001)')
    parser.add_argument('-start', help='指定开始的比赛编号 (例如: 周日001)')
    parser.add_argument('-end', help='指定结束的比赛编号 (例如: 周日003)')
    parser.add_argument('-t', '--threads', type=int, help='设置线程数 (默认: 4)', default=4)
    parser.add_argument('--match_id', type=str, help='指定比赛ID')
    parser.add_argument('--fixture_id', type=str, help='指定Fixture ID')
    parser.add_argument('--mode', type=str, choices=['all', 'main', 'odds', 'size', 'handicap', 'asian', 'debug', 'clean', 'odds_script', 'merge_handicap', 'test_size'], 
                        help='指定运行模式: all-全部运行, main-只运行主要函数, odds-只爬取欧赔数据, size-只爬取大小球数据, handicap-只爬取让球数据, asian-只爬取亚盘数据, debug-调试模式, clean-清理临时文件, odds_script-生成赔率脚本')
    
    args = parser.parse_args()
    
    # 使用指定日期或当前日期
    target_date = args.date
    keep_html = args.keep_html
    target_match = args.match or args.match_id
    start_match = args.start
    end_match = args.end
    max_threads = args.threads
    
    # 创建data目录
    if not os.path.exists('data'):
        os.makedirs('data')
    
    # 检查mode参数
    if args.mode:
        # 新版命令行参数逻辑
        date = args.date if args.date else datetime.now().strftime('%Y-%m-%d')
        
        # 根据模式执行相应的函数
        if args.mode == 'main' or args.mode == 'all' or args.mode is None:
            # 创建目录
            create_directory(date)
            
            # 获取比赛数据
            match_data = get_match_data(date)
            
            # 保存到JSON文件
            save_to_json(match_data, date)
            
            # 添加让球数据到main.json
            add_handicap_to_main_json(date)
            
        if args.mode == 'odds' or args.mode == 'all':
            # 创建目录
            create_directory(date)
            
            # 爬取欧赔数据
            main_file_path = os.path.join('data', date, 'main.json')
            if os.path.exists(main_file_path):
                with open(main_file_path, 'r', encoding='utf-8') as f:
                    main_data = json.load(f)
                
                for match in main_data:
                    match_id = match.get('match_id')
                    fixture_id = match.get('fixture_id')
                    if match_id and fixture_id:
                        # 处理请求
                        process_odds_request(fixture_id, match_id, date)
            else:
                print(f"未找到main.json文件: {main_file_path}")
        
        if args.mode == 'size' or args.mode == 'all':
            # 创建目录
            create_directory(date)
            
            # 爬取大小球数据
            main_file_path = os.path.join('data', date, 'main.json')
            if os.path.exists(main_file_path):
                with open(main_file_path, 'r', encoding='utf-8') as f:
                    main_data = json.load(f)
                
                for match in main_data:
                    match_id = match.get('match_id')
                    fixture_id = match.get('fixture_id')
                    if match_id and fixture_id:
                        # 处理请求
                        process_size_request(fixture_id, match_id, date)
            else:
                print(f"未找到main.json文件: {main_file_path}")
        
        if args.mode == 'handicap' or args.mode == 'all':
            # 创建目录
            create_directory(date)
            
            # 爬取让球数据
            main_file_path = os.path.join('data', date, 'main.json')
            if os.path.exists(main_file_path):
                with open(main_file_path, 'r', encoding='utf-8') as f:
                    main_data = json.load(f)
                
                for match in main_data:
                    match_id = match.get('match_id')
                    fixture_id = match.get('fixture_id')
                    if match_id and fixture_id:
                        # 处理请求
                        process_handicap_request(fixture_id, match_id, date)
            else:
                print(f"未找到main.json文件: {main_file_path}")
        
        if args.mode == 'asian' or args.mode == 'all':
            # 创建目录
            create_directory(date)
            
            # 爬取亚盘数据
            main_file_path = os.path.join('data', date, 'main.json')
            if os.path.exists(main_file_path):
                with open(main_file_path, 'r', encoding='utf-8') as f:
                    main_data = json.load(f)
                
                for match in main_data:
                    match_id = match.get('match_id')
                    fixture_id = match.get('fixture_id')
                    if match_id and fixture_id:
                        # 处理请求
                        process_asian_request(fixture_id, match_id, date)
            else:
                print(f"未找到main.json文件: {main_file_path}")
        
        if args.mode == 'debug':
            # 调试模式
            if args.match_id and args.fixture_id:
                debug_match(args.fixture_id, args.match_id, date)
            else:
                print("调试模式需要指定match_id和fixture_id参数")
        
        if args.mode == 'clean':
            # 清理临时文件
            clean_temp_html_files(date)
        
        if args.mode == 'odds_script':
            # 生成赔率脚本
            generate_odds_script(date)
        
        if args.mode == 'merge_handicap':
            # 添加让球数据到main.json
            add_handicap_to_main_json(date)
        
        if args.mode == 'test_size':
            # 测试大小球数据写入
            if args.match_id:
                test_size_data_write(args.match_id, date)
            else:
                print("test_size模式需要指定match_id参数")
        
        # 在所有操作完成后删除竞彩官方数据
        remove_jingcai_data(date)
        
        return
    
    # 如果未指定mode，则执行传统逻辑
    print(f"开始爬取 {target_date} 的比赛数据")
    
    # 获取比赛数据
    matches = get_match_data(target_date)
    
    if matches:
        # 保存数据
        save_to_json(matches, target_date)
        
        # 如果指定了特定比赛，则只处理该比赛
        if target_match:
            print(f"仅处理指定比赛: {target_match}")
            filtered_matches = [match for match in matches if match.get('match_id') == target_match]
            if filtered_matches:
                matches = filtered_matches
                print(f"找到指定比赛: {target_match}")
            else:
                print(f"未找到指定比赛: {target_match}")
                return
        # 如果指定了比赛范围，则按范围筛选
        elif start_match and end_match:
            print(f"处理比赛范围: {start_match} 至 {end_match}")
            # 提取前缀(如"周日")和编号
            start_prefix = ''.join(filter(lambda c: not c.isdigit(), start_match))
            end_prefix = ''.join(filter(lambda c: not c.isdigit(), end_match))
            
            # 确保前缀相同
            if start_prefix != end_prefix:
                print(f"错误: 开始和结束比赛的前缀不同 ({start_prefix} vs {end_prefix})")
                return
                
            # 提取编号部分
            try:
                start_num = int(''.join(filter(lambda c: c.isdigit(), start_match)))
                end_num = int(''.join(filter(lambda c: c.isdigit(), end_match)))
                
                if start_num > end_num:
                    print(f"错误: 开始编号 {start_num} 大于结束编号 {end_num}")
                    return
                    
                # 筛选比赛
                filtered_matches = []
                for match in matches:
                    match_id = match.get('match_id', '')
                    if match_id.startswith(start_prefix):
                        match_num = int(''.join(filter(lambda c: c.isdigit(), match_id)))
                        if start_num <= match_num <= end_num:
                            filtered_matches.append(match)
                
                if filtered_matches:
                    matches = filtered_matches
                    print(f"找到符合范围的比赛: {len(matches)} 场")
                else:
                    print(f"未找到范围 {start_match} 至 {end_match} 的比赛")
                    return
            except ValueError:
                print(f"错误: 无法解析比赛编号")
                return
        
        # 使用多线程处理比赛数据
        print(f"使用 {max_threads} 个线程处理 {len(matches)} 场比赛...")
        
        # 创建目录结构（防止线程竞争创建目录）
        odds_dir = os.path.join('data', target_date, 'ou_odds')
        size_dir = os.path.join('data', target_date, 'size_odds')
        handicap_dir = os.path.join('data', target_date, 'handicap_odds')
        asian_dir = os.path.join('data', target_date, 'asian_odds')
        os.makedirs(odds_dir, exist_ok=True)
        os.makedirs(size_dir, exist_ok=True)
        os.makedirs(handicap_dir, exist_ok=True)
        os.makedirs(asian_dir, exist_ok=True)

        successful_matches = 0
        failed_matches = 0
        
        # 使用线程池处理所有比赛
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            # 提交所有任务
            future_to_match = {
                executor.submit(debug_match, match['fixture_id'], match['match_id'], target_date): match 
                for match in matches if 'fixture_id' in match
            }
            
            # 处理任务结果
            for future in as_completed(future_to_match):
                match = future_to_match[future]
                try:
                    result = future.result()
                    if result:
                        print(f"成功处理比赛: {match['match_id']} - {match.get('home_team', '')} vs {match.get('away_team', '')}")
                        successful_matches += 1
                    else:
                        print(f"处理比赛失败: {match['match_id']}")
                        failed_matches += 1
                        
                    # 特殊处理周二001的结果
                    if match['match_id'] == '周二001':
                        size_file_path = os.path.join('data', target_date, 'size_odds', f"{match['match_id']}.json")
                        if os.path.exists(size_file_path):
                            with open(size_file_path, 'r', encoding='utf-8') as f:
                                data = f.read()
                                if data.strip() == '{}' or len(data) < 10:
                                    print(f"周二001数据为空，尝试重新解析...")
                                    # 重新调用测试函数尝试解析数据
                                    test_size_data_write(match['match_id'], target_date)
                except Exception as e:
                    print(f"处理比赛 {match['match_id']} 时出错: {str(e)}")
                    failed_matches += 1
        
        print(f"所有比赛处理完成: 成功 {successful_matches} 场, 失败 {failed_matches} 场")
        
        # 如果不需要保留HTML文件，则清理
        if not keep_html:
            clean_temp_html_files(target_date)
        
        # 在所有处理完成后，将让球值添加到main.json文件中
        add_handicap_to_main_json(target_date)
        
        # 在所有处理完成后，删除竞彩官方数据
        remove_jingcai_data(target_date)
                
    else:
        print(f"未获取到 {target_date} 的比赛数据")

if __name__ == '__main__':
    main()