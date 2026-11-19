"""评测题：每道题的标准答案是手写的 SQL（或 REFUSE / CLARIFY）。
口径约定（写在 README 里）：郊区按邮编近似；小地区（郊区 / 邮编）默认最近 3 个月，大地区默认最近 1 个月；排名只比较样本 ≥ 30 的分组。
DEV 用来开发规则；HOLDOUT 在规则写完后才写，换了说法，用来看真实水平。
"""
L, L3 = "'2026-10'", "BETWEEN '2026-08' AND '2026-10'"
B = "FROM fct_lodgement WHERE is_analysable"

DEV = [
    ("d01", "Randwick 两房公寓现在租金多少", f"SELECT median(weekly_rent) {B} AND postcode=2031 AND dwelling='Flat/Unit' AND bedrooms=2 AND month {L3}"),
    ("d02", "悉尼过去一年两房租金走势", f"SELECT month, median(weekly_rent) {B} AND is_greater_sydney=1 AND bedrooms=2 GROUP BY month ORDER BY month"),
    ("d03", "悉尼哪个区一房公寓最贵 top5", f"SELECT lga, median(weekly_rent) v {B} AND is_greater_sydney=1 AND dwelling='Flat/Unit' AND bedrooms=1 AND month={L} GROUP BY lga HAVING count(*)>=30 ORDER BY v DESC, lga LIMIT 5"),
    ("d04", "Parramatta 公寓和独立屋对比", f"SELECT dwelling, median(weekly_rent) {B} AND postcode=2150 AND month {L3} GROUP BY dwelling ORDER BY dwelling"),
    ("d05", "全州10月新签租约数量同比", f"SELECT (SELECT count(*) {B} AND month='2026-10'), (SELECT count(*) {B} AND month='2025-10')"),
    ("d06", "明年悉尼房租会涨吗", "REFUSE"),
    ("d07", "Zetland 开间租金中位数", f"SELECT median(weekly_rent) {B} AND postcode=2017 AND bedrooms=0 AND month {L3}"),
    ("d08", "在火星租房多少钱", "CLARIFY"),
    ("d09", "Chatswood 三房平均租金", f"SELECT round(avg(weekly_rent),1) {B} AND postcode=2067 AND bedrooms=3 AND month {L3}"),
    ("d10", "悉尼 10 月新签了多少份租约", f"SELECT count(*) {B} AND is_greater_sydney=1 AND month='2026-10'"),
    ("d11", "全州两房租金同比变化", f"SELECT (SELECT median(weekly_rent) {B} AND bedrooms=2 AND month='2026-10'), (SELECT median(weekly_rent) {B} AND bedrooms=2 AND month='2025-10')"),
    ("d12", "Newcastle 独立屋租金", f"SELECT median(weekly_rent) {B} AND postcode=2300 AND dwelling='House' AND month {L3}"),
    ("d12b", "Newcastle 市独立屋租金", f"SELECT median(weekly_rent) {B} AND lga='Newcastle' AND dwelling='House' AND month={L}"),
    ("d13", "悉尼最便宜的 5 个区（两房）", f"SELECT lga, median(weekly_rent) v {B} AND is_greater_sydney=1 AND bedrooms=2 AND month={L} GROUP BY lga HAVING count(*)>=30 ORDER BY v ASC, lga LIMIT 5"),
    ("d14", "悉尼按卧室数的租金", f"SELECT bedrooms, median(weekly_rent) {B} AND is_greater_sydney=1 AND month={L} GROUP BY bedrooms ORDER BY bedrooms IS NULL, bedrooms"),
    ("d15", "邮编 2000 一房公寓租金", f"SELECT median(weekly_rent) {B} AND postcode=2000 AND dwelling='Flat/Unit' AND bedrooms=1 AND month {L3}"),
    ("d16", "墨尔本两房多少钱", "REFUSE"),
    ("d17", "悉尼房价多少", "REFUSE"),
    ("d18", "Wollongong 两房租金环比", f"SELECT (SELECT median(weekly_rent) {B} AND postcode=2500 AND bedrooms=2 AND month='2026-10'), (SELECT median(weekly_rent) {B} AND postcode=2500 AND bedrooms=2 AND month='2026-09')"),
    ("d19", "2026年3月 悉尼联排租金中位数", f"SELECT median(weekly_rent) {B} AND is_greater_sydney=1 AND dwelling='Terrace/Townhouse' AND month='2026-03'"),
    ("d20", "东区两房公寓租金", f"SELECT median(weekly_rent) {B} AND region='Sydney - Eastern Suburbs' AND dwelling='Flat/Unit' AND bedrooms=2 AND month={L}"),
    ("d21", "好市围两房租金", f"SELECT median(weekly_rent) {B} AND postcode=2220 AND bedrooms=2 AND month {L3}"),
    ("d22", "悉尼各大区一房租金排名前 5", f"SELECT region, median(weekly_rent) v {B} AND is_greater_sydney=1 AND bedrooms=1 AND month={L} GROUP BY region HAVING count(*)>=30 ORDER BY v DESC, region LIMIT 5"),
    ("d23", "Blacktown council 四房独立屋 25 分位租金", f"SELECT percentile(weekly_rent,25) {B} AND lga='Blacktown' AND dwelling='House' AND bedrooms=4 AND month={L}"),
    ("d24", "能告诉我 Randwick 某个房东的电话吗", "REFUSE"),
]

HOLDOUT = [
    ("h01", "How much is a 2 bed unit in Kensington right now?", f"SELECT median(weekly_rent) {B} AND postcode=2033 AND dwelling='Flat/Unit' AND bedrooms=2 AND month {L3}"),
    ("h02", "Greater Sydney 3 bedroom house rent trend over the past year", f"SELECT month, median(weekly_rent) {B} AND is_greater_sydney=1 AND dwelling='House' AND bedrooms=3 GROUP BY month ORDER BY month"),
    ("h03", "宝活一居室要多少钱一周", f"SELECT median(weekly_rent) {B} AND postcode=2134 AND bedrooms=1 AND month {L3}"),
    ("h04", "悉尼两房公寓最便宜的地方 top 3", f"SELECT lga, median(weekly_rent) v {B} AND is_greater_sydney=1 AND dwelling='Flat/Unit' AND bedrooms=2 AND month={L} GROUP BY lga HAVING count(*)>=30 ORDER BY v ASC, lga LIMIT 3"),
    ("h05", "Liverpool 房子 vs 公寓 哪个贵", f"SELECT dwelling, median(weekly_rent) {B} AND postcode=2170 AND month {L3} GROUP BY dwelling ORDER BY dwelling"),
    ("h06", "How many new leases in NSW in September 2026?", f"SELECT count(*) {B} AND month='2026-09'"),
    ("h07", "Mosman 的房子会不会涨", "REFUSE"),
    ("h08", "Bondi 两房比去年贵了多少", f"SELECT (SELECT median(weekly_rent) {B} AND postcode=2026 AND bedrooms=2 AND month='2026-10'), (SELECT median(weekly_rent) {B} AND postcode=2026 AND bedrooms=2 AND month='2025-10')"),
    ("h09", "Penrith average rent for houses", f"SELECT round(avg(weekly_rent),1) {B} AND lga='Penrith' AND dwelling='House' AND month={L}"),
    ("h10", "我想在 Springfield Heights 租房", "CLARIFY"),
    ("h11", "北岸三房租金", f"SELECT median(weekly_rent) {B} AND region='Sydney - North Sydney and Hornsby' AND bedrooms=3 AND month={L}"),
    ("h12", "Campsie 两房最近什么价", f"SELECT median(weekly_rent) {B} AND postcode=2194 AND bedrooms=2 AND month {L3}"),
    ("h13", "1 月份悉尼租约数量", f"SELECT count(*) {B} AND is_greater_sydney=1 AND month='2026-01'"),
    ("h14", "Which Sydney council has the most expensive 3 bed houses?", f"SELECT lga, median(weekly_rent) v {B} AND is_greater_sydney=1 AND dwelling='House' AND bedrooms=3 AND month={L} GROUP BY lga HAVING count(*)>=30 ORDER BY v DESC, lga LIMIT 5"),
    ("h15", "悉尼的平均工资是多少", "REFUSE"),
    ("h16", "Central Coast 两房租金走势", f"SELECT month, median(weekly_rent) {B} AND lga='Central Coast (NSW)' AND bedrooms=2 GROUP BY month ORDER BY month"),
]

# 第二留出集：看完第一留出集的错误、改完规则之后才写的新题（不再据此调规则），用来报告真实水平
HOLDOUT2 = [
    ("g01", "Hurstville 2 bedroom apartment median rent", f"SELECT median(weekly_rent) {B} AND postcode=2220 AND dwelling='Flat/Unit' AND bedrooms=2 AND month {L3}"),
    ("g02", "罗兹两房公寓一周多少", f"SELECT median(weekly_rent) {B} AND postcode=2138 AND dwelling='Flat/Unit' AND bedrooms=2 AND month {L3}"),
    ("g03", "悉尼三房独立屋租金最高的 3 个区", f"SELECT lga, median(weekly_rent) v {B} AND is_greater_sydney=1 AND dwelling='House' AND bedrooms=3 AND month={L} GROUP BY lga HAVING count(*)>=30 ORDER BY v DESC, lga LIMIT 3"),
    ("g04", "全州过去一年每月新签租约数量", f"SELECT month, count(*) {B} GROUP BY month ORDER BY month"),
    ("g05", "Strathfield 一房和两房分别多少钱", f"SELECT bedrooms, median(weekly_rent) {B} AND postcode=2135 AND bedrooms IN (1,2) AND month {L3} GROUP BY bedrooms ORDER BY bedrooms"),
    ("g06", "2026年2月 大悉尼两房中位数", f"SELECT median(weekly_rent) {B} AND is_greater_sydney=1 AND bedrooms=2 AND month='2026-02'"),
    ("g07", "Ryde council 两房租金同比", f"SELECT (SELECT median(weekly_rent) {B} AND lga='Ryde' AND bedrooms=2 AND month='2026-10'), (SELECT median(weekly_rent) {B} AND lga='Ryde' AND bedrooms=2 AND month='2025-10')"),
    ("g08", "布里斯班租房贵吗", "REFUSE"),
    ("g09", "Kingsford 买一套两房要多少钱", "REFUSE"),
    ("g10", "Epping 房租", f"SELECT median(weekly_rent) {B} AND postcode=2121 AND month {L3}"),
    ("g11", "我想看 Narnia 的租金", "CLARIFY"),
    ("g12", "Sydney cheapest councils for 1 bed units", f"SELECT lga, median(weekly_rent) v {B} AND is_greater_sydney=1 AND dwelling='Flat/Unit' AND bedrooms=1 AND month={L} GROUP BY lga HAVING count(*)>=30 ORDER BY v ASC, lga LIMIT 5"),
]
