--# 10_Linha_do_tempo_com_gastos_e_media_da_idade.sql 
SELECT
    d.ano,
    sum(f.gasto_usd) as gasto_usd,
    ROUND(avg(f.expectativa_de_vida),2) as expectativa_media_anos
FROM marts.fato_gastos AS f
JOIN marts.d_calendario AS d USING (id_calendario)
JOIN marts.d_pais AS p USING (id_pais)
WHERE d.ano BETWEEN ? AND ?
  AND (? IS NULL OR list_contains(CAST(? AS INTEGER[]), d.ano))
  AND (? IS NULL OR list_contains(CAST(? AS VARCHAR[]), p.pais))
GROUP BY d.ano
ORDER BY d.ano ASC;