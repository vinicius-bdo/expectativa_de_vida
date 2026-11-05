SELECT
    d.ano,
    p.pais,
    f.gasto_usd,
    f.expectativa_de_vida
FROM marts.fato_gastos AS f
JOIN marts.d_calendario AS d USING (id_calendario)
JOIN marts.d_pais AS p USING (id_pais)
WHERE d.ano BETWEEN ? AND ?
  AND (? IS NULL OR list_contains(CAST(? AS INTEGER[]), d.ano))
  AND (? IS NULL OR list_contains(CAST(? AS VARCHAR[]), p.pais))
ORDER BY d.ano, p.pais;