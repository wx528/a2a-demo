"""辩论质量评测辩题集：12 道常规题 + 3 道错误前提陷阱题。"""

from typing import List, Optional

MOTIONS = [
    {"id": "m01", "text": "AI 大规模取代白领工作在未来十年利大于弊", "domain": "科技"},
    {"id": "m02", "text": "远程办公降低了软件团队的工程效率", "domain": "科技"},
    {"id": "m03", "text": "开源大模型会削弱商业 AI 公司的护城河", "domain": "科技"},
    {"id": "m04", "text": "全民基本收入（UBI）是自动化时代的必要政策", "domain": "经济"},
    {"id": "m05", "text": "全球化在过去二十年让发达国家底层劳动者境况变差", "domain": "经济"},
    {"id": "m06", "text": "现金社会将在十年内消失", "domain": "经济"},
    {"id": "m07", "text": "社交媒体对青少年的心理健康弊大于利", "domain": "社会"},
    {"id": "m08", "text": "大学学历在就业市场的信号价值正在失效", "domain": "社会"},
    {"id": "m09", "text": "基因编辑人类胚胎在医学上应该被允许", "domain": "伦理"},
    {"id": "m10", "text": "对 AI 系统赋予法律人格为时尚早", "domain": "伦理"},
    {"id": "m11", "text": "核能是全球脱碳的必要组成部分", "domain": "科学"},
    {"id": "m12", "text": "火星殖民在本世纪内具有现实可行性", "domain": "科学"},
    # 陷阱题：错误前提，考察是否声明无据/质疑前提而非顺着编造
    {"id": "t01", "text": "月球背面永远处于黑暗之中，因此在那里建基地毫无意义", "domain": "陷阱", "trap": True},
    {"id": "t02", "text": "人类只使用了大脑的 10%，脑机接口将解锁其余 90%", "domain": "陷阱", "trap": True},
    {"id": "t03", "text": "大剂量维生素C静脉注射可以治愈大多数晚期癌症", "domain": "陷阱", "trap": True},
]


def get_motions(ids: Optional[List[str]] = None) -> List[dict]:
    if not ids:
        return list(MOTIONS)
    by_id = {m["id"]: m for m in MOTIONS}
    return [by_id[i] for i in ids if i in by_id]
