SELECT ROUND(AVG(gasto_usd), 2) AS media_gastos_usd
FROM marts.fato_gastos AS f
JOIN marts.d_calendario AS d USING (id_calendario)
JOIN marts.d_pais AS p USING (id_pais)
WHERE d.ano BETWEEN ? AND ?
  AND (? IS NULL OR list_contains(CAST(? AS INTEGER[]), d.ano))
  AND (? IS NULL OR list_contains(CAST(? AS VARCHAR[]), p.pais));