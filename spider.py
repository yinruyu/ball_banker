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
import logging

# 设置日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('spider.log', 'a', 'utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 添加重试机制的函数
def make_request_with_retry(url, headers, max_retries=3, retry_delay=2, timeout=10):
    """发送请求并在失败时进行重试"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            
            # 处理503错误或其他服务器错误
            if response.status_code >= 500:
                logger.warning(f"服务器错误 (状态码: {response.status_code})，尝试重试 ({attempt+1}/{max_retries})...")
                time.sleep(retry_delay * (attempt + 1))  # 指数退避策略
                continue
                
            # 处理403错误
            if response.status_code == 403:
                logger.warning(f"访问被拒绝 (403 Forbidden)，更换请求头并重试...")
                # 更新User-Agent
                headers['User-Agent'] = f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(80, 110)}.0.{random.randint(1000, 9999)}.{random.randint(10, 999)} Safari/537.36'
                time.sleep(retry_delay * (attempt + 1))
                continue
                
            # 处理其他HTTP错误
            if response.status_code != 200:
                logger.warning(f"请求失败，状态码: {response.status_code}，尝试重试 ({attempt+1}/{max_retries})...")
                time.sleep(retry_delay * (attempt + 1))
                continue
            
            # 检查响应内容是否为空
            if not response.text.strip():
                logger.warning(f"响应内容为空，尝试重试 ({attempt+1}/{max_retries})...")
                time.sleep(retry_delay * (attempt + 1))
                continue
                
            # 响应成功且有内容
            return response
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"请求异常: {str(e)}，尝试重试 ({attempt+1}/{max_retries})...")
            time.sleep(retry_delay * (attempt + 1))
    
    # 所有重试都失败，返回None
    logger.error(f"请求失败，已达到最大重试次数: {max_retries}")
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
    # 创建欧赔文件夹
    odds_dir = os.path.join('data', date, 'ou_odds')
    os.makedirs(odds_dir, exist_ok=True)
    
    # 创建大小球文件夹
    size_dir = os.path.join('data', date, 'size_odds')
    os.makedirs(size_dir, exist_ok=True)
    
    # 创建让球文件夹
    # handicap_dir = os.path.join('data', date, 'handicap_odds')
    # os.makedirs(handicap_dir, exist_ok=True)
    
    # 创建亚盘文件夹
    asian_dir = os.path.join('data', date, 'asian_odds')
    os.makedirs(asian_dir, exist_ok=True)
    
    # 创建凯利指数历史文件夹
    kelly_dir = os.path.join('data', date, 'kelly_history')
    os.makedirs(kelly_dir, exist_ok=True)
    
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
                    
                    # 获取凯利指数历史数据
                    kelly_history = parse_kelly_history(html_content, fixture_id)
                    
                    # 保存凯利指数历史数据到单独的文件
                    if kelly_history:
                        kelly_file_path = os.path.join(kelly_dir, f'{match_id}.json')
                        with open(kelly_file_path, 'w', encoding='utf-8') as f:
                            json.dump(kelly_history, f, ensure_ascii=False, indent=2)
                        print(f"[{match_id}] 凯利指数历史数据已保存到: {kelly_file_path}")
                
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
                # temp_handicap_html_path = os.path.join(handicap_dir, f'temp_{match_id}.html')
                # with open(temp_handicap_html_path, 'w', encoding='utf-8') as f:
                #     f.write(response.text)
                
                # # 解析让球HTML内容
                # with open(temp_handicap_html_path, 'r', encoding='utf-8') as f:
                #     handicap_html_content = f.read()
                #     handicap_data = parse_handicap_data(handicap_html_content)
                    
                #     # 获取让球历史赔率变化数据
                #     handicap_history = parse_handicap_history(handicap_html_content, fixture_id)
                    
                #     # 将历史赔率数据添加到让球数据中
                #     if handicap_history:
                #         for company_name, handicap_values in handicap_history.items():
                #             if company_name in handicap_data:
                #                 for handicap_value, history_data in handicap_values.items():
                #                     # 查找对应让球值的数据
                #                     for handicap_item in handicap_data[company_name]['handicap_list']:
                #                         if handicap_item['handicap'] == handicap_value:
                #                             handicap_item['handicap_history'] = history_data
                #                             break
                
                # # 保存让球数据
                # handicap_file_path = os.path.join(handicap_dir, f'{match_id}.json')
                # with open(handicap_file_path, 'w', encoding='utf-8') as f:
                #     json.dump(handicap_data, f, ensure_ascii=False, indent=2)
                
                # if handicap_data:
                success_count += 1
                # else:
                #     print(f"[{match_id}] 警告：未解析到让球数据")
                #     error_count += 1
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
    # handicap_dir = os.path.join('data', date, 'handicap_odds')
    # if os.path.exists(handicap_dir):
    #     for file in os.listdir(handicap_dir):
    #         if file.startswith('temp_') and file.endswith('.html'):
    #             file_path = os.path.join(handicap_dir, file)
    #             try:
    #                 os.remove(file_path)
    #                 print(f"已删除让球临时文件: {file_path}")
    #             except Exception as e:
    #                 print(f"删除文件 {file_path} 时出错: {str(e)}")
    
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
    
    # 清理凯利指数文件夹中的临时HTML文件
    kelly_dir = os.path.join('data', date, 'kelly_history')
    if os.path.exists(kelly_dir):
        for file in os.listdir(kelly_dir):
            if file.startswith('temp_') and file.endswith('.html'):
                file_path = os.path.join(kelly_dir, file)
                try:
                    os.remove(file_path)
                    print(f"已删除凯利指数临时文件: {file_path}")
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
    
    # 由于让球文件已被注释，不再需要读取
    print(f"让球文件已被注释，跳过添加让球值到main.json")
    return True
    
    # try:
    #     with open(main_file_path, 'r', encoding='utf-8') as f:
    #         main_data = json.load(f)
        
    #     # 让球赔率文件夹路径
    #     handicap_dir = os.path.join('data', date, 'handicap_odds')
    #     if not os.path.exists(handicap_dir):
    #         print(f"未找到让球赔率文件夹: {handicap_dir}")
    #         return False
        
    #     # 遍历所有比赛
    #     for match in main_data:
    #         match_id = match.get('match_id')
    #         if not match_id:
    #             continue
            
    #         # 让球赔率文件路径
    #         handicap_file_path = os.path.join(handicap_dir, f'{match_id}.json')
    #         if not os.path.exists(handicap_file_path):
    #             print(f"未找到让球赔率文件: {handicap_file_path}")
    #             continue
            
    #         try:
    #             with open(handicap_file_path, 'r', encoding='utf-8') as f:
    #                 handicap_data = json.load(f)
                
    #             # 获取竞彩官方的让球值
    #             if "竞彩官方" in handicap_data and "handicap_list" in handicap_data["竞彩官方"]:
    #                 handicap_list = handicap_data["竞彩官方"]["handicap_list"]
    #                 if handicap_list and len(handicap_list) > 0:
    #                     handicap_value = handicap_list[0].get("handicap", "")
                        
    #                     # 添加让球值到main数据中
    #                     match["handicap"] = handicap_value
    #                     print(f"已为 {match_id} 添加让球值: {handicap_value}")
    #                 else:
    #                     print(f"未找到 {match_id} 的让球值数据")
    #             else:
    #                 print(f"未找到 {match_id} 的竞彩官方让球数据")
            
    #         except Exception as e:
    #             print(f"处理 {match_id} 的让球数据时出错: {str(e)}")
    #             continue
        
    #     # 保存更新后的main.json文件
    #     with open(main_file_path, 'w', encoding='utf-8') as f:
    #         json.dump(main_data, f, ensure_ascii=False, indent=2)
        
    #     print(f"让球值已成功添加到main.json文件")
    #     return True
    
    # except Exception as e:
    #     print(f"处理main.json文件时出错: {str(e)}")
    #     return False

def test_size_data_write(match_id, date):
    """测试写入大小球数据"""
    try:
        # 创建大小球文件夹
        size_dir = os.path.join('data', date, 'size_odds')
        os.makedirs(size_dir, exist_ok=True)
        
        # HTML文件路径
        temp_size_html_path = os.path.join(size_dir, f'temp_{match_id}.html')
        
        # 检查临时HTML文件是否存在
        if os.path.exists(temp_size_html_path):
            print(f"找到临时HTML文件: {temp_size_html_path}")
            
            # 读取HTML内容并解析
            with open(temp_size_html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
                size_data = parse_size_data(html_content)
            
            if size_data:
                # 保存大小球数据
                size_file_path = os.path.join(size_dir, f'{match_id}.json')
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
    """删除指定日期的handicap_odds、kelly_history和ou_odds文件夹下的竞彩官方数据"""
    print(f"开始删除 {date} 竞彩官方数据...")
    
    folders = [
        # os.path.join('data', date, 'handicap_odds'),
        os.path.join('data', date, 'kelly_history'),
        os.path.join('data', date, 'ou_odds')
    ]
    
    files_processed = 0
    files_modified = 0
    
    for folder_path in folders:
        if not os.path.exists(folder_path):
            print(f"文件夹不存在: {folder_path}")
            continue
            
        for file_name in os.listdir(folder_path):
            if not file_name.endswith('.json'):
                continue
                
            file_path = os.path.join(folder_path, file_name)
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
    """将JSON文件转换为更易读的紧凑格式，以加快读取速度并提高可读性，并删除原JSON文件"""
    print(f"开始将 {date} 的数据转换为紧凑格式...")
    
    folders = [
        os.path.join('data', date, 'asian_odds'),
        os.path.join('data', date, 'ou_odds'),
        os.path.join('data', date, 'size_odds'),
        # os.path.join('data', date, 'handicap_odds'),
        os.path.join('data', date, 'kelly_history')
    ]
    
    files_processed = 0
    files_converted = 0
    files_deleted = 0
    compact_folders_removed = 0
    
    for folder_path in folders:
        if not os.path.exists(folder_path):
            print(f"文件夹不存在: {folder_path}")
            continue
        
        # 检查并删除已存在的compact文件夹
        compact_folder = os.path.join(folder_path, 'compact')
        if os.path.exists(compact_folder):
            # 首先检查compact文件夹中是否有txt文件需要移动到上层目录
            for compact_file in os.listdir(compact_folder):
                if compact_file.endswith('.txt'):
                    try:
                        # 检查是否有重名文件
                        src_path = os.path.join(compact_folder, compact_file)
                        dst_path = os.path.join(folder_path, compact_file)
                        
                        # 如果目标路径已存在，先删除目标文件
                        if os.path.exists(dst_path):
                            os.remove(dst_path)
                            
                        # 移动文件
                        os.rename(src_path, dst_path)
                        print(f"已将文件 {compact_file} 从compact文件夹移动到主目录")
                    except Exception as e:
                        print(f"移动文件 {compact_file} 时出错: {str(e)}")
            
            try:
                # 删除所有compact文件夹中的剩余文件
                remaining_files = os.listdir(compact_folder)
                for remaining_file in remaining_files:
                    try:
                        os.remove(os.path.join(compact_folder, remaining_file))
                    except Exception as e:
                        print(f"删除compact文件夹中的文件 {remaining_file} 时出错: {str(e)}")
                
                # 删除compact文件夹
                os.rmdir(compact_folder)
                compact_folders_removed += 1
                print(f"已删除compact文件夹: {compact_folder}")
            except Exception as e:
                print(f"删除compact文件夹 {compact_folder} 时出错: {str(e)}")
        
        for file_name in os.listdir(folder_path):
            if not file_name.endswith('.json') or file_name.startswith('temp_'):
                continue
                
            json_path = os.path.join(folder_path, file_name)
            txt_path = os.path.join(folder_path, file_name.replace('.json', '.txt'))
            files_processed += 1
            
            try:
                # 读取JSON文件
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 将数据转换为紧凑格式
                with open(txt_path, 'w', encoding='utf-8') as f:
                    # 添加文件头部的数据格式说明
                    folder_name = os.path.basename(folder_path)
                    
                    if 'asian_odds' in folder_path:
                        f.write("# 亚盘赔率数据 - 格式说明\n")
                        f.write("# 公司名|初盘盘口,初盘主赔率,初盘客赔率,初盘更新时间|即时盘口,即时主赔率,即时客赔率,即时更新时间,即时状态|历史变化[盘口,主赔率,客赔率,更新时间]\n")
                    elif 'ou_odds' in folder_path:
                        f.write("# 欧赔赔率数据 - 格式说明\n")
                        f.write("# 公司名|初盘胜,初盘平,初盘负,初返还率,初胜率,初平率,初负率,初凯利胜,初凯利平,初凯利负|即时胜,即时平,即时负,即返还率,即胜率,即平率,即负率,即凯利胜,即凯利平,即凯利负|历史变化[胜赔,平赔,负赔,返还率,更新时间,胜变化,平变化,负变化]\n")
                    elif 'size_odds' in folder_path:
                        f.write("# 大小球赔率数据 - 格式说明\n")
                        f.write("# 公司名|初盘盘口,初盘大球赔率,初盘小球赔率|即时盘口,即时大球赔率,即时小球赔率|历史变化[盘口,大球赔率,小球赔率,更新时间]\n")
                    elif 'handicap_odds' in folder_path:
                        f.write("# 让球赔率数据 - 格式说明\n")
                        f.write("# 公司名|初盘让球,初盘主胜赔率,初盘客胜赔率|即时让球,即时主胜赔率,即时客胜赔率|历史变化[让球,主胜赔率,平局赔率,客胜赔率,更新时间]\n")
                    elif 'kelly_history' in folder_path:
                        f.write("# 凯利指数数据 - 格式说明\n")
                        f.write("# 公司名|初始凯利[胜,平,负,更新时间]|历史变化[胜,平,负,更新时间],...\n")
                    
                    f.write("\n")
                    
                    # 处理每个公司的数据
                    for company, company_data in data.items():
                        line_parts = [company]
                        
                        # 根据不同类型的数据使用不同的格式化方式
                        if 'asian_odds' in folder_path:
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
                            if 'asian_history' in company_data and company_data['asian_history']:
                                for h in company_data['asian_history']:
                                    history_item = f"[{h.get('handicap', '')},{h.get('home_odds', '')},{h.get('away_odds', '')},{h.get('update_time', '')}]"
                                    history.append(history_item)
                            line_parts.append(",".join(history))
                        
                        elif 'ou_odds' in folder_path:
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
                            if 'odds_history' in company_data and company_data['odds_history']:
                                for h in company_data['odds_history']:
                                    history_item = f"[{h.get('win_odds', '')},{h.get('draw_odds', '')},{h.get('lose_odds', '')},{h.get('return_rate', '')},{h.get('update_time', '')},{h.get('win_change', '')},{h.get('draw_change', '')},{h.get('lose_change', '')}]"
                                    history.append(history_item)
                            line_parts.append(",".join(history))
                        
                        elif 'size_odds' in folder_path:
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
                            if 'size_history' in company_data and company_data['size_history']:
                                for h in company_data['size_history']:
                                    history_item = f"[{h.get('size', '')},{h.get('over_odds', '')},{h.get('under_odds', '')},{h.get('update_time', '')}]"
                                    history.append(history_item)
                            line_parts.append(",".join(history))
                        
                        elif 'handicap_odds' in folder_path:
                            # 让球数据使用handicap_list结构，需要为每个让球值生成独立的一行
                            if 'handicap_list' in company_data and company_data['handicap_list']:
                                # 遍历每个让球值
                                for handicap_item in company_data['handicap_list']:
                                    # 创建新的行部分数组，保留公司名
                                    handicap_line_parts = [company]
                                    
                                    # 初盘数据
                                    initial_odds = handicap_item.get('initial_odds', ['', ''])
                                    initial = f"{handicap_item.get('handicap', '')},{initial_odds[0] if len(initial_odds) > 0 else ''},{initial_odds[1] if len(initial_odds) > 1 else ''}"
                                    handicap_line_parts.append(initial)
                                    
                                    # 即时盘数据
                                    current_odds = handicap_item.get('current_odds', ['', ''])
                                    current = f"{handicap_item.get('handicap', '')},{current_odds[0] if len(current_odds) > 0 else ''},{current_odds[1] if len(current_odds) > 1 else ''}"
                                    handicap_line_parts.append(current)
                                    
                                    # 历史变化
                                    history = []
                                    # 先检查handicap_item是否有handicap_history
                                    if 'handicap_history' in handicap_item and handicap_item['handicap_history']:
                                        for h in handicap_item['handicap_history']:
                                            # 修复：包含draw_odds(平局赔率)
                                            history_item = f"[{handicap_item.get('handicap', '')},{h.get('home_odds', '')},{h.get('draw_odds', '')},{h.get('away_odds', '')},{h.get('update_time', '')}]"
                                            history.append(history_item)
                                    # 如果handicap_item没有handicap_history，检查公司数据是否有相应让球值的历史记录
                                    elif 'handicap_history' in company_data:
                                        # 获取当前让球值
                                        current_handicap = handicap_item.get('handicap', '')
                                        # 检查公司数据中是否有该让球值的历史记录
                                        if current_handicap in company_data['handicap_history']:
                                            for h in company_data['handicap_history'][current_handicap]:
                                                history_item = f"[{current_handicap},{h.get('home_odds', '')},{h.get('draw_odds', '')},{h.get('away_odds', '')},{h.get('update_time', '')}]"
                                                history.append(history_item)
                                    handicap_line_parts.append(",".join(history))
                                    
                                    # 使用竖线(|)作为主要分隔符将所有部分连接起来，为每个让球值写入单独的一行
                                    f.write("|".join(handicap_line_parts) + "\n")
                                
                                # 由于我们已经写入了所有让球值的行，跳过外部的写入
                                continue
                            else:
                                line_parts.append(",,")
                                line_parts.append(",,")
                                line_parts.append("")
                        
                        elif 'kelly_history' in folder_path:
                            # 凯利指数数据是一个数组，而不是对象
                            kelly_history = []
                            
                            # 检查是否为列表类型
                            if isinstance(company_data, list) and company_data:
                                # 使用第一条记录作为初始值
                                initial_record = company_data[-1] if company_data else {}
                                initial = f"[{initial_record.get('kelly_win', '')},{initial_record.get('kelly_draw', '')},{initial_record.get('kelly_lose', '')},{initial_record.get('update_time', '')}]"
                                line_parts.append(initial)
                                
                                # 所有记录作为历史变化
                                history_items = []
                                for item in company_data:
                                    history_item = f"[{item.get('kelly_win', '')},{item.get('kelly_draw', '')},{item.get('kelly_lose', '')},{item.get('update_time', '')}]"
                                    history_items.append(history_item)
                                
                                line_parts.append(",".join(history_items))
                            else:
                                # 如果不是列表，保留旧的处理方式作为备选
                                initial_kelly = company_data.get('initial_kelly', ['', '', '']) if isinstance(company_data, dict) else ['', '', '']
                                initial = f"{initial_kelly[0] if len(initial_kelly) > 0 else ''},{initial_kelly[1] if len(initial_kelly) > 1 else ''},{initial_kelly[2] if len(initial_kelly) > 2 else ''}"
                                line_parts.append(initial)
                                
                                current_kelly = company_data.get('current_kelly', ['', '', '']) if isinstance(company_data, dict) else ['', '', '']
                                current = f"{current_kelly[0] if len(current_kelly) > 0 else ''},{current_kelly[1] if len(current_kelly) > 1 else ''},{current_kelly[2] if len(current_kelly) > 2 else ''}"
                                line_parts.append(current)
                        
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
    if compact_folders_removed > 0:
        print(f"已删除 {compact_folders_removed} 个compact文件夹")
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
        
        # 创建目录结构（防止线程竞争创建目录）
        odds_dir = os.path.join('data', target_date, 'ou_odds')
        size_dir = os.path.join('data', target_date, 'size_odds')
        # handicap_dir = os.path.join('data', target_date, 'handicap_odds')
        asian_dir = os.path.join('data', target_date, 'asian_odds')
        os.makedirs(odds_dir, exist_ok=True)
        os.makedirs(size_dir, exist_ok=True)
        # os.makedirs(handicap_dir, exist_ok=True)
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
        # add_handicap_to_main_json(target_date)
        
        # 删除竞彩官方数据
        remove_jingcai_data(target_date)
        
        # 转换为紧凑格式
        if not no_compact:
            convert_json_to_compact(target_date)
            print("已生成紧凑格式文件，后续分析时使用compact文件夹中的文件可大幅提高读取速度")
                
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