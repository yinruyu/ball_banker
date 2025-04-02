import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
import time
import random
import argparse
import sys

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

def debug_match(fixture_id, match_id, date):
    # 创建欧赔文件夹
    odds_dir = os.path.join('data', date, 'ou_odds')
    os.makedirs(odds_dir, exist_ok=True)
    
    # 创建大小球文件夹
    size_dir = os.path.join('data', date, 'size_odds')
    os.makedirs(size_dir, exist_ok=True)
    
    # 欧赔URL
    odds_url = f'https://odds.500.com/fenxi/ouzhi-{fixture_id}.shtml?ctype=2'
    
    # 大小球URL
    size_url = f'https://odds.500.com/fenxi/daxiao-{fixture_id}.shtml'
    
    # 模拟浏览器请求头
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Connection': 'keep-alive',
        'Referer': 'https://odds.500.com/',
        'Upgrade-Insecure-Requests': '1'
    }
    
    try:
        # 使用会话保持
        session = requests.Session()
        
        # 获取欧赔数据
        print(f"正在获取欧赔数据: {odds_url}")
        response = session.get(odds_url, headers=headers, timeout=10)
        response.encoding = 'gb2312'
        
        # 添加随机延迟
        time.sleep(random.uniform(1, 3))
        
        if response.status_code == 403:
            print(f"访问被拒绝 (403 Forbidden): {odds_url}")
            return
        
        # 临时保存HTML文件
        temp_html_path = os.path.join(odds_dir, f'temp_{match_id}.html')
        with open(temp_html_path, 'w', encoding='utf-8') as f:
            f.write(response.text)
        print(f"已保存临时HTML文件: {temp_html_path}")
        
        # 解析HTML内容
        with open(temp_html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
            odds_data = parse_odds_data(html_content)
        
        # 保存欧赔数据
        file_path = os.path.join(odds_dir, f'{match_id}.json')
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(odds_data, f, ensure_ascii=False, indent=2)
        print(f"已保存欧赔数据到: {file_path}")
            
        if not odds_data:
            print(f"警告：未解析到 {match_id} 的欧赔数据")
        
        # 获取大小球数据
        print(f"正在获取大小球数据: {size_url}")
        response = session.get(size_url, headers=headers, timeout=10)
        response.encoding = 'gb2312'
        
        # 添加随机延迟
        time.sleep(random.uniform(1, 3))
        
        if response.status_code == 403:
            print(f"访问被拒绝 (403 Forbidden): {size_url}")
            return
        
        # 临时保存大小球HTML文件
        temp_size_html_path = os.path.join(size_dir, f'temp_{match_id}.html')
        with open(temp_size_html_path, 'w', encoding='utf-8') as f:
            f.write(response.text)
        print(f"已保存临时大小球HTML文件: {temp_size_html_path}")
        
        # 解析大小球HTML内容
        with open(temp_size_html_path, 'r', encoding='utf-8') as f:
            size_html_content = f.read()
            size_data = parse_size_data(size_html_content)
        
        # 保存大小球数据
        size_file_path = os.path.join(size_dir, f'{match_id}.json')
        with open(size_file_path, 'w', encoding='utf-8') as f:
            json.dump(size_data, f, ensure_ascii=False, indent=2)
        print(f"已保存大小球数据到: {size_file_path}")
        
        if not size_data:
            print(f"警告：未解析到 {match_id} 的大小球数据")
            
    except requests.exceptions.RequestException as e:
        print(f"网络请求错误: {str(e)}")
    except Exception as e:
        print(f"处理 {match_id} 时出错: {str(e)}")

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
    
    print(f"清理临时HTML文件完成")

def main():
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='爬取足球比赛赔率数据')
    parser.add_argument('-d', '--date', help='指定日期 (格式: YYYY-MM-DD)', default=datetime.now().strftime('%Y-%m-%d'))
    parser.add_argument('--keep-html', action='store_true', help='保留临时HTML文件')
    args = parser.parse_args()
    
    # 使用指定日期或当前日期
    target_date = args.date
    keep_html = args.keep_html
    
    # 创建data目录
    if not os.path.exists('data'):
        os.makedirs('data')
    
    print(f"开始爬取 {target_date} 的比赛数据")
    
    # 获取比赛数据
    matches = get_match_data(target_date)
    
    if matches:
        # 保存数据
        save_to_json(matches, target_date)
        
        # 处理所有比赛
        for match in matches:
            if 'fixture_id' in match:
                print(f"正在处理: {match['match_id']} - {match.get('home_team', '')} vs {match.get('away_team', '')}")
                # 特殊处理周二001
                if match['match_id'] == '周二001':
                    print(f"特殊处理周二001...")
                    # 尝试多次获取数据，使用不同的选择器和解析策略
                    # 额外的处理逻辑...
                
                debug_match(match['fixture_id'], match['match_id'], target_date)
                
                # 特殊处理周二001，检查是否成功获取数据
                if match['match_id'] == '周二001':
                    size_file_path = os.path.join('data', target_date, 'size_odds', f"{match['match_id']}.json")
                    if os.path.exists(size_file_path):
                        with open(size_file_path, 'r', encoding='utf-8') as f:
                            data = f.read()
                            if data.strip() == '{}' or len(data) < 10:
                                print(f"周二001数据为空，尝试重新解析...")
                                # 重新调用测试函数尝试解析数据
                                test_size_data_write(match['match_id'], target_date)
        
        # 如果不需要保留HTML文件，则清理
        if not keep_html:
            clean_temp_html_files(target_date)
                
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

if __name__ == '__main__':
    # 检查命令行参数
    if len(sys.argv) > 1:
        if sys.argv[1] == '-d':
            main()  # 只运行主函数，不运行测试函数
        else:
            print(f"未知参数: {sys.argv[1]}")
    else:
        # 如果直接运行脚本（没有参数），使用不同的文件名运行测试函数
        test_file = 'test_data'
        test_size_data_write(test_file, '2025-04-01')
        print(f"测试数据已写入 {test_file}.json") 