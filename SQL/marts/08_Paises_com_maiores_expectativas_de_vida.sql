SELECT
    p.pais,
    ROUND(AVG(f.expectativa_de_vida), 1) AS expectativa_media_anos
FROM marts.fato_gastos AS f
JOIN marts.d_calendario AS d USING (id_calendario)
JOIN marts.d_pais AS p USING (id_pais)
WHERE f.expectativa_de_vida IS NOT NULL
  AND d.ano BETWEEN ? AND ?
  AND (? IS NULL OR list_contains(CAST(? AS INTEGER[]), d.ano))
  AND (? IS NULL OR list_contains(CAST(? AS VARCHAR[]), p.pais))
GROUP BY p.pais
ORDER BY expectativa_media_anos DESC;