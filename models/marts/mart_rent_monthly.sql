-- 指标表：月 × 区域 × 房型 × 卧室数 的租约量与租金分位数（只用 is_analysable 的行）
SELECT month, region, is_greater_sydney, dwelling, bedrooms,
       count(*)                          AS lodgements,
       median(weekly_rent)               AS median_rent,
       percentile(weekly_rent, 25)       AS p25_rent,
       percentile(weekly_rent, 75)       AS p75_rent
FROM {{ ref('fct_lodgement') }}
WHERE is_analysable
GROUP BY month, region, is_greater_sydney, dwelling, bedrooms
