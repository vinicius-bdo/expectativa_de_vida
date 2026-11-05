--# 02_Total_paises.sql 
SELECT COUNT(DISTINCT p.id_pais) AS total_paises
FROM marts.d_pais AS p
JOIN marts.fato_gastos AS f USING (id_pais)
JOIN marts.d_calendario AS d USING (id_calendario)
WHERE d.ano BETWEEN ? AND ?
  AND (? IS NULL OR list_contains(CAST(? AS INTEGER[]), d.ano))
  AND (? IS NULL OR list_contains(CAST(? AS VARCHAR[]), p.pais));