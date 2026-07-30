# -*- coding: utf-8 -*-
"""业务深度分析 — 行业/产业链/竞争格局（LLM 生成）"""

import os
from typing import Dict


def _call_llm(prompt: str, max_tokens: int = 800) -> str:
    """调用 LLM 生成分析文本"""
    try:
        import openai
        
        api_key = os.environ.get("OPENAI_API_KEY", "")
        base_url = os.environ.get("OPENAI_BASE_URL", "")
        model = os.environ.get("LLM_MODEL", "")
        
        # Fallback: 读取 Hermes config
        if not api_key:
            import yaml
            config_path = os.path.expanduser("~/.hermes/config.yaml")
            if os.path.exists(config_path):
                with open(config_path) as f:
                    cfg = yaml.safe_load(f)
                api_key = cfg.get("model", {}).get("api_key", "")
                base_url = cfg.get("model", {}).get("base_url", "")
                model = cfg.get("model", {}).get("default", model)
        
        if not api_key:
            print("[LLM] No API key found")
            return ""
        
        client = openai.OpenAI(api_key=api_key, base_url=base_url)
        
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.7,
        )
        content = response.choices[0].message.content
        return content.strip() if content else ""
    except Exception as e:
        print(f"[LLM] Error: {e}")
        return ""


def _build_industry_prompt(company: Dict, fundamentals: Dict) -> str:
    """构建行业分析 prompt"""
    return f"""你是一位资深的半导体行业分析师。请基于以下信息，撰写该公司的行业分析报告（300-500字）：

公司：{company.get('short_name', '')}
行业：{company.get('industry', '')}
主营业务：{company.get('main_business', '')}
产品：{company.get('product_names', '')}
财务数据：
- 营收增速：{fundamentals.get('growth', {}).get('revenue_growth', {}).get('value', 'N/A')}%
- 净利增速：{fundamentals.get('growth', {}).get('net_profit_growth', {}).get('value', 'N/A')}%
- ROE：{fundamentals.get('profitability', {}).get('roe', {}).get('value', 'N/A')}%
- 毛利率：{fundamentals.get('profitability', {}).get('gross_margin', {}).get('value', 'N/A')}%

请从以下维度分析：
1. 行业整体发展趋势与市场规模
2. 技术演进方向（如AI、国产替代等）
3. 政策环境与行业壁垒
4. 行业周期位置（上行/下行/复苏）
5. 未来3-5年增长点预测

输出格式：直接输出分析文本，不要标题，段落清晰，语言专业但易懂。"""


def _build_supply_chain_prompt(company: Dict) -> str:
    """构建产业链分析 prompt"""
    return f"""你是一位半导体产业链专家。请分析该公司的产业链上下游关系（200-300字）：

公司：{company.get('short_name', '')}
主营业务：{company.get('main_business', '')}
产品类型：{company.get('product_type', '')}
产品名称：{company.get('product_names', '')}

请分析：
1. 上游供应商：晶圆代工、封装测试、IP授权、EDA工具等
2. 下游应用：消费电子、汽车电子、工业控制、物联网等
3. 公司在产业链中的位置与话语权
4. 供应链风险与国产替代进展

输出格式：直接输出分析文本，简洁专业。"""


def _build_competition_prompt(company: Dict, fundamentals: Dict) -> str:
    """构建竞争格局分析 prompt"""
    return f"""你是一位半导体行业研究员。请分析该公司的竞争格局（200-300字）：

公司：{company.get('short_name', '')}
行业：{company.get('industry', '')}
产品：{company.get('product_names', '')}
毛利率：{fundamentals.get('profitability', {}).get('gross_margin', {}).get('value', 'N/A')}%
营收增速：{fundamentals.get('growth', {}).get('revenue_growth', {}).get('value', 'N/A')}%

请分析：
1. 国内外主要竞争对手（2-3家）
2. 公司的核心竞争力与差异化
3. 市场份额与行业地位
4. 技术壁垒与护城河

输出格式：直接输出分析文本，客观专业。"""


def _build_business_prompt(company: Dict, fundamentals: Dict) -> str:
    """构建业务构成分析 prompt"""
    return f"""你是一位财务分析师。请分析该公司的业务构成与产品结构（200-300字）：

公司：{company.get('short_name', '')}
主营业务：{company.get('main_business', '')}
产品类型：{company.get('product_type', '')}
产品名称：{company.get('product_names', '')}
营收增速：{fundamentals.get('growth', {}).get('revenue_growth', {}).get('value', 'N/A')}%
毛利率：{fundamentals.get('profitability', {}).get('gross_margin', {}).get('value', 'N/A')}%

请分析：
1. 核心产品线及其市场定位
2. 产品结构与收入贡献推测
3. 高增长业务与潜力产品
4. 产品组合的协同效应

输出格式：直接输出分析文本，简洁清晰。"""


def _build_tech_interpretation_prompt(technicals: Dict) -> str:
    """构建技术面解读 prompt"""
    return f"""你是一位技术分析师。请用通俗易懂的语言解读以下技术指标（150-200字）：

当前价格：{technicals.get('price', 'N/A')}
MA5：{technicals.get('ma5', 'N/A')}（{technicals.get('ma5_signal', '')}）
MA20：{technicals.get('ma20', 'N/A')}（{technicals.get('ma20_signal', '')}）
MA60：{technicals.get('ma60', 'N/A')}（{technicals.get('ma60_signal', '')}）
MACD：{technicals.get('macd', {}).get('signal', '')}
KDJ：K={technicals.get('kdj', {}).get('k', 'N/A')}
RSI6：{technicals.get('rsi6', 'N/A')}
量比：{technicals.get('volume_ratio', 'N/A')}
支撑位：{technicals.get('support', 'N/A')}
压力位：{technicals.get('resistance', 'N/A')}

请解读：
1. 当前趋势判断（上升/下降/震荡）
2. 短期买卖信号
3. 关键价位与风险提示

输出格式：直接输出解读文本，避免专业术语堆砌。"""


def analyze(symbol: str, company: Dict, fundamentals: Dict, technicals: Dict) -> Dict:
    """生成业务深度分析"""
    result = {
        "industry_analysis": "",
        "supply_chain": "",
        "competition": "",
        "business_structure": "",
        "tech_interpretation": "",
    }
    
    # 行业分析
    prompt = _build_industry_prompt(company, fundamentals)
    result["industry_analysis"] = _call_llm(prompt, max_tokens=800)
    
    # 产业链分析
    prompt = _build_supply_chain_prompt(company)
    result["supply_chain"] = _call_llm(prompt, max_tokens=500)
    
    # 竞争格局
    prompt = _build_competition_prompt(company, fundamentals)
    result["competition"] = _call_llm(prompt, max_tokens=500)
    
    # 业务构成
    prompt = _build_business_prompt(company, fundamentals)
    result["business_structure"] = _call_llm(prompt, max_tokens=500)
    
    # 技术面解读
    prompt = _build_tech_interpretation_prompt(technicals)
    result["tech_interpretation"] = _call_llm(prompt, max_tokens=400)
    
    return result
