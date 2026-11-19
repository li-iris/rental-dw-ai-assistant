-- 邮编参考表清洗：只保留投递区域，统一大小写；注意上游 SA4_NAME_2021 列整列错误，改用 sa4name（数据质量测试会拦截）
SELECT DISTINCT
  CAST(postcode AS INTEGER)                     AS postcode,
  upper(substr(locality,1,1)) || lower(substr(locality,2)) AS locality,
  NULLIF(sa4name, '')                           AS sa4,
  NULLIF(sa3name, '')                           AS sa3,
  NULLIF(lgaregion, '')                         AS lga
FROM raw_postcodes
WHERE type = 'Delivery Area' AND locality NOT LIKE '% DC' AND locality NOT LIKE '% BC'
