-- 事实表：每条新签租约一行，带维度和分析可用标记；口径：住宅类型 + 租金 80–5000 澳元/周 + 邮编可匹配
SELECT
  l.lodgement_date, l.month, l.postcode, d.region, d.district, d.lga, COALESCE(d.is_greater_sydney, 0) AS is_greater_sydney,
  l.dwelling, l.bedrooms, l.weekly_rent,
  (l.dwelling IN ('Flat/Unit', 'House', 'Terrace/Townhouse'))         AS is_residential,
  (l.weekly_rent BETWEEN 80 AND 5000)                                  AS rent_plausible,
  (d.postcode IS NOT NULL)                                             AS postcode_known,
  (l.dwelling IN ('Flat/Unit', 'House', 'Terrace/Townhouse') AND l.weekly_rent BETWEEN 80 AND 5000 AND d.postcode IS NOT NULL) AS is_analysable,
  l.source_file, l.source_row
FROM {{ ref('stg_bond_lodgements') }} l
LEFT JOIN {{ ref('dim_postcode') }} d ON d.postcode = l.postcode
