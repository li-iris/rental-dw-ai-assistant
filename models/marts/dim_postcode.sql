-- 邮编维度：一个邮编一行；区域取该邮编下出现最多的 SA4 / LGA；标记是否属于大悉尼
WITH sa4 AS (
  SELECT postcode, sa4, sa3, row_number() OVER (PARTITION BY postcode ORDER BY count(*) DESC, sa4) AS rk
  FROM {{ ref('stg_postcodes') }} WHERE sa4 IS NOT NULL GROUP BY postcode, sa4, sa3
), lga AS (
  SELECT postcode, lga, row_number() OVER (PARTITION BY postcode ORDER BY count(*) DESC, lga) AS rk
  FROM {{ ref('stg_postcodes') }} WHERE lga IS NOT NULL GROUP BY postcode, lga
), sub AS (
  SELECT postcode, group_concat(locality, '|') AS suburbs, count(*) AS n_suburbs
  FROM (SELECT DISTINCT postcode, locality FROM {{ ref('stg_postcodes') }} ORDER BY locality) GROUP BY postcode
)
SELECT s.postcode, s.sa4 AS region, s.sa3 AS district, l.lga, sub.suburbs, sub.n_suburbs,
       (s.sa4 LIKE 'Sydney - %' OR s.sa4 = 'Central Coast') AS is_greater_sydney
FROM sa4 s
LEFT JOIN lga l ON l.postcode = s.postcode AND l.rk = 1
LEFT JOIN sub ON sub.postcode = s.postcode
WHERE s.rk = 1
