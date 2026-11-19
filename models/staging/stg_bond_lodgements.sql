-- 押金登记清洗：类型转换、编码解码；只转换不删行，问题行在下游打标
SELECT
  lodgement_date,
  substr(lodgement_date, 1, 7)                                   AS month,
  CAST(postcode AS INTEGER)                                      AS postcode,
  CASE dwelling_type
    WHEN 'F' THEN 'Flat/Unit' WHEN 'H' THEN 'House' WHEN 'T' THEN 'Terrace/Townhouse'
    WHEN 'O' THEN 'Other'     WHEN 'U' THEN 'Unknown' ELSE 'Invalid' END AS dwelling,
  CASE WHEN bedrooms GLOB '[0-9]*' AND bedrooms NOT GLOB '*[^0-9]*'
       THEN CAST(bedrooms AS INTEGER) END                        AS bedrooms,
  CASE WHEN weekly_rent GLOB '[0-9]*' AND weekly_rent NOT GLOB '*[^0-9.]*' AND CAST(weekly_rent AS REAL) > 0
       THEN CAST(weekly_rent AS REAL) END                        AS weekly_rent,
  dwelling_type AS dwelling_code_raw,
  bedrooms      AS bedrooms_raw,
  weekly_rent   AS weekly_rent_raw,
  source_file,
  source_row
FROM raw_bond_lodgements
