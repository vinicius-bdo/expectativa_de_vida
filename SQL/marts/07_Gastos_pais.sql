SELECT
    p.pais,
    sum(f.gasto_usd) as gasto_usd
FROM marts.fato_gastos AS f
JOIN marts.d_calendario AS d USING (id_calendario)
JOIN marts.d_pais AS p USING (id_pais)
WHERE f.gasto_usd IS NOT NULL
  AND d.ano BETWEEN ? AND ?
  AND (? IS NULL OR list_contains(CAST(? AS INTEGER[]), d.ano))
  AND (? IS NULL OR list_contains(CAST(? AS VARCHAR[]), p.pais))
group by p.pais
ORDER BY gasto_usd DESC
LIMIT 10;