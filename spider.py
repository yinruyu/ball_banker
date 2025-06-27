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
import traceback

# 添加博彩公司名称映射函数
def replace_company_names(company_name):
    """将带星号的博彩公司名称替换为完整名称"""
    company_map = {
        "威***": "威廉希尔",
        "澳*": "澳门",
        "立*": "立博",
        "36*": "365bet",
        "Inter*": "Interwetten",
        "SN**": "SNAI",
        "皇*": "皇冠",
        "易**": "易胜博",
        "韦*": "韦德",
        "10*": "10BET",
        "平*": "平博",
        "利*": "利记",
        "马*": "马博",
        "12*": "12bet",
        "明*": "明陞",
        "18*": "18Bet",
        "盈*": "盈禾",
        "金宝*": "金宝博",
        "伟*": "伟德",
        "YSB*": "YSB体育",
        "必*": "必发",
        "bet3*": "bet365",
        "SP*": "SportingBet",
        "优*": "优胜客",
        "乐天*": "乐天堂",
        "金宝博": "金宝博",
        "Crown*": "Crown",
        "明升": "明升",
        "BET*": "BETCMP",
        "IM*": "IM体育",
        "巴黎*": "巴黎人",
        "沙巴*": "沙巴体育",
        "官方": "官方",
        # 添加其他可能的映射
    }
    
    # 检查是否能够直接映射
    if company_name in company_map:
        return company_map[company_name]
    
    # 如果不能直接映射，尝试使用正则表达式进行部分匹配
    for masked, full in company_map.items():
        # 创建一个正则表达式，将*替换为通配符
        pattern = masked.replace("*", ".*")
        if re.match(f"^{pattern}$", company_name):
            return full
    
    # 如果没有匹配，则返回原始名称
    return company_name

# 添加重试机制的函数
def make_request_with_retry(url, headers, max_retries=3, retry_delay=2, timeout=10):
    """发送请求并在失败时进行重试"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            
            # 处理503错误或其他服务器错误
            if response.status_code >= 500:
                print(f"服务器错误 (状态码: {response.status_code})，尝试重试 ({attempt+1}/{max_retries})...")
                time.sleep(retry_delay * (attempt + 1))  # 指数退避策略
                continue
                
            # 处理403错误
            if response.status_code == 403:
                print(f"访问被拒绝 (403 Forbidden)，更换请求头并重试...")
                # 更新User-Agent
                headers['User-Agent'] = f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(80, 110)}.0.{random.randint(1000, 9999)}.{random.randint(10, 999)} Safari/537.36'
                time.sleep(retry_delay * (attempt + 1))
                continue
                
            # 处理其他HTTP错误
            if response.status_code != 200:
                print(f"请求失败，状态码: {response.status_code}，尝试重试 ({attempt+1}/{max_retries})...")
                time.sleep(retry_delay * (attempt + 1))
                continue
            
            # 检查响应内容是否为空
            if not response.text.strip():
                print(f"响应内容为空，尝试重试 ({attempt+1}/{max_retries})...")
                time.sleep(retry_delay * (attempt + 1))
                continue
                
            # 响应成功且有内容
            return response
            
        except requests.exceptions.RequestException as e:
            print(f"请求异常: {str(e)}，尝试重试 ({attempt+1}/{max_retries})...")
            time.sleep(retry_delay * (attempt + 1))
    
    # 所有重试都失败，返回None
    print(f"请求失败，已达到最大重试次数: {max_retries}")
    return None

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
        'User-Agent': f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(80, 110)}.0.{random.randint(1000, 9999)}.{random.randint(10, 999)} Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    try:
        print(f"正在获取 {date} 的比赛数据...")
        
        # 使用重试机制发送请求
        response = make_request_with_retry(url, headers)
        
        if not response or response.status_code != 200:
            print(f"请求失败，状态码: {response.status_code if response else 'None'}")
            return []
            
        response.encoding = 'gb2312'
        
        # 保存HTML以供调试
        with open('debug.html', 'w', encoding='utf-8') as f:
            f.write(response.text)
        print("已保存HTML到debug.html文件")
        
        matches = []
        
        # 尝试解析3次
        max_parse_retries = 2
        
        for retry in range(max_parse_retries + 1):
            try:
                soup = BeautifulSoup(response.text, 'lxml')
                
                # 查找所有比赛行
                match_rows = soup.select('tr.bet-tb-tr')
                print(f"找到 {len(match_rows)} 场比赛")
                
                if not match_rows and retry < max_parse_retries:
                    print(f"未找到比赛行，第 {retry+1} 次重试解析...")
                    time.sleep(1)
                    continue
                
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
                
                # 如果成功解析到比赛，跳出重试循环
                if matches:
                    break
                elif retry < max_parse_retries:
                    print(f"未解析到比赛数据，第 {retry+1} 次重试解析...")
                    time.sleep(1)
            
            except Exception as e:
                if retry < max_parse_retries:
                    print(f"解析HTML出错，第 {retry+1} 次重试: {str(e)}")
                    time.sleep(1)
                else:
                    print(f"所有重试后仍解析HTML出错: {str(e)}")
        
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
        
        # 使用replace_company_names函数转换为完整名称
        company_name = replace_company_names(company_name)
        
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
            
        # 使用replace_company_names函数转换为完整名称
        company_name = replace_company_names(company_name)
            
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
        
        # 使用replace_company_names函数转换为完整名称
        company_name = replace_company_names(company_name)
        
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
                        'User-Agent': f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(80, 110)}.0.{random.randint(1000, 9999)}.{random.randint(10, 999)} Safari/537.36',
                        'Accept': 'application/json, text/javascript, */*; q=0.01',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                        'Referer': f'https://odds.500.com/fenxi/yazhi-{fixture_id}.shtml',
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                    
                    max_data_retries = 2  # 数据为空时的最大重试次数
                    
                    for data_retry in range(max_data_retries + 1):
                        try:
                            # 添加随机延迟避免被限制
                            time.sleep(random.uniform(0.5, 1.5))
                            
                            # 使用重试函数发送请求
                            response = make_request_with_retry(history_url, headers)
                            
                            if response and response.status_code == 200:
                                response_text = response.text
                                print(f"请求历史数据成功，响应长度: {len(response_text)}")
                                
                                # 检查响应是否为空或无效数据
                                if not response_text or response_text.strip() == '[]' or response_text.strip() == '{}':
                                    if data_retry < max_data_retries:
                                        print(f"响应数据为空，进行第 {data_retry+1} 次重试...")
                                        time.sleep(2 * (data_retry + 1))
                                        continue
                                    else:
                                        print(f"历史数据重试耗尽，未获取到 {company_name} 的历史数据")
                                        break
                                
                                # 解析JSON响应
                                try:
                                    # 有时响应可能为HTML或其他格式，尝试使用不同的解析方式
                                    try:
                                        history_data = response.json()
                                    except:
                                        print(f"响应不是有效的JSON，尝试解析HTML")
                                        history_data = response_text.replace('\n', '').replace('\r', '')
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
                                            break  # 成功获取数据，跳出重试循环
                                        elif data_retry < max_data_retries:
                                            print(f"未解析到有效历史记录，进行第 {data_retry+1} 次重试...")
                                            time.sleep(2 * (data_retry + 1))
                                            continue
                                        else:
                                            print(f"未解析到 {company_name} 的有效历史亚盘数据记录")
                                    elif data_retry < max_data_retries:
                                        print(f"响应数据无效，进行第 {data_retry+1} 次重试...")
                                        time.sleep(2 * (data_retry + 1))
                                        continue
                                    else:
                                        print(f"未获取到 {company_name} 的有效历史亚盘数据, 响应类型: {type(history_data)}")
                                except Exception as e:
                                    print(f"解析 {company_name} 历史亚盘JSON响应时出错: {str(e)}")
                                    if data_retry < max_data_retries:
                                        print(f"解析错误，进行第 {data_retry+1} 次重试...")
                                        time.sleep(2 * (data_retry + 1))
                                        continue
                            elif data_retry < max_data_retries:
                                print(f"请求失败，进行第 {data_retry+1} 次重试...")
                                time.sleep(2 * (data_retry + 1))
                                continue
                            else:
                                print(f"请求 {company_name} 历史亚盘数据失败")
                        
                        except Exception as e:
                            print(f"获取 {company_name} 历史亚盘数据时出错: {str(e)}")
                            if data_retry < max_data_retries:
                                print(f"发生异常，进行第 {data_retry+1} 次重试...")
                                time.sleep(2 * (data_retry + 1))
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
    # 为每场比赛创建单独的文件夹
    match_dir = os.path.join('data', date, match_id)
    os.makedirs(match_dir, exist_ok=True)
    
    # 旧的文件夹路径(用于临时文件)
    temp_odds_dir = os.path.join('data', date, 'temp_ou_odds')
    temp_size_dir = os.path.join('data', date, 'temp_size_odds')
    temp_asian_dir = os.path.join('data', date, 'temp_asian_odds')
    temp_bifa_dir = os.path.join('data', date, 'temp_bifa_data')
    temp_kelly_dir = os.path.join('data', date, 'temp_kelly_history')
    
    # 创建临时文件夹(用于HTML)
    os.makedirs(temp_odds_dir, exist_ok=True)
    os.makedirs(temp_size_dir, exist_ok=True)
    os.makedirs(temp_asian_dir, exist_ok=True)
    os.makedirs(temp_bifa_dir, exist_ok=True)
    os.makedirs(temp_kelly_dir, exist_ok=True)
    
    # 欧赔URL
    odds_url = f'https://odds.500.com/fenxi/ouzhi-{fixture_id}.shtml?ctype=2'
    
    # 大小球URL
    size_url = f'https://odds.500.com/fenxi/daxiao-{fixture_id}.shtml'
    
    # 让球URL
    handicap_url = f'https://odds.500.com/fenxi/rangqiu-{fixture_id}.shtml'
    
    # 亚盘URL
    asian_url = f'https://odds.500.com/fenxi/yazhi-{fixture_id}.shtml'
    
    # 必发交易URL
    bifa_url = f'https://odds.500.com/fenxi/touzhu-{fixture_id}.shtml'
    
    # 模拟浏览器请求头
    headers = {
        'User-Agent': f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(80, 110)}.0.{random.randint(1000, 9999)}.{random.randint(10, 999)} Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Connection': 'keep-alive',
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
            # 使用重试机制获取欧赔数据
            response = make_request_with_retry(odds_url, headers)
            
            # 添加随机延迟，减轻并发压力
            time.sleep(random.uniform(0.5, 2))
            
            if not response or response.status_code == 403:
                print(f"[{match_id}] 访问被拒绝 (403 Forbidden): {odds_url}")
                error_count += 1
            else:
                response.encoding = 'gb2312'  # 设置编码
                
                # 临时保存HTML文件
                temp_html_path = os.path.join(temp_odds_dir, f'temp_{match_id}.html')
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
                            # 尝试使用原始公司名和替换后的公司名
                            replaced_company_name = replace_company_names(company_name)
                            if company_name in odds_data:
                                odds_data[company_name]['odds_history'] = history_data
                            elif replaced_company_name in odds_data:
                                odds_data[replaced_company_name]['odds_history'] = history_data
                    
                    # 获取凯利指数历史数据
                    kelly_history = parse_kelly_history(html_content, fixture_id)
                    
                    # 保存凯利指数历史数据到比赛文件夹中
                    if kelly_history:
                        kelly_file_path = os.path.join(match_dir, 'kelly_history.json')
                        with open(kelly_file_path, 'w', encoding='utf-8') as f:
                            json.dump(kelly_history, f, ensure_ascii=False, indent=2)
                        print(f"[{match_id}] 凯利指数历史数据已保存到: {kelly_file_path}")
                
                # 保存欧赔数据到比赛文件夹中
                file_path = os.path.join(match_dir, 'ou_odds.json')
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
            # 使用重试机制获取大小球数据
            response = make_request_with_retry(size_url, headers)
            
            # 添加随机延迟，减轻并发压力
            time.sleep(random.uniform(0.5, 2))
            
            if not response or response.status_code == 403:
                print(f"[{match_id}] 访问被拒绝 (403 Forbidden): {size_url}")
                error_count += 1
            else:
                response.encoding = 'gb2312'  # 设置编码
                
                # 临时保存大小球HTML文件
                temp_size_html_path = os.path.join(temp_size_dir, f'temp_{match_id}.html')
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
                            # 尝试使用原始公司名和替换后的公司名
                            replaced_company_name = replace_company_names(company_name)
                            if company_name in size_data:
                                size_data[company_name]['size_history'] = history_data
                            elif replaced_company_name in size_data:
                                size_data[replaced_company_name]['size_history'] = history_data
                
                # 保存大小球数据到比赛文件夹中
                size_file_path = os.path.join(match_dir, 'size_odds.json')
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
                success_count += 1
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
                temp_asian_html_path = os.path.join(temp_asian_dir, f'temp_{match_id}.html')
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
                        for company_name, history_data in asian_history.items():
                            # 尝试使用原始公司名和替换后的公司名
                            replaced_company_name = replace_company_names(company_name)
                            if company_name in asian_data:
                                asian_data[company_name]['asian_history'] = history_data
                            elif replaced_company_name in asian_data:
                                asian_data[replaced_company_name]['asian_history'] = history_data
                
                # 保存亚盘数据到比赛文件夹中
                asian_file_path = os.path.join(match_dir, 'asian_odds.json')
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
        
        # 获取必发交易数据
        print(f"[{match_id}] 正在获取必发交易数据")
        try:
            # 使用重试机制获取必发交易数据
            response = make_request_with_retry(bifa_url, headers)
            
            # 添加随机延迟，减轻并发压力
            time.sleep(random.uniform(0.5, 2))
            
            if not response or response.status_code == 403:
                print(f"[{match_id}] 访问被拒绝 (403 Forbidden): {bifa_url}")
                error_count += 1
            else:
                response.encoding = 'gb2312'  # 设置编码
                
                # 临时保存必发交易HTML文件
                temp_bifa_html_path = os.path.join(temp_bifa_dir, f'temp_{match_id}.html')
                with open(temp_bifa_html_path, 'w', encoding='utf-8') as f:
                    f.write(response.text)
                
                # 解析必发交易HTML内容
                with open(temp_bifa_html_path, 'r', encoding='utf-8') as f:
                    bifa_html_content = f.read()
                    bifa_data = parse_bifa_data(bifa_html_content)
                
                # 保存必发交易数据到比赛文件夹中
                bifa_file_path = os.path.join(match_dir, 'bifa_data.json')
                with open(bifa_file_path, 'w', encoding='utf-8') as f:
                    json.dump(bifa_data, f, ensure_ascii=False, indent=2)
                
                # 检查是否有实际数据（不仅仅是空的结构）
                has_actual_data = False
                if bifa_data.get("hot_analysis") and len(bifa_data["hot_analysis"]) > 0:
                    has_actual_data = True
                elif bifa_data.get("trade_analysis") and len(bifa_data["trade_analysis"]) > 0:
                    has_actual_data = True
                elif bifa_data.get("big_trade") and len(bifa_data["big_trade"]) > 0:
                    has_actual_data = True
                elif bifa_data.get("trade_details") and len(bifa_data["trade_details"]) > 0:
                    has_actual_data = True
                
                if has_actual_data:
                    success_count += 1
                    print(f"[{match_id}] 必发交易数据已保存到: {bifa_file_path}")
                elif "no_data_reason" in bifa_data:
                    print(f"[{match_id}] 警告：{bifa_data.get('no_data_reason')}")
                    # 虽然没有实际数据，但文件已保存，不算作错误
                    success_count += 1
                else:
                    print(f"[{match_id}] 警告：解析到的必发交易数据为空")
                    error_count += 1
        except Exception as e:
            print(f"[{match_id}] 获取必发交易数据出错: {str(e)}")
            error_count += 1
        
        # 返回处理结果
        print(f"[{match_id}] 数据获取完成: 成功 {success_count}/5, 失败 {error_count}/5")
        return success_count > 0
    
    except Exception as e:
        print(f"[{match_id}] 处理比赛时出错: {str(e)}")
        return False

def clean_temp_html_files(date):
    """清理临时HTML文件"""
    print(f"开始清理 {date} 的临时HTML文件...")
    
    # 清理临时文件夹
    temp_dirs = [
        os.path.join('data', date, 'temp_ou_odds'),
        os.path.join('data', date, 'temp_size_odds'),
        os.path.join('data', date, 'temp_asian_odds'),
        os.path.join('data', date, 'temp_bifa_data'),
        os.path.join('data', date, 'temp_kelly_history')
    ]
    
    for temp_dir in temp_dirs:
        if os.path.exists(temp_dir):
            for file in os.listdir(temp_dir):
                if file.startswith('temp_') and file.endswith('.html'):
                    file_path = os.path.join(temp_dir, file)
                    try:
                        os.remove(file_path)
                        print(f"已删除临时文件: {file_path}")
                    except Exception as e:
                        print(f"删除文件 {file_path} 时出错: {str(e)}")
            
            # 删除空的临时文件夹
            try:
                if len(os.listdir(temp_dir)) == 0:
                    os.rmdir(temp_dir)
                    print(f"已删除空的临时文件夹: {temp_dir}")
            except Exception as e:
                print(f"删除文件夹 {temp_dir} 时出错: {str(e)}")
    
    print(f"清理临时HTML文件完成")

def add_handicap_to_main_json(date):
    """将让球赔率数据添加到main.json文件中"""
    print(f"开始将让球值添加到main.json文件...")
    
    # 读取main.json文件
    main_file_path = os.path.join('data', date, f'{date}_main.json')
    if not os.path.exists(main_file_path):
        print(f"未找到main.json文件: {main_file_path}")
        return False
    
    # 由于让球文件已被注释，不再需要读取
    print(f"让球文件已被注释，跳过添加让球值到main.json")
    return True

def test_size_data_write(match_id, date):
    """测试写入大小球数据"""
    try:
        # 创建比赛文件夹
        match_dir = os.path.join('data', date, match_id)
        os.makedirs(match_dir, exist_ok=True)
        
        # 临时文件夹路径
        temp_size_dir = os.path.join('data', date, 'temp_size_odds')
        os.makedirs(temp_size_dir, exist_ok=True)
        
        # HTML文件路径
        temp_size_html_path = os.path.join(temp_size_dir, f'temp_{match_id}.html')
        
        # 检查临时HTML文件是否存在
        if os.path.exists(temp_size_html_path):
            print(f"找到临时HTML文件: {temp_size_html_path}")
            
            # 读取HTML内容并解析
            with open(temp_size_html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
                size_data = parse_size_data(html_content)
            
            if size_data:
                # 保存大小球数据到比赛文件夹
                size_file_path = os.path.join(match_dir, 'size_odds.json')
                print(f"尝试写入数据到: {size_file_path}")
                with open(size_file_path, 'w', encoding='utf-8') as f:
                    json.dump(size_data, f, ensure_ascii=False, indent=2)
                print(f"已成功保存大小球数据到: {size_file_path}")
                
                # 验证文件是否已正确写入
                if os.path.exists(size_file_path):
                    file_size = os.path.getsize(size_file_path)
                    print(f"文件大小: {file_size} 字节")
                    
                    with open(size_file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        print(f"文件内容长度: {len(content)} 字符")
                    
                    return True
                else:
                    print(f"错误：文件未创建 {size_file_path}")
                    return False
            else:
                print(f"无法从HTML文件解析到数据: {temp_size_html_path}")
                return False
        else:
            print(f"临时HTML文件不存在: {temp_size_html_path}")
            return False
        
    except Exception as e:
        print(f"测试写入数据时出错: {str(e)}")
        return False

def remove_jingcai_data(date):
    """删除指定日期所有比赛文件夹中的竞彩官方数据"""
    print(f"开始删除 {date} 竞彩官方数据...")
    
    # 获取日期目录下所有比赛文件夹
    date_dir = os.path.join('data', date)
    if not os.path.exists(date_dir):
        print(f"日期目录不存在: {date_dir}")
        return False
    
    # 获取所有比赛文件夹
    match_folders = []
    for item in os.listdir(date_dir):
        item_path = os.path.join(date_dir, item)
        if os.path.isdir(item_path) and not item.startswith('temp_'):
            if item not in ['ou_odds', 'size_odds', 'asian_odds', 'kelly_history', 'bifa_data']:
                match_folders.append(item)
    
    if not match_folders:
        print(f"未找到任何比赛文件夹")
        return False
    
    print(f"找到 {len(match_folders)} 个比赛文件夹")
    
    # 需要处理的文件类型
    file_types = ['ou_odds.json', 'kelly_history.json']
    
    files_processed = 0
    files_modified = 0
    
    # 处理每个比赛文件夹
    for match_id in match_folders:
        match_dir = os.path.join(date_dir, match_id)
        
        # 处理每种文件类型
        for file_type in file_types:
            file_path = os.path.join(match_dir, file_type)
            
            if not os.path.exists(file_path):
                continue
                
            files_processed += 1
            
            try:
                # 读取JSON文件
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 检查并删除竞彩官方数据
                if '竞彩官方' in data:
                    del data['竞彩官方']
                    
                    # 将修改后的数据写回文件
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    
                    files_modified += 1
                    print(f"已从 {file_path} 中删除竞彩官方数据")
            
            except Exception as e:
                print(f"处理文件 {file_path} 时出错: {str(e)}")
    
    print(f"竞彩官方数据删除完成: 处理了 {files_processed} 个文件, 修改了 {files_modified} 个文件")
    return files_modified > 0

def convert_json_to_compact(date):
    """将JSON数据转换为紧凑格式，并存储为易读的TXT文件"""
    print(f"开始将 {date} 的数据转换为紧凑格式...")
    
    # 获取日期目录下所有比赛文件夹
    date_dir = os.path.join('data', date)
    if not os.path.exists(date_dir):
        print(f"日期目录不存在: {date_dir}")
        return False
    
    # 获取所有比赛文件夹
    match_folders = []
    for item in os.listdir(date_dir):
        item_path = os.path.join(date_dir, item)
        if os.path.isdir(item_path) and not item.startswith('temp_'):
            if item not in ['ou_odds', 'size_odds', 'asian_odds', 'kelly_history', 'bifa_data']:
                match_folders.append(item)
    
    if not match_folders:
        print(f"未找到任何比赛文件夹")
        return False
    
    print(f"找到 {len(match_folders)} 个比赛文件夹")
    
    # 数据类型和对应文件名
    data_types = {
        'ou_odds.json': {'name': '欧赔数据', 'txt_name': 'ou_odds.txt'},
        'size_odds.json': {'name': '大小球数据', 'txt_name': 'size_odds.txt'},
        'asian_odds.json': {'name': '亚盘数据', 'txt_name': 'asian_odds.txt'},
        'kelly_history.json': {'name': '凯利指数数据', 'txt_name': 'kelly_history.txt'}
        # 必发数据保持JSON格式，不转换
    }
    
    files_processed = 0
    files_converted = 0
    files_deleted = 0
    
    # 处理每个比赛文件夹
    for match_id in match_folders:
        match_dir = os.path.join(date_dir, match_id)
        
        # 处理每种数据类型
        for json_file, type_info in data_types.items():
            json_path = os.path.join(match_dir, json_file)
            txt_path = os.path.join(match_dir, type_info['txt_name'])
            
            if not os.path.exists(json_path):
                continue
                
            files_processed += 1
            
            try:
                # 读取JSON文件
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 凯利历史数据的结构与其他不同，需要特殊处理
                if 'kelly_history' in json_file:
                    # 凯利历史数据是一个字典，其中每个键是公司名，值是历史记录列表
                    with open(txt_path, 'w', encoding='utf-8') as f:
                        # 添加文件头部的数据格式说明
                        data_type = type_info['name']
                        f.write(f"# {data_type} - 格式说明\n")
                        f.write("# 公司名|初始凯利[胜,平,负,更新时间]|历史变化[胜,平,负,更新时间],...\n\n")
                        
                        # 处理每个公司的数据
                        for company, history_data in data.items():
                            # 使用映射后的公司名
                            full_name = replace_company_names(company)
                            line_parts = [full_name]
                            
                            if history_data and isinstance(history_data, list):
                                # 使用最早的记录作为初始值
                                initial_record = history_data[-1] if history_data else {}
                                initial = f"[{initial_record.get('kelly_win', '')},{initial_record.get('kelly_draw', '')},{initial_record.get('kelly_lose', '')},{initial_record.get('update_time', '')}]"
                                line_parts.append(initial)
                                
                                # 所有记录作为历史变化
                                history_items = []
                                for item in history_data:
                                    history_item = f"[{item.get('kelly_win', '')},{item.get('kelly_draw', '')},{item.get('kelly_lose', '')},{item.get('update_time', '')}]"
                                    history_items.append(history_item)
                                
                                line_parts.append(",".join(history_items))
                            else:
                                # 如果没有历史数据，添加空值
                                line_parts.append("[]")
                                line_parts.append("")
                            
                            # 使用竖线(|)作为主要分隔符将所有部分连接起来
                            f.write("|".join(line_parts) + "\n")
                    
                    # 成功转换为txt格式后，删除原JSON文件
                    try:
                        os.remove(json_path)
                        files_deleted += 1
                    except Exception as e:
                        print(f"删除文件 {json_path} 时出错: {str(e)}")
                    
                    files_converted += 1
                    continue
                
                # 替换公司名称 - 创建一个新的数据结构，使用替换后的公司名作为键
                updated_data = {}
                for company, company_data in data.items():
                    # 恢复使用公司名称映射
                    full_name = replace_company_names(company)
                    # 保留原始公司名称，以便后续能找到对应的历史数据
                    company_data['original_company_name'] = company
                    updated_data[full_name] = company_data
                
                # 将数据转换为紧凑格式
                with open(txt_path, 'w', encoding='utf-8') as f:
                    # 添加文件头部的数据格式说明
                    data_type = type_info['name']
                    
                    if 'asian_odds' in json_file:
                        f.write(f"# {data_type} - 格式说明\n")
                        f.write("# 公司名|初盘盘口,初盘主赔率,初盘客赔率,初盘更新时间|即时盘口,即时主赔率,即时客赔率,即时更新时间,即时状态|历史变化[盘口,主赔率,客赔率,更新时间]\n")
                    elif 'ou_odds' in json_file:
                        f.write(f"# {data_type} - 格式说明\n")
                        f.write("# 公司名|初盘胜,初盘平,初盘负,初返还率,初胜率,初平率,初负率,初凯利胜,初凯利平,初凯利负|即时胜,即时平,即时负,即返还率,即胜率,即平率,即负率,即凯利胜,即凯利平,即凯利负|历史变化[胜赔,平赔,负赔,返还率,更新时间,胜变化,平变化,负变化]\n")
                    elif 'size_odds' in json_file:
                        f.write(f"# {data_type} - 格式说明\n")
                        f.write("# 公司名|初盘盘口,初盘大球赔率,初盘小球赔率|即时盘口,即时大球赔率,即时小球赔率|历史变化[盘口,大球赔率,小球赔率,更新时间]\n")
                    elif 'kelly_history' in json_file:
                        f.write(f"# {data_type} - 格式说明\n")
                        f.write("# 公司名|初始凯利[胜,平,负,更新时间]|历史变化[胜,平,负,更新时间],...\n")
                    
                    f.write("\n")
                    
                    # 处理每个公司的数据 - 使用更新后的数据结构
                    for company, company_data in updated_data.items():
                        line_parts = [company]
                        
                        # 根据不同类型的数据使用不同的格式化方式
                        if 'asian_odds' in json_file:
                            # 亚盘数据特殊处理，结构是嵌套的
                            if 'initial_asian' in company_data:
                                initial_asian = company_data['initial_asian']
                                initial = f"{initial_asian.get('handicap', '')},{initial_asian.get('home_odds', '')},{initial_asian.get('away_odds', '')},{initial_asian.get('update_time', '')}"
                                line_parts.append(initial)
                            else:
                                line_parts.append(",,")
                            
                            if 'current_asian' in company_data:
                                current_asian = company_data['current_asian']
                                current = f"{current_asian.get('handicap', '')},{current_asian.get('home_odds', '')},{current_asian.get('away_odds', '')},{current_asian.get('update_time', '')},{current_asian.get('status', '')}"
                                line_parts.append(current)
                            else:
                                line_parts.append(",,")
                            
                            # 历史变化
                            history = []
                            # 亚盘历史数据，处理多种可能的键名
                            if 'asian_history' in company_data and company_data['asian_history']:
                                for h in company_data['asian_history']:
                                    history_item = f"[{h.get('handicap', '')},{h.get('home_odds', '')},{h.get('away_odds', '')},{h.get('update_time', '')}]"
                                    history.append(history_item)
                            # 向上查找历史数据：在原始公司名下查找
                            elif 'original_company_name' in company_data and company_data['original_company_name'] in data:
                                original_data = data[company_data['original_company_name']]
                                if 'asian_history' in original_data:
                                    for h in original_data['asian_history']:
                                        history_item = f"[{h.get('handicap', '')},{h.get('home_odds', '')},{h.get('away_odds', '')},{h.get('update_time', '')}]"
                                        history.append(history_item)
                            # 尝试在原始数据中查找替换后的公司名
                            elif company in data and 'asian_history' in data[company]:
                                for h in data[company]['asian_history']:
                                    history_item = f"[{h.get('handicap', '')},{h.get('home_odds', '')},{h.get('away_odds', '')},{h.get('update_time', '')}]"
                                    history.append(history_item)
                            line_parts.append(",".join(history))
                        
                        elif 'ou_odds' in json_file:
                            # 初盘数据
                            initial_odds = company_data.get('initial_odds', ['', '', ''])
                            initial_probs = company_data.get('initial_probabilities', ['', '', ''])
                            initial_kelly = company_data.get('initial_kelly', ['', '', ''])
                            initial = f"{initial_odds[0] if len(initial_odds) > 0 else ''},{initial_odds[1] if len(initial_odds) > 1 else ''},{initial_odds[2] if len(initial_odds) > 2 else ''},{company_data.get('initial_return_rate', '')},{initial_probs[0] if len(initial_probs) > 0 else ''},{initial_probs[1] if len(initial_probs) > 1 else ''},{initial_probs[2] if len(initial_probs) > 2 else ''},{initial_kelly[0] if len(initial_kelly) > 0 else ''},{initial_kelly[1] if len(initial_kelly) > 1 else ''},{initial_kelly[2] if len(initial_kelly) > 2 else ''}"
                            line_parts.append(initial)
                            
                            # 即时盘数据
                            current_odds = company_data.get('current_odds', ['', '', ''])
                            current_probs = company_data.get('current_probabilities', ['', '', ''])
                            current_kelly = company_data.get('current_kelly', ['', '', ''])
                            current = f"{current_odds[0] if len(current_odds) > 0 else ''},{current_odds[1] if len(current_odds) > 1 else ''},{current_odds[2] if len(current_odds) > 2 else ''},{company_data.get('current_return_rate', '')},{current_probs[0] if len(current_probs) > 0 else ''},{current_probs[1] if len(current_probs) > 1 else ''},{current_probs[2] if len(current_probs) > 2 else ''},{current_kelly[0] if len(current_kelly) > 0 else ''},{current_kelly[1] if len(current_kelly) > 1 else ''},{current_kelly[2] if len(current_kelly) > 2 else ''}"
                            line_parts.append(current)
                            
                            # 历史变化
                            history = []
                            # 欧赔历史数据，处理多种可能的键名
                            if 'odds_history' in company_data and company_data['odds_history']:
                                for h in company_data['odds_history']:
                                    history_item = f"[{h.get('win_odds', '')},{h.get('draw_odds', '')},{h.get('lose_odds', '')},{h.get('return_rate', '')},{h.get('update_time', '')},{h.get('win_change', '')},{h.get('draw_change', '')},{h.get('lose_change', '')}]"
                                    history.append(history_item)
                            # 向上查找历史数据：在原始公司名下查找
                            elif 'original_company_name' in company_data and company_data['original_company_name'] in data:
                                original_data = data[company_data['original_company_name']]
                                if 'odds_history' in original_data:
                                    for h in original_data['odds_history']:
                                        history_item = f"[{h.get('win_odds', '')},{h.get('draw_odds', '')},{h.get('lose_odds', '')},{h.get('return_rate', '')},{h.get('update_time', '')},{h.get('win_change', '')},{h.get('draw_change', '')},{h.get('lose_change', '')}]"
                                        history.append(history_item)
                            # 尝试在原始数据中查找替换后的公司名
                            elif company in data and 'odds_history' in data[company]:
                                for h in data[company]['odds_history']:
                                    history_item = f"[{h.get('win_odds', '')},{h.get('draw_odds', '')},{h.get('lose_odds', '')},{h.get('return_rate', '')},{h.get('update_time', '')},{h.get('win_change', '')},{h.get('draw_change', '')},{h.get('lose_change', '')}]"
                                    history.append(history_item)
                            line_parts.append(",".join(history))
                        
                        elif 'size_odds' in json_file:
                            # 初盘数据 - 注意size_odds的结构
                            initial_size = company_data.get('initial_size', {})
                            initial = f"{initial_size.get('size', '')},{initial_size.get('over', '')},{initial_size.get('under', '')},{initial_size.get('update_time', '')}"
                            line_parts.append(initial)
                            
                            # 即时盘数据
                            current_size = company_data.get('current_size', {})
                            current = f"{current_size.get('size', '')},{current_size.get('over', '')},{current_size.get('under', '')},{current_size.get('update_time', '')}"
                            line_parts.append(current)
                            
                            # 历史变化
                            history = []
                            # 大小球历史数据，处理多种可能的键名
                            if 'size_history' in company_data and company_data['size_history']:
                                for h in company_data['size_history']:
                                    history_item = f"[{h.get('size', '')},{h.get('over_odds', '')},{h.get('under_odds', '')},{h.get('update_time', '')}]"
                                    history.append(history_item)
                            # 向上查找历史数据：在原始公司名下查找
                            elif 'original_company_name' in company_data and company_data['original_company_name'] in data:
                                original_data = data[company_data['original_company_name']]
                                if 'size_history' in original_data:
                                    for h in original_data['size_history']:
                                        history_item = f"[{h.get('size', '')},{h.get('over_odds', '')},{h.get('under_odds', '')},{h.get('update_time', '')}]"
                                        history.append(history_item)
                            # 尝试在原始数据中查找替换后的公司名
                            elif company in data and 'size_history' in data[company]:
                                for h in data[company]['size_history']:
                                    history_item = f"[{h.get('size', '')},{h.get('over_odds', '')},{h.get('under_odds', '')},{h.get('update_time', '')}]"
                                    history.append(history_item)
                            line_parts.append(",".join(history))
                        
                        # kelly_history 数据已在前面特殊处理
                        
                        # 使用竖线(|)作为主要分隔符将所有部分连接起来
                        f.write("|".join(line_parts) + "\n")                
                files_converted += 1
                
                # 成功转换为txt格式后，删除原JSON文件
                try:
                    os.remove(json_path)
                    files_deleted += 1
                    # 只打印每5个文件一次日志，减少输出
                    if files_deleted % 5 == 0:
                        print(f"已删除 {files_deleted} 个原JSON文件")
                except Exception as e:
                    print(f"删除文件 {json_path} 时出错: {str(e)}")
                
                # 只打印每5个文件一次日志，减少输出
                if files_converted % 5 == 0:
                    print(f"已转换 {files_converted}/{files_processed} 个文件")
            
            except Exception as e:
                print(f"处理文件 {json_path} 时出错: {str(e)}")
                traceback.print_exc()  # 添加这行以打印详细的错误堆栈
    
    print(f"数据转换完成: 处理了 {files_processed} 个文件, 转换了 {files_converted} 个文件, 删除了 {files_deleted} 个原JSON文件")
    print(f"数据已转换为易读的TXT格式，并删除了原JSON文件，读取时可大幅提高速度并增强可读性")
    
    return files_converted > 0

def main():
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='爬取足球比赛赔率数据')
    parser.add_argument('-d', '--date', help='指定日期 (格式: YYYY-MM-DD)', default=datetime.now().strftime('%Y-%m-%d'))
    parser.add_argument('--keep-html', action='store_true', help='保留临时HTML文件')
    parser.add_argument('-m', '--match', help='只处理指定的比赛编号 (例如: 周四001)')
    parser.add_argument('-start', help='指定开始的比赛编号 (例如: 周日001)')
    parser.add_argument('-end', help='指定结束的比赛编号 (例如: 周日003)')
    parser.add_argument('-t', '--threads', type=int, help='设置线程数 (默认: 4)', default=4)
    parser.add_argument('--no-compact', action='store_true', help='不生成紧凑格式文件')
    args = parser.parse_args()
    
    # 使用指定日期或当前日期
    target_date = args.date
    keep_html = args.keep_html
    target_match = args.match
    start_match = args.start
    end_match = args.end
    max_threads = args.threads
    no_compact = args.no_compact
    
    # 创建data目录
    if not os.path.exists('data'):
        os.makedirs('data')
    
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
        
        # 创建临时目录结构（防止线程竞争创建目录）
        temp_odds_dir = os.path.join('data', target_date, 'temp_ou_odds')
        temp_size_dir = os.path.join('data', target_date, 'temp_size_odds')
        temp_asian_dir = os.path.join('data', target_date, 'temp_asian_odds')
        temp_bifa_dir = os.path.join('data', target_date, 'temp_bifa_data')
        temp_kelly_dir = os.path.join('data', target_date, 'temp_kelly_history')
        
        os.makedirs(temp_odds_dir, exist_ok=True)
        os.makedirs(temp_size_dir, exist_ok=True)
        os.makedirs(temp_asian_dir, exist_ok=True)
        os.makedirs(temp_bifa_dir, exist_ok=True)
        os.makedirs(temp_kelly_dir, exist_ok=True)
        
        # 为每场比赛创建单独的文件夹
        for match in matches:
            match_id = match.get('match_id')
            if match_id:
                match_dir = os.path.join('data', target_date, match_id)
                os.makedirs(match_dir, exist_ok=True)

        successful_matches = 0
        failed_matches = 0
        
        # 使用线程池处理所有比赛
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            # 提交所有任务
            future_to_match = {
                executor.submit(debug_match, match['fixture_id'], match['match_id'], target_date): match 
                for match in matches if 'fixture_id' in match
            }
            
            try:
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
                            size_file_path = os.path.join('data', target_date, match['match_id'], 'size_odds.json')
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
            except KeyboardInterrupt:
                print("\n程序被用户中断，正在取消剩余任务...")
                # 取消所有未完成的任务
                for future in future_to_match:
                    if not future.done():
                        future.cancel()
                print("已取消所有未完成的任务，正在进行清理操作...")
        
        print(f"所有比赛处理完成: 成功 {successful_matches} 场, 失败 {failed_matches} 场")
        
        # 如果不需要保留HTML文件，则清理
        if not keep_html:
            clean_temp_html_files(target_date)
        
        # 在所有处理完成后，将让球值添加到main.json文件中
        # add_handicap_to_main_json(target_date)
        
        # 删除竞彩官方数据
        remove_jingcai_data(target_date)
        
        # 转换为紧凑格式（不包括必发数据）
        if not no_compact:
            convert_json_to_compact(target_date)
            print("已生成紧凑格式文件，后续分析时使用JSON格式（必发数据）和TXT格式（其他数据）可大幅提高读取速度")
                
    else:
        print(f"未获取到 {target_date} 的比赛数据")

def generate_odds_script(date):
    # 创建ou_odds文件夹
    odds_dir = os.path.join('data', date, 'ou_odds')
    os.makedirs(odds_dir, exist_ok=True)

    # 示例赔率数据
    odds_data = {
        "威廉希尔": {
            "initial_odds": [2.0, 3.0, 4.0],
            "current_odds": [2.1, 3.1, 4.1],
            "initial_probabilities": [0.5, 0.3, 0.2],
            "current_probabilities": [0.52, 0.28, 0.2],
            "initial_return_rate": 0.9,
            "current_return_rate": 0.92,
            "initial_kelly": [0.9, 0.8, 0.7],
            "current_kelly": [0.92, 0.82, 0.72]
        }
        # 可以添加更多公司的赔率数据
    }

    # 保存赔率数据到JSON文件
    file_path = os.path.join(odds_dir, f'{date}_odds.json')
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(odds_data, f, ensure_ascii=False, indent=2)
    print(f"赔率数据已保存到: {file_path}")

def parse_odds_history(html_content, fixture_id, date):
    """解析HTML中的赔率历史变化URL并获取数据"""
    print("开始解析赔率历史变化...")
    
    soup = BeautifulSoup(html_content, 'html.parser')
    odds_history_data = {}
    
    try:
        # 查找所有赔率公司行
        company_rows = soup.select('tr[id][ttl="zy"]')
        
        for row in company_rows:
            try:
                # 获取公司名称
                company_name_elem = row.select_one('td.tb_plgs span.quancheng')
                if not company_name_elem:
                    continue
                    
                company_name = company_name_elem.text.strip()
                company_id = None
                
                # 尝试获取公司ID
                company_link = row.select_one('td.tb_plgs a')
                if company_link and company_link.get('href'):
                    href = company_link.get('href')
                    if 'cid=' in href:
                        company_id = href.split('cid=')[1].split('&')[0] if '&' in href.split('cid=')[1] else href.split('cid=')[1]
                        print(f"从链接获取到 {company_name} 的公司ID: {company_id}")
                
                if not company_id:
                    # 尝试从tr的cid属性获取
                    cid_attr = row.get('cid')
                    if cid_attr:
                        company_id = cid_attr
                        print(f"从tr标签的cid属性获取到 {company_name} 的公司ID: {company_id}")
                
                if not company_id:
                    # 尝试从复选框ID获取
                    checkbox = row.select_one('input[type="checkbox"]')
                    if checkbox and checkbox.get('value'):
                        company_id = checkbox.get('value')
                        print(f"从复选框value获取到 {company_name} 的公司ID: {company_id}")
                    elif checkbox and checkbox.get('id'):
                        checkbox_id = checkbox.get('id')
                        if checkbox_id.startswith('ck'):
                            company_id = checkbox_id[2:]
                            print(f"从复选框id获取到 {company_name} 的公司ID: {company_id}")
                
                if company_id:
                    # 构建历史赔率URL
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    timestamp = int(time.time() * 1000)  # 当前毫秒时间戳
                    encoded_time = current_time.replace(' ', '+').replace(':', '%3A')
                    history_url = f"https://odds.500.com/fenxi1/json/ouzhi.php?_={timestamp}&fid={fixture_id}&cid={company_id}&r=1&time={encoded_time}&type=europe"
                    
                    print(f"尝试获取 {company_name} 的历史赔率数据: {history_url}")
                    
                    # 设置请求头
                    headers = {
                        'User-Agent': f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(80, 110)}.0.{random.randint(1000, 9999)}.{random.randint(10, 999)} Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                        'Referer': f'https://odds.500.com/fenxi/yazhi-{fixture_id}.shtml',
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                    
                    max_data_retries = 2  # 数据为空时的最大重试次数
                    
                    for data_retry in range(max_data_retries + 1):
                        try:
                            # 添加随机延迟避免被限制
                            time.sleep(random.uniform(0.5, 1.5))
                            
                            # 使用重试机制发送请求
                            response = make_request_with_retry(history_url, headers)
                            
                            if response and response.status_code == 200:
                                # 检查响应是否为空
                                if not response.text or response.text.strip() == '[]' or response.text.strip() == '{}':
                                    if data_retry < max_data_retries:
                                        print(f"响应数据为空，进行第 {data_retry+1} 次重试...")
                                        time.sleep(2 * (data_retry + 1))
                                        continue
                                    else:
                                        print(f"历史数据重试耗尽，未获取到 {company_name} 的历史数据")
                                        break
                                
                                # 解析JSON响应
                                try:
                                    history_data = response.json()
                                    if history_data:
                                        # 解析历史数据, 格式为 [[胜, 平, 负, 返还率, 时间, 胜变化, 平变化, 负变化], ...]
                                        parsed_history = []
                                        for item in history_data:
                                            if len(item) >= 8:
                                                history_item = {
                                                    'win_odds': float(item[0]),
                                                    'draw_odds': float(item[1]),
                                                    'lose_odds': float(item[2]),
                                                    'return_rate': float(item[3]),
                                                    'update_time': item[4],
                                                    'win_change': int(item[5]),  # 1:上升, 0:不变, -1:下降
                                                    'draw_change': int(item[6]),
                                                    'lose_change': int(item[7])
                                                }
                                                parsed_history.append(history_item)
                                        
                                        if parsed_history:
                                            odds_history_data[company_name] = parsed_history
                                            print(f"成功获取 {company_name} 的历史赔率数据, 共 {len(parsed_history)} 条记录")
                                            break  # 成功获取数据，跳出重试循环
                                        elif data_retry < max_data_retries:
                                            print(f"未解析到有效历史记录，进行第 {data_retry+1} 次重试...")
                                            time.sleep(2 * (data_retry + 1))
                                            continue
                                        else:
                                            print(f"未获取到 {company_name} 的有效历史赔率数据")
                                    elif data_retry < max_data_retries:
                                        print(f"响应数据无效，进行第 {data_retry+1} 次重试...")
                                        time.sleep(2 * (data_retry + 1))
                                        continue
                                    else:
                                        print(f"未获取到 {company_name} 的有效历史赔率数据")
                                except Exception as e:
                                    print(f"解析 {company_name} 历史赔率JSON响应时出错: {str(e)}")
                                    if data_retry < max_data_retries:
                                        print(f"解析错误，进行第 {data_retry+1} 次重试...")
                                        time.sleep(2 * (data_retry + 1))
                                        continue
                            elif data_retry < max_data_retries:
                                print(f"请求失败，进行第 {data_retry+1} 次重试...")
                                time.sleep(2 * (data_retry + 1))
                                continue
                            else:
                                print(f"请求 {company_name} 历史赔率失败")
                        
                        except Exception as e:
                            print(f"获取 {company_name} 历史赔率时出错: {str(e)}")
                            if data_retry < max_data_retries:
                                print(f"发生异常，进行第 {data_retry+1} 次重试...")
                                time.sleep(2 * (data_retry + 1))
                                continue
                else:
                    print(f"未能获取 {company_name} 的公司ID")
            
            except Exception as e:
                print(f"解析公司行时出错: {str(e)}")
                continue
    
    except Exception as e:
        print(f"解析历史赔率数据时出错: {str(e)}")
    
    return odds_history_data

def parse_size_history(html_content, fixture_id):
    """解析大小球历史变化数据"""
    print("开始解析大小球历史变化数据...")
    
    soup = BeautifulSoup(html_content, 'html.parser')
    size_history_data = {}
    
    try:
        # 查找所有大小球公司行
        company_rows = soup.select('tr[class*="tr"][id]')
        if not company_rows:
            company_rows = soup.select('tr.tableline')
        if not company_rows:
            company_rows = soup.select('tr[class*="line"]')
        
        print(f"找到 {len(company_rows)} 个公司行")
        
        for row in company_rows:
            try:
                # 获取公司名称
                company_name_elem = row.select_one('td.tb_plgs')
                company_name = "未知公司"
                
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
                    if first_td and first_td.text.strip() and len(first_td.text.strip()) < 30:
                        company_name = first_td.text.strip()
                
                print(f"处理公司: {company_name}")
                
                # 获取公司ID
                company_id = None
                
                # 尝试从行ID获取
                row_id = row.get('id')
                if row_id and row_id.startswith('tr'):
                    company_id = row_id[2:]
                
                # 尝试从链接中获取
                if not company_id:
                    company_link = row.select_one('a[href*="id="]')
                    if company_link and company_link.get('href'):
                        href = company_link.get('href')
                        if 'id=' in href:
                            company_id = href.split('id=')[1].split('&')[0] if '&' in href.split('id=')[1] else href.split('id=')[1]
                
                # 尝试从复选框ID获取
                if not company_id:
                    checkbox = row.select_one('input[type="checkbox"]')
                    if checkbox and checkbox.get('id'):
                        checkbox_id = checkbox.get('id')
                        if checkbox_id.startswith('ck'):
                            company_id = checkbox_id[2:]
                
                if company_id:
                    # 构建历史大小球数据URL
                    timestamp = int(time.time() * 1000)  # 当前毫秒时间戳
                    history_url = f"https://odds.500.com/fenxi1/inc/daxiaoajax.php?fid={fixture_id}&id={company_id}&t={timestamp}"
                    
                    print(f"尝试获取 {company_name} 的历史大小球数据: {history_url}")
                    
                    # 设置请求头
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept': 'application/json, text/javascript, */*; q=0.01',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                        'Referer': f'https://odds.500.com/fenxi/daxiao-{fixture_id}.shtml',
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                    
                    try:
                        # 添加随机延迟避免被限制
                        time.sleep(random.uniform(0.5, 1.5))
                        
                        # 发送请求获取历史数据
                        response = requests.get(history_url, headers=headers, timeout=10)
                        
                        if response.status_code == 200:
                            # 解析JSON响应
                            try:
                                history_data = response.json()
                                if history_data and isinstance(history_data, list):
                                    # 解析历史数据，格式为 ["<tr><td class='tips_down'>0.88</td><td class=''>3/3.5</td><td class='tips_up'>0.92</td><td class=''>04-03 13:06</td></tr>", ...]
                                    parsed_history = []
                                    
                                    for html_item in history_data:
                                        try:
                                            # 解析HTML片段
                                            item_soup = BeautifulSoup(html_item, 'html.parser')
                                            cells = item_soup.select('td')
                                            
                                            if len(cells) >= 4:
                                                # 判断是否有上升下降指示
                                                over_cell_class = cells[0].get('class', [])
                                                over_change = 0  # 默认不变
                                                if 'tips_up' in over_cell_class:
                                                    over_change = 1  # 上升
                                                elif 'tips_down' in over_cell_class:
                                                    over_change = -1  # 下降
                                                
                                                under_cell_class = cells[2].get('class', [])
                                                under_change = 0  # 默认不变
                                                if 'tips_up' in under_cell_class:
                                                    under_change = 1  # 上升
                                                elif 'tips_down' in under_cell_class:
                                                    under_change = -1  # 下降
                                                
                                                # 解析数据
                                                over_odds = cells[0].text.strip()
                                                size_value = cells[1].text.strip()
                                                under_odds = cells[2].text.strip()
                                                update_time = cells[3].text.strip()
                                                
                                                history_item = {
                                                    'over_odds': float(over_odds),
                                                    'size': size_value,
                                                    'under_odds': float(under_odds),
                                                    'update_time': update_time,
                                                    'over_change': over_change,
                                                    'under_change': under_change
                                                }
                                                parsed_history.append(history_item)
                                        except Exception as e:
                                            print(f"解析单条历史记录时出错: {str(e)}")
                                            continue
                                    
                                    if parsed_history:
                                        size_history_data[company_name] = parsed_history
                                        print(f"成功获取 {company_name} 的历史大小球数据, 共 {len(parsed_history)} 条记录")
                                    else:
                                        print(f"未解析到 {company_name} 的有效历史大小球数据记录")
                                else:
                                    print(f"未获取到 {company_name} 的有效历史大小球数据, 响应: {response.text[:100]}")
                            except Exception as e:
                                print(f"解析 {company_name} 历史大小球JSON响应时出错: {str(e)}")
                        else:
                            print(f"请求 {company_name} 历史大小球数据失败, 状态码: {response.status_code}")
                    
                    except Exception as e:
                        print(f"获取 {company_name} 历史大小球数据时出错: {str(e)}")
                        continue
                else:
                    print(f"未能获取 {company_name} 的公司ID，无法请求历史数据")
            
            except Exception as e:
                print(f"解析公司行时出错: {str(e)}")
                continue
    
    except Exception as e:
        print(f"解析历史大小球数据时出错: {str(e)}")
    
    return size_history_data

def parse_handicap_history(html_content, fixture_id):
    """解析让球历史赔率变化数据"""
    print("开始解析让球历史变化数据...")
    
    soup = BeautifulSoup(html_content, 'html.parser')
    handicap_history_data = {}
    
    try:
        # 查找所有让球赔率公司行
        company_rows = soup.select('tr[id][ttl="zy"]')
        
        if not company_rows:
            print("未找到让球赔率行数据")
            return handicap_history_data
        
        print(f"找到 {len(company_rows)} 个让球公司行")
        
        for row in company_rows:
            try:
                # 获取公司名称
                company_name_elem = row.select_one('td.tb_plgs span.quancheng')
                if not company_name_elem:
                    continue
                    
                company_name = company_name_elem.text.strip()
                company_id = None
                
                # 获取让球值
                handicap_value = ""
                handicap_td = row.select_one('td[row="1"]:nth-of-type(3)')
                if handicap_td:
                    handicap_value = handicap_td.text.strip()
                    print(f"找到让球值: {handicap_value}")
                else:
                    print(f"警告: 未找到 {company_name} 的让球值")
                
                # 尝试获取公司ID
                company_link = row.select_one('td.tb_plgs a')
                if company_link and company_link.get('href'):
                    href = company_link.get('href')
                    if 'cid=' in href:
                        company_id = href.split('cid=')[1].split('&')[0] if '&' in href.split('cid=')[1] else href.split('cid=')[1]
                        print(f"从链接获取到 {company_name} 的公司ID: {company_id}")
                
                if not company_id:
                    # 尝试从tr的cid属性获取
                    cid_attr = row.get('cid')
                    if cid_attr:
                        company_id = cid_attr
                        print(f"从tr标签的cid属性获取到 {company_name} 的公司ID: {company_id}")
                
                if not company_id:
                    # 尝试从复选框ID获取
                    checkbox = row.select_one('input[type="checkbox"]')
                    if checkbox and checkbox.get('value'):
                        company_id = checkbox.get('value')
                        print(f"从复选框value获取到 {company_name} 的公司ID: {company_id}")
                    elif checkbox and checkbox.get('id'):
                        checkbox_id = checkbox.get('id')
                        if checkbox_id.startswith('ck'):
                            company_id = checkbox_id[2:]
                            print(f"从复选框id获取到 {company_name} 的公司ID: {company_id}")
                
                if company_id:
                    # 构建历史让球赔率URL
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    timestamp = int(time.time() * 1000)  # 当前毫秒时间戳
                    encoded_time = current_time.replace(' ', '+').replace(':', '%3A')
                    
                    # 处理让球值，确保格式正确
                    handicap_param = handicap_value.replace('+', '%2B') if handicap_value else "-1"
                    
                    # 尝试替换特殊字符格式
                    if handicap_value == "-1":
                        handicap_param = "-1"
                    elif handicap_value == "+1":
                        handicap_param = "%2B1"
                    elif handicap_value == "-1.5":
                        handicap_param = "-1.5"
                    elif handicap_value == "+1.5":
                        handicap_param = "%2B1.5"
                    
                    print(f"处理后的让球参数值: {handicap_param}")
                    
                    history_url = f"https://odds.500.com/fenxi1/json/rspf.php?_={timestamp}&fid={fixture_id}&cid={company_id}&r=1&time={encoded_time}&handicapline={handicap_param}&type=rspf"
                    
                    print(f"尝试获取 {company_name} 的历史让球赔率数据: {history_url}")
                    
                    # 设置请求头
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept': 'application/json, text/javascript, */*; q=0.01',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                        'Referer': f'https://odds.500.com/fenxi/rangqiu-{fixture_id}.shtml',
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                    
                    try:
                        # 添加随机延迟避免被限制
                        time.sleep(random.uniform(0.5, 1.5))
                        
                        # 发送请求获取历史数据
                        response = requests.get(history_url, headers=headers, timeout=10)
                        
                        if response.status_code == 200:
                            print(f"请求成功，响应内容: {response.text[:200]}")
                            # 解析JSON响应
                            try:
                                history_data = response.json()
                                if history_data:
                                    # 解析历史数据, 格式为 [[主胜, 平, 客胜, 返还率, 时间, 主胜变化, 平变化, 客胜变化], ...]
                                    parsed_history = []
                                    for item in history_data:
                                        if len(item) >= 8:
                                            history_item = {
                                                'home_odds': float(item[0]),
                                                'draw_odds': float(item[1]),
                                                'away_odds': float(item[2]),
                                                'return_rate': float(item[3]),
                                                'update_time': item[4],
                                                'home_change': int(item[5]),  # 1:上升, 0:不变, -1:下降
                                                'draw_change': int(item[6]),
                                                'away_change': int(item[7])
                                            }
                                            parsed_history.append(history_item)
                                    
                                    # 初始化公司数据(如果不存在)
                                    if company_name not in handicap_history_data:
                                        handicap_history_data[company_name] = {}
                                    
                                    handicap_history_data[company_name][handicap_value] = parsed_history
                                    print(f"成功获取 {company_name} 的历史让球赔率数据 (让球值: {handicap_value}), 共 {len(parsed_history)} 条记录")
                                else:
                                    print(f"未获取到 {company_name} 的有效历史让球赔率数据，响应内容为空")
                            except Exception as e:
                                print(f"解析JSON响应时出错: {str(e)}, 响应内容: {response.text[:200]}")
                        else:
                            print(f"请求 {company_name} 历史让球赔率失败, 状态码: {response.status_code}")
                    
                    except Exception as e:
                        print(f"获取 {company_name} 历史让球赔率时出错: {str(e)}")
                        continue
                else:
                    print(f"未能获取 {company_name} 的公司ID")
            
            except Exception as e:
                print(f"解析公司行时出错: {str(e)}")
                continue
    
    except Exception as e:
        print(f"解析历史让球赔率数据时出错: {str(e)}")
    
    return handicap_history_data

def parse_kelly_history(html_content, fixture_id):
    """解析凯利指数历史变化数据"""
    print("开始解析凯利指数历史变化数据...")
    
    soup = BeautifulSoup(html_content, 'html.parser')
    kelly_history_data = {}
    
    try:
        # 查找所有欧赔公司行
        company_rows = soup.select('tr[id][ttl="zy"]')
        if not company_rows:
            print("未找到欧赔公司行，尝试其他选择器")
            company_rows = soup.select('tr.tableline')
            if not company_rows:
                company_rows = soup.select('tr[class*="tr"][id]')
                if not company_rows:
                    company_rows = soup.select('tr[id]')
        
        if not company_rows:
            print("未找到任何欧赔公司行，无法获取凯利指数历史数据")
            return kelly_history_data
        
        print(f"找到 {len(company_rows)} 个欧赔公司行")
        
        for row in company_rows:
            try:
                # 获取公司名称
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
                
                # 使用replace_company_names函数转换为完整名称
                company_name = replace_company_names(company_name)
                
                print(f"处理公司凯利指数历史数据: {company_name}")
                
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
                    # 获取当前时间作为初始查询时间
                    current_time = datetime.now().strftime('%Y-%m-%d+%H%%3A%M%%3A%S')
                    
                    # 构建凯利指数历史数据URL
                    timestamp = int(time.time() * 1000)  # 当前毫秒时间戳
                    kelly_history_url = f"https://odds.500.com/fenxi1/json/ouzhi.php?_={timestamp}&fid={fixture_id}&cid={company_id}&r=1&time={current_time}&type=kelly"
                    
                    print(f"尝试获取 {company_name} 的凯利指数历史数据: {kelly_history_url}")
                    
                    # 设置请求头
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept': 'application/json, text/javascript, */*; q=0.01',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                        'Referer': f'https://odds.500.com/fenxi/ouzhi-{fixture_id}.shtml',
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                    
                    try:
                        # 添加随机延迟避免被限制
                        time.sleep(random.uniform(0.5, 1.5))
                        
                        # 发送请求获取历史数据
                        response = requests.get(kelly_history_url, headers=headers, timeout=10)
                        
                        if response.status_code == 200:
                            print(f"请求凯利指数历史数据成功，响应长度: {len(response.text)}")
                            
                            # 解析JSON响应
                            try:
                                # 尝试解析JSON
                                try:
                                    history_data = response.json()
                                except:
                                    print(f"响应不是有效的JSON，尝试手动解析")
                                    history_data = response.text.replace('\n', '').replace('\r', '')
                                    if history_data.startswith('[') and history_data.endswith(']'):
                                        # 手动解析类JSON格式
                                        history_data = eval(history_data)
                                
                                if history_data and isinstance(history_data, list):
                                    # 将每条记录构造为[凯胜, 凯平, 凯负, 更新时间]的格式
                                    parsed_history = []
                                    
                                    for item in history_data:
                                        if len(item) >= 4:
                                            kelly_item = {
                                                'kelly_win': float(item[0]),
                                                'kelly_draw': float(item[1]),
                                                'kelly_lose': float(item[2]),
                                                'update_time': item[3]
                                            }
                                            parsed_history.append(kelly_item)
                                    
                                    if parsed_history:
                                        kelly_history_data[company_name] = parsed_history
                                        print(f"成功获取 {company_name} 的凯利指数历史数据, 共 {len(parsed_history)} 条记录")
                                    else:
                                        print(f"未解析到 {company_name} 的有效凯利指数历史数据记录")
                                else:
                                    print(f"未获取到 {company_name} 的有效凯利指数历史数据, 响应类型: {type(history_data)}")
                            except Exception as e:
                                print(f"解析 {company_name} 凯利指数历史JSON响应时出错: {str(e)}")
                        else:
                            print(f"请求 {company_name} 凯利指数历史数据失败, 状态码: {response.status_code}")
                    
                    except Exception as e:
                        print(f"获取 {company_name} 凯利指数历史数据时出错: {str(e)}")
                        continue
                else:
                    print(f"未能获取 {company_name} 的公司ID，无法请求凯利指数历史数据")
            
            except Exception as e:
                print(f"解析公司行时出错: {str(e)}")
                continue
    
    except Exception as e:
        print(f"解析凯利指数历史数据时出错: {str(e)}")
    
    return kelly_history_data

# 添加新的解析必发交易数据的函数
def parse_bifa_data(html_content):
    """解析必发交易数据页面"""
    soup = BeautifulSoup(html_content, 'html.parser')
    bifa_data = {
        "hot_analysis": {}, # 热度分析
        "trade_analysis": {}, # 交易分析
        "big_trade": {}, # 必发大额交易
        "trade_details": [] # 交易明细
    }

    # 检查页面是否包含必发交易数据
    has_bifa_data = False
    
    # 首先检查是否有旧版的必发交易数据结构
    if soup.select_one('div.danchangtouzhu') or soup.select_one('div.bf-analyse-data') or \
       soup.select_one('div.bigeye-data') or soup.select_one('table.bf-table'):
        has_bifa_data = True
    
    # 检查新版的必发交易数据结构
    if soup.select_one('div.M_box.record') or soup.select_one('div.czxl-tb') or \
       soup.select_one('table.bif-yab'):
        has_bifa_data = True

    if not has_bifa_data:
        print("警告：未在页面中找到必发交易数据结构，可能该比赛没有必发交易数据")
        bifa_data["no_data_reason"] = "页面中不存在必发交易数据结构"
        return bifa_data

    try:
        # 1. 尝试解析新版热度分析和交易分析数据（通常在第一个表格中）
        bifa_table = soup.select_one('div.M_box table')
        if bifa_table:
            # 创建热度分析中需要的字段
            teams = ["home", "draw", "away"]
            team_names = {"home": "主胜", "draw": "平局", "away": "客胜"}
            for team in teams:
                bifa_data["hot_analysis"][team] = {
                    "name": team_names[team],
                    "odds": "",
                    "prob": "",
                    "north_single": "",
                    "trade_ratio": "",
                    "trade_price": "",
                    "volume": "",
                    "profit": "",
                    "bifa_index": "",
                    "hot_index": "",
                    "profit_index": ""
                }
            
            # 获取表格行
            rows = bifa_table.select('tr')
            if len(rows) >= 3:  # 至少包含标题行和三个选项行
                # 热度分析数据通常在前三行
                try:
                    # 获取每行的单元格
                    for row_idx, row in enumerate(rows[1:4]):  # 跳过标题行，处理三个选项行
                        cells = row.select('td')
                        if len(cells) >= 7:
                            # 找到对应的行（主胜、平局、客胜）
                            team_name = cells[0].text.strip() if cells[0] else ""
                            
                            # 定义标签
                            label = ""
                            if "哈萨克" in team_name or "主" in team_name:
                                label = "home"
                                bifa_data["hot_analysis"]["home"]["name"] = team_name
                            elif "平局" in team_name or "平" in team_name:
                                label = "draw"
                                bifa_data["hot_analysis"]["draw"]["name"] = team_name
                            elif "北马其顿" in team_name or "客" in team_name or row_idx == 2:  # 假设第三行是客胜
                                label = "away"
                                bifa_data["hot_analysis"]["away"]["name"] = team_name
                            else:
                                continue
                            
                            # 获取赔率和概率数据
                            if len(cells) > 1:
                                odds_text = cells[1].text.strip() if cells[1] else ""
                                if odds_text and not odds_text.startswith("赔率"):
                                    try:
                                        bifa_data["hot_analysis"][label]["odds"] = float(odds_text)
                                    except ValueError:
                                        bifa_data["hot_analysis"][label]["odds"] = odds_text
                            
                            if len(cells) > 1:
                                prob_text = cells[2].text.strip() if cells[2] else ""
                                if prob_text:
                                    bifa_data["hot_analysis"][label]["prob"] = prob_text
                            
                            # 获取北单数据
                            if len(cells) > 2:
                                bd_text = cells[3].text.strip() if cells[3] else ""
                                bifa_data["hot_analysis"][label]["north_single"] = bd_text
                            
                            # 获取交易比例
                            if len(cells) > 3:
                                trade_ratio = cells[4].text.strip() if cells[4] else ""
                                if trade_ratio:
                                    bifa_data["hot_analysis"][label]["trade_ratio"] = trade_ratio
                            
                            # 获取成交价
                            if len(cells) > 4:
                                trade_price = cells[5].text.strip() if cells[5] else ""
                                if trade_price:
                                    try:
                                        bifa_data["hot_analysis"][label]["trade_price"] = float(trade_price)
                                    except ValueError:
                                        bifa_data["hot_analysis"][label]["trade_price"] = trade_price
                            
                            # 获取必发成交量
                            bet_volume = cells[6].text.strip() if len(cells) > 5 else ""
                            if bet_volume:
                                try:
                                    bifa_data["hot_analysis"][label]["volume"] = int(bet_volume.replace(',', ''))
                                except ValueError:
                                    bifa_data["hot_analysis"][label]["volume"] = bet_volume

                            # 获取庄家盈亏
                            profit_loss = cells[7].text.strip() if len(cells) > 6 else ""
                            if profit_loss:
                                try:
                                    bifa_data["hot_analysis"][label]["profit"] = int(profit_loss.replace(',', ''))
                                except ValueError:
                                    bifa_data["hot_analysis"][label]["profit"] = profit_loss
                            
                            # 获取必发指数
                            bifa_index = cells[8].text.strip() if len(cells) > 7 else ""
                            if bifa_index:
                                bifa_data["hot_analysis"][label]["bifa_index"] = bifa_index
                            
                            # 获取冷热指数
                            hot_cold_index = cells[9].text.strip() if len(cells) > 8 else ""
                            if hot_cold_index:
                                try:
                                    bifa_data["hot_analysis"][label]["hot_index"] = int(hot_cold_index) if hot_cold_index != "-" else hot_cold_index
                                except ValueError:
                                    bifa_data["hot_analysis"][label]["hot_index"] = hot_cold_index
                            
                            # 获取盈亏指数
                            profit_index = cells[10].text.strip() if len(cells) > 9 else ""
                            if profit_index:
                                try:
                                    bifa_data["hot_analysis"][label]["profit_index"] = int(profit_index)
                                except ValueError:
                                    bifa_data["hot_analysis"][label]["profit_index"] = profit_index
                    
                    # 特殊处理: 使用交易明细数据，确保正确解析客胜数据
                    for detail in bifa_data["trade_details"]:
                        if "北马其顿" in detail["type"] or "客" in detail["type"]:
                            if detail["action"] and not bifa_data["hot_analysis"]["away"]["odds"]:
                                try:
                                    bifa_data["hot_analysis"]["away"]["odds"] = float(detail["action"])
                                except ValueError:
                                    bifa_data["hot_analysis"]["away"]["odds"] = detail["action"]
                            
                            if detail["amount"] and not bifa_data["hot_analysis"]["away"]["prob"]:
                                bifa_data["hot_analysis"]["away"]["prob"] = detail["amount"]
                            
                            if detail["time"] and not bifa_data["hot_analysis"]["away"]["north_single"]:
                                bifa_data["hot_analysis"]["away"]["north_single"] = detail["time"]
                            
                            if detail["percentage"] and not bifa_data["hot_analysis"]["away"]["trade_ratio"]:
                                bifa_data["hot_analysis"]["away"]["trade_ratio"] = detail["percentage"] + "%"
                                
                    # 解析数据提点（通常在最后几行）
                    data_tips_rows = [row for row in rows if len(row.select('td')) > 1 and '数据提点' in row.text]
                    if data_tips_rows:
                        # 找到数据提点所在行的索引
                        tip_idx = rows.index(data_tips_rows[0])
                        bifa_data["hot_analysis"]["tips"] = []
                        # 获取数据提点后的所有行
                        for row in rows[tip_idx+1:]:
                            tip_text = row.text.strip()
                            if tip_text and not tip_text.startswith('数据提点'):
                                bifa_data["hot_analysis"]["tips"].append(tip_text)
                
                except Exception as e:
                    print(f"解析热度分析数据时出错: {str(e)}")
                    traceback.print_exc()
                
        # 2. 解析必发交易数据
        trade_info_div = soup.select_one('div.czxl-tb.M_content')
        if trade_info_div:
            # 总交易额
            total_trade_text = trade_info_div.select_one('span.czxl-zxl em')
            if total_trade_text:
                try:
                    bifa_data["trade_analysis"]["total_volume"] = int(total_trade_text.text.strip().replace(',', ''))
                except ValueError:
                    bifa_data["trade_analysis"]["total_volume"] = total_trade_text.text.strip()
            
            # 交易明细（主胜、平局、客胜的交易量）
            data_details = trade_info_div.select('div.data-detail li')
            bet_labels = ['home', 'draw', 'away']
            for i, detail in enumerate(data_details):
                if i < len(bet_labels):
                    try:
                        bifa_data["trade_analysis"][f"{bet_labels[i]}_volume"] = int(detail.text.strip().replace(',', ''))
                    except ValueError:
                        bifa_data["trade_analysis"][f"{bet_labels[i]}_volume"] = detail.text.strip()
        
        # 3. 解析必发大额交易数据
        big_trade_div = soup.select('.czxl-tb.M_content')
        if len(big_trade_div) > 1:  # 第二个是大额交易数据
            big_trade_section = big_trade_div[1]
            
            # 总交易额
            total_big_trade_text = big_trade_section.select_one('span.czxl-zxl em')
            if total_big_trade_text:
                try:
                    bifa_data["big_trade"]["total_volume"] = int(total_big_trade_text.text.strip().replace(',', ''))
                except ValueError:
                    bifa_data["big_trade"]["total_volume"] = total_big_trade_text.text.strip()
            
            # 交易明细（主胜、平局、客胜的交易量）
            big_data_details = big_trade_section.select('div.data-detail li')
            bet_labels = ['home', 'draw', 'away']
            for i, detail in enumerate(big_data_details):
                if i < len(bet_labels):
                    try:
                        bifa_data["big_trade"][f"{bet_labels[i]}_volume"] = int(detail.text.strip().replace(',', ''))
                    except ValueError:
                        bifa_data["big_trade"][f"{bet_labels[i]}_volume"] = detail.text.strip()
        
        # 4. 解析交易明细表格（必发大额交易明细）
        # 查找标题包含"必发大额交易明细"的div下的表格
        trade_details_table = None
        trade_details_divs = soup.select('div.M_title')
        for div in trade_details_divs:
            if '必发大额交易明细' in div.text:
                trade_details_table = div.find_next('table', class_='pub_table')
                break
        
        if trade_details_table:
            print("找到必发大额交易明细表格")
            rows = trade_details_table.select('tr')
            # 跳过表头
            for row in rows[1:]:  # 跳过表头行
                cells = row.select('td')
                if len(cells) >= 5:
                    try:
                        detail = {
                            "type": cells[0].text.strip(),  # 综合（主/平/客）
                            "action": cells[1].text.strip(),  # 属性（买/卖）
                            "amount": cells[2].text.strip().replace(',', ''),  # 成交量
                            "time": cells[3].text.strip(),  # 交易时间
                            "percentage": cells[4].text.strip().replace('%', '')  # 交易比例
                        }
                        bifa_data["trade_details"].append(detail)
                    except Exception as e:
                        print(f"解析交易明细行时出错: {str(e)}")
        
        # 5. 解析必发交易量与赔率表格（模拟盈亏 - 第一部分）
        trade_odds_table = soup.select('table.bif-yab.bif-tabr-one')
        if len(trade_odds_table) >= 1:
            rows = trade_odds_table[0].select('tr')
            bet_labels = ['home', 'draw', 'away']
            bet_names = ['主胜', '平局', '客胜']
            
            # 创建一个模拟盈亏数据的字典
            if "simulation" not in bifa_data:
                bifa_data["simulation"] = {
                    "odds": [],
                    "profit": []
                }
            
            for i, row in enumerate(rows[1:4]):  # 跳过表头，取三行数据
                if i < len(bet_labels):
                    cells = row.select('td')
                    if len(cells) >= 3:
                        odds_item = {
                            "type": bet_names[i],
                            "volume": "",
                            "odds": ""
                        }
                        
                        # 交易量
                        volume_text = cells[1].text.strip()
                        try:
                            odds_item["volume"] = int(volume_text.replace(',', ''))
                            bifa_data["trade_analysis"][f"{bet_labels[i]}_volume"] = int(volume_text.replace(',', ''))
                            
                            # 额外更新热度分析中的成交量数据
                            if not bifa_data["hot_analysis"][bet_labels[i]]["volume"]:
                                bifa_data["hot_analysis"][bet_labels[i]]["volume"] = int(volume_text.replace(',', ''))
                        except ValueError:
                            odds_item["volume"] = volume_text
                            bifa_data["trade_analysis"][f"{bet_labels[i]}_volume"] = volume_text
                        
                        # 赔率
                        odds_text = cells[2].text.strip()
                        try:
                            odds_item["odds"] = float(odds_text)
                            bifa_data["trade_analysis"][f"{bet_labels[i]}_odds"] = float(odds_text)
                            
                            # 额外更新热度分析中的赔率数据
                            if not bifa_data["hot_analysis"][bet_labels[i]]["trade_price"]:
                                bifa_data["hot_analysis"][bet_labels[i]]["trade_price"] = float(odds_text)
                        except ValueError:
                            odds_item["odds"] = odds_text
                            bifa_data["trade_analysis"][f"{bet_labels[i]}_odds"] = odds_text
                        
                        bifa_data["simulation"]["odds"].append(odds_item)
        
        # 6. 解析庄家盈亏表格（模拟盈亏 - 第二部分）
        if len(trade_odds_table) >= 2:
            rows = trade_odds_table[1].select('tr')
            bet_labels = ['home', 'draw', 'away']
            bet_names = ['主胜', '平局', '客胜']
            
            for i, row in enumerate(rows[1:4]):  # 跳过表头，取三行数据
                if i < len(bet_labels):
                    cells = row.select('td')
                    if len(cells) >= 3:
                        profit_item = {
                            "type": bet_names[i],
                            "profit": "",
                            "profit_index": ""
                        }
                        
                        # 庄家盈亏
                        profit_text = cells[1].text.strip()
                        try:
                            profit_item["profit"] = int(profit_text.replace(',', ''))
                            bifa_data["trade_analysis"][f"{bet_labels[i]}_profit"] = int(profit_text.replace(',', ''))
                            
                            # 额外更新热度分析中的盈亏数据
                            if not bifa_data["hot_analysis"][bet_labels[i]]["profit"]:
                                bifa_data["hot_analysis"][bet_labels[i]]["profit"] = int(profit_text.replace(',', ''))
                        except ValueError:
                            profit_item["profit"] = profit_text
                            bifa_data["trade_analysis"][f"{bet_labels[i]}_profit"] = profit_text
                        
                        # 盈亏指数
                        index_text = cells[2].text.strip()
                        try:
                            profit_item["profit_index"] = int(index_text)
                            bifa_data["trade_analysis"][f"{bet_labels[i]}_profit_index"] = int(index_text)
                            
                            # 额外更新热度分析中的盈亏指数数据
                            if not bifa_data["hot_analysis"][bet_labels[i]]["profit_index"]:
                                bifa_data["hot_analysis"][bet_labels[i]]["profit_index"] = int(index_text)
                        except ValueError:
                            profit_item["profit_index"] = index_text
                            bifa_data["trade_analysis"][f"{bet_labels[i]}_profit_index"] = index_text
                        
                        bifa_data["simulation"]["profit"].append(profit_item)
        
        # 7. 兼容旧版HTML结构的解析
        # 旧版热度分析
        hot_analysis_section = soup.select_one('div.danchangtouzhu')
        if hot_analysis_section:
            # 获取主队、客队和平局的投注量
            bet_amounts = hot_analysis_section.select('div.chartball span')
            bet_labels = ['home', 'draw', 'away']
            
            for i, amount in enumerate(bet_amounts):
                if i < len(bet_labels):
                    value_text = amount.text.strip().replace(',', '').replace('注', '')
                    try:
                        bifa_data["hot_analysis"][bet_labels[i]]["volume"] = int(value_text)
                    except ValueError:
                        bifa_data["hot_analysis"][bet_labels[i]]["volume"] = 0
            
            # 获取热度指数变化
            heat_index = hot_analysis_section.select_one('div.danzi-value span')
            if heat_index:
                bifa_data["hot_analysis"]["heat_index"] = heat_index.text.strip()
            
            # 获取变化趋势
            trend_elements = hot_analysis_section.select('div.change-item')
            for elem in trend_elements:
                label = elem.select_one('p')
                value = elem.select_one('span')
                if label and value:
                    label_text = label.text.strip()
                    value_text = value.text.strip()
                    
                    if '主' in label_text:
                        bifa_data["hot_analysis"]["home"]["trend"] = value_text
                    elif '平' in label_text:
                        bifa_data["hot_analysis"]["draw"]["trend"] = value_text
                    elif '客' in label_text:
                        bifa_data["hot_analysis"]["away"]["trend"] = value_text

        # 旧版交易分析
        trade_analysis_section = soup.select_one('div.bf-analyse-data')
        if trade_analysis_section:
            data_items = trade_analysis_section.select('div.analyse-data-item')
            for item in data_items:
                label = item.select_one('p')
                value = item.select_one('p.data-value')
                if label and value:
                    label_text = label.text.strip().replace('：', '')
                    value_text = value.text.strip()
                    
                    # 转换为适当的数据类型
                    if '金额' in label_text:
                        try:
                            value_text = value_text.replace(',', '').replace('元', '')
                            bifa_data["trade_analysis"][label_text] = float(value_text)
                        except ValueError:
                            bifa_data["trade_analysis"][label_text] = value_text
                    else:
                        bifa_data["trade_analysis"][label_text] = value_text

        # 旧版必发大额交易
        big_trade_section = soup.select_one('div.bigeye-data')
        if big_trade_section:
            data_items = big_trade_section.select('div.bigeye-data-item')
            for item in data_items:
                label = item.select_one('p.label')
                value = item.select_one('p.value')
                if label and value:
                    label_text = label.text.strip().replace('：', '')
                    value_text = value.text.strip()
                    
                    # 转换为适当的数据类型
                    if '金额' in label_text or '占比' in label_text:
                        try:
                            value_text = value_text.replace(',', '').replace('元', '').replace('%', '')
                            bifa_data["big_trade"][label_text] = float(value_text)
                        except ValueError:
                            bifa_data["big_trade"][label_text] = value_text
                    else:
                        bifa_data["big_trade"][label_text] = value_text

        # 旧版交易明细
        trade_details_table = soup.select_one('table.bf-table')
        if trade_details_table:
            rows = trade_details_table.select('tr:not(.head)')
            for row in rows:
                cells = row.select('td')
                if len(cells) >= 6:
                    try:
                        detail = {
                            "time": cells[0].text.strip(),
                            "amount": cells[1].text.strip().replace(',', ''),
                            "odds": cells[2].text.strip(),
                            "selection": cells[3].text.strip(),
                            "type": cells[4].text.strip(),
                            "status": cells[5].text.strip()
                        }
                        bifa_data["trade_details"].append(detail)
                    except Exception as e:
                        print(f"解析交易明细行时出错: {str(e)}")
    
        # 8. 如果trade_details为空，尝试其他方法找到必发大额交易明细数据
        if len(bifa_data["trade_details"]) == 0:
            print("尝试其他方法查找必发大额交易明细数据...")
            
            # 尝试方法1：使用更宽松的选择器
            try:
                any_trade_table = soup.select_one('table.pub_table')
                if any_trade_table:
                    print("找到一个可能的交易表格")
                    header_row = any_trade_table.select_one('tr')
                    if header_row and '成交量' in header_row.text and '交易时间' in header_row.text and '交易比例' in header_row.text:
                        print("该表格包含交易明细数据")
                        rows = any_trade_table.select('tr')
                        # 跳过表头
                        for row in rows[1:]:  # 跳过表头行
                            cells = row.select('td')
                            if len(cells) >= 5:
                                try:
                                    detail = {
                                        "type": cells[0].text.strip(),  # 综合（主/平/客）
                                        "action": cells[1].text.strip(),  # 属性（买/卖）
                                        "amount": cells[2].text.strip().replace(',', ''),  # 成交量
                                        "time": cells[3].text.strip(),  # 交易时间
                                        "percentage": cells[4].text.strip().replace('%', '')  # 交易比例
                                    }
                                    bifa_data["trade_details"].append(detail)
                                except Exception as e:
                                    print(f"解析交易明细行时出错: {str(e)}")
            except Exception as e:
                print(f"尝试使用宽松选择器查找交易表格时出错: {str(e)}")
            
            # 尝试方法2：使用文本查找方式
            if len(bifa_data["trade_details"]) == 0:
                try:
                    all_tables = soup.select('table.pub_table')
                    for table in all_tables:
                        if '属性' in table.text and '成交量' in table.text and '交易时间' in table.text:
                            print("找到包含交易明细的表格")
                            rows = table.select('tr')
                            # 跳过表头
                            for row in rows[1:]:  # 跳过表头行
                                cells = row.select('td')
                                if len(cells) >= 5:
                                    try:
                                        detail = {
                                            "type": cells[0].text.strip(),  # 综合（主/平/客）
                                            "action": cells[1].text.strip(),  # 属性（买/卖）
                                            "amount": cells[2].text.strip().replace(',', ''),  # 成交量
                                            "time": cells[3].text.strip(),  # 交易时间
                                            "percentage": cells[4].text.strip().replace('%', '')  # 交易比例
                                        }
                                        bifa_data["trade_details"].append(detail)
                                    except Exception as e:
                                        print(f"解析交易明细行时出错: {str(e)}")
                            break
                except Exception as e:
                    print(f"尝试通过文本查找交易表格时出错: {str(e)}")
            
            # 删除原来的big_trade_details相关代码，不再需要这个字段
                
    except Exception as e:
        print(f"解析必发交易数据时出错: {str(e)}")
        traceback.print_exc()  # 添加详细的错误堆栈跟踪
    
    return bifa_data

if __name__ == '__main__':
    # 检查命令行参数
    if len(sys.argv) > 1:
        if sys.argv[1] in ['-d', '--date', '-m', '--match', '-start', '-end', '--keep-html', '-t', '--threads', '--no-compact']:
            main()  # 运行主函数
        else:
            print(f"未知参数: {sys.argv[1]}")
    else:
        # 如果直接运行脚本（没有参数），使用不同的文件名运行测试函数
        test_file = 'test_data'
        test_size_data_write(test_file, '2025-04-01')
        print(f"测试数据已写入 {test_file}.json") 