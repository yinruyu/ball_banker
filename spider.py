import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
import time
import random
import argparse

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

    # 查找所有大小球行
    rows = soup.select('tr.tableline')
    if not rows:
        print("未找到大小球数据")
        return size_data
    
    for row in rows:
        company_name_elem = row.select_one('td.tb_plgs')
        if company_name_elem:
            company_name = company_name_elem.text.strip()
        else:
            company_name = "未知公司"
        
        # 初始化该公司的数据结构
        company_data = {
            'current_size': {
                '大': '',
                '盘': '',
                '小': '',
                '更新时间': ''
            },
            'initial_size': {
                '大': '',
                '盘': '',
                '小': '',
                '更新时间': ''
            }
        }
        
        # 解析即时大小球数据
        current_size_cells = row.select('td.odds_daxiao')
        if len(current_size_cells) >= 3:
            company_data['current_size']['大'] = current_size_cells[0].text.strip()
            company_data['current_size']['盘'] = current_size_cells[1].text.strip()
            company_data['current_size']['小'] = current_size_cells[2].text.strip()
            
            # 尝试获取更新时间
            update_time = row.select_one('td.odds_uptime')
            if update_time:
                company_data['current_size']['更新时间'] = update_time.text.strip()
        
        # 解析初始大小球数据
        initial_size_cells = row.select('td.odds_daxiao_begin')
        if len(initial_size_cells) >= 3:
            company_data['initial_size']['大'] = initial_size_cells[0].text.strip()
            company_data['initial_size']['盘'] = initial_size_cells[1].text.strip()
            company_data['initial_size']['小'] = initial_size_cells[2].text.strip()
            
            # 尝试获取更新时间
            begin_time = row.select_one('td.odds_begin_uptime')
            if begin_time:
                company_data['initial_size']['更新时间'] = begin_time.text.strip()
        
        # 添加该公司的数据
        size_data[company_name] = company_data
    
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
        
        # 处理完后删除临时HTML文件
        if os.path.exists(temp_html_path):
            os.remove(temp_html_path)
            print(f"已删除临时HTML文件: {temp_html_path}")
            
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
        
        # 处理完后删除临时大小球HTML文件
        if os.path.exists(temp_size_html_path):
            os.remove(temp_size_html_path)
            print(f"已删除临时大小球HTML文件: {temp_size_html_path}")
        
        if not size_data:
            print(f"警告：未解析到 {match_id} 的大小球数据")
            
    except requests.exceptions.RequestException as e:
        print(f"网络请求错误: {str(e)}")
    except Exception as e:
        print(f"处理 {match_id} 时出错: {str(e)}")

def main():
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='爬取足球比赛赔率数据')
    parser.add_argument('-d', '--date', help='指定日期 (格式: YYYY-MM-DD)', default=datetime.now().strftime('%Y-%m-%d'))
    args = parser.parse_args()
    
    # 使用指定日期或当前日期
    target_date = args.date
    
    # 创建data目录
    if not os.path.exists('data'):
        os.makedirs('data')
    
    print(f"开始爬取 {target_date} 的比赛数据")
    
    # 获取比赛数据
    matches = get_match_data(target_date)
    
    if matches:
        # 保存数据
        save_to_json(matches, target_date)
        # 处理所有比赛，而不仅仅是周二001
        for match in matches:
            if 'fixture_id' in match:
                print(f"正在处理: {match['match_id']} - {match.get('home_team', '')} vs {match.get('away_team', '')}")
                debug_match(match['fixture_id'], match['match_id'], target_date)
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

if __name__ == '__main__':
    main() 